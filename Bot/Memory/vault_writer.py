import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
import requests

SCRIPT_DIR = Path(__file__).resolve().parent
DB_PATH = SCRIPT_DIR / "athena.db"

# Vault Root Resolution
VAULT_DIR = SCRIPT_DIR.parents[1] / "Brain"
if not VAULT_DIR.exists():
    VAULT_DIR = SCRIPT_DIR.parent / "Brain"
if not VAULT_DIR.exists():
    VAULT_DIR = SCRIPT_DIR / "Brain"

TEMPLATES_DIR = VAULT_DIR / "Templates"

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen2.5:7b"

EXTRACTION_PROMPT = """You are the data consolidation engine for Elliot's personal knowledge graph.
Extract ONLY brand-new facts, visits, recommendations, and updates directly stated by Elliot.

CRITICAL CONSTRAINTS:
1. STRICTLY USER-ASSERTED FACTS ONLY:
   - Only extract affirmative assertions where Elliot directly shares new real-world information.
   - If Elliot asks a question (e.g., "tell me about X", "who is Y", "where is Z", "what does X do"), DO NOT extract anything from it.
   - Completely ignore inquiries, conversational banter, meta-comments, or empty statements.
   - If the transcript contains only questions or banter with no new affirmative facts, return empty lists for all arrays.
2. NO DUPLICATION & SELF-CONTAINED FACTS:
   - Do NOT duplicate existing facts.
   - NEVER leave pronouns like "it", "they", or "the place" in trivia notes; resolve them to canonical names.
   - Write trivia notes as objective, standalone statements with explicit [[Wikilinks]].
   - Do NOT include generic "Visited [[Place]]" in trivia arrays; visits are handled automatically via "visited_place".
3. DISCRETE EVENTS:
   - Only link people and places if Elliot explicitly states they were physically there together in that event.
4. SCHEMA:
   - "new_places": Name, category (cafe|restaurant|bar|brewery|spot), and who recommended it.
   - "people_updates": Name (use "Elliot Waigh" for Elliot), factual trivia list, and visited_place (or null).
   - "triples": Explicit factual relations (Subject -> Predicate -> Object).
   - "open_loops": Concrete commitments/promises made with external people.

TRANSCRIPT:
\"\"\"
{transcript}
\"\"\"

Output strictly valid JSON matching this schema:
{
  "episodic_summary": "<1-2 sentence summary with [[Wikilinks]] or empty string>",
  "new_places": [
    {
      "name": "<Exact Venue Name>",
      "category": "cafe|restaurant|bar|brewery|spot",
      "recommended_by": ["[[Person]]"]
    }
  ],
  "people_updates": [
    {
      "name": "<Full Name>",
      "trivia": ["<self-contained factual note with explicit [[Wikilinks]]>"],
      "visited_place": "<Venue Name or null>"
    }
  ],
  "triples": [
    {
      "subject": "<Entity>",
      "predicate": "<visited|met_with|works_at|recommends|located_in>",
      "object": "<Entity>"
    }
  ],
  "open_loops": [
    {
      "target": "<External Contact>",
      "commitment": "<Action>",
      "direction": "i_owe_them|they_owe_me"
    }
  ]
}"""

GENERIC_BANNED_ENTITIES = {
    "company", "current company", "job", "workplace", "bar", "cafe", 
    "restaurant", "the place", "someone", "friend", "guy", "mate",
    "<person name>", "<name>", "person name", "unknown", "none"
}

def resolve_canonical_name(folder: Path, raw_name: str) -> str:
    """Resolves single/partial names (e.g. 'Dylan') to existing canonical notes (e.g. 'Dylan Rabie')."""
    target = raw_name.strip().replace("[[", "").replace("]]", "")
    if not target or target.lower() in {"elliot", "elliot waigh", "athena"}:
        return target

    clean_target = target.lower().replace(" ", "")
    exact_matches = []
    prefix_matches = []

    if folder.exists():
        for f in folder.glob("*.md"):
            stem = f.stem
            stem_clean = stem.lower().replace(" ", "")
            parts = stem.lower().split()

            if stem_clean == clean_target:
                exact_matches.append(stem)
            elif parts and parts[0] == target.lower():
                prefix_matches.append(stem)
            elif len(clean_target) >= 4 and clean_target in stem_clean:
                prefix_matches.append(stem)

    if exact_matches:
        return exact_matches[0]
    if len(prefix_matches) == 1:
        return prefix_matches[0]
    return target

def ensure_wikilinks(text: str, people_names: List[str] = None, place_names: List[str] = None) -> str:
    """Enforces that Elliot, named contacts, and places are properly wrapped in double-bracket wikilinks."""
    if not text:
        return ""

    text = re.sub(r"\[\[Elliot(?:\s+Waigh)?\]\]", "[[Elliot Waigh]]", text)
    text = re.sub(r"(?<!\[\[)\bElliot\s+Waigh\b(?!\]\])", "[[Elliot Waigh]]", text)
    text = re.sub(r"(?<!\[\[)\bElliot\b(?!\]\])", "[[Elliot Waigh]]", text)

    if people_names:
        for name in people_names:
            if name.lower() not in {"elliot", "elliot waigh"} and not name.startswith("<"):
                pattern = rf"(?<!\[\[)\b{re.escape(name)}\b(?!\]\])"
                text = re.sub(pattern, f"[[{name}]]", text)

    if place_names:
        for pl in place_names:
            if not pl.startswith("<"):
                pattern = rf"(?<!\[\[)\b{re.escape(pl)}\b(?!\]\])"
                text = re.sub(pattern, f"[[{pl}]]", text)

    return text

def sanitize_extracted_payload(data: dict, transcript: str, people_dir: Path, places_dir: Path) -> dict:
    if not isinstance(data, dict):
        return {}

    cleaned_people = []
    for p in data.get("people_updates", []):
        raw_name = p.get("name", "").strip()
        if not raw_name or raw_name.lower() == "athena" or raw_name.startswith("<"):
            continue
        canonical_name = resolve_canonical_name(people_dir, raw_name)
        p["name"] = canonical_name

        if p.get("visited_place"):
            p["visited_place"] = resolve_canonical_name(places_dir, p["visited_place"])

        p["trivia"] = [t for t in p.get("trivia", []) if t]
        cleaned_people.append(p)
    data["people_updates"] = cleaned_people

    cleaned_places = []
    for pl in data.get("new_places", []):
        raw_place = pl.get("name", "").strip()
        if not raw_place or raw_place.startswith("<"):
            continue
        pl["name"] = resolve_canonical_name(places_dir, raw_place)
        cleaned_places.append(pl)
    data["new_places"] = cleaned_places

    cleaned_triples = []
    for trip in data.get("triples", []):
        raw_sub = trip.get("subject", "").strip().replace("[[", "").replace("]]", "")
        pred = trip.get("predicate", "").strip().lower().replace(" ", "_")
        raw_obj = trip.get("object", "").strip().replace("[[", "").replace("]]", "")

        sub = resolve_canonical_name(people_dir, raw_sub)
        obj = resolve_canonical_name(places_dir, raw_obj) if pred in {"visited", "located_in"} else resolve_canonical_name(people_dir, raw_obj)

        if not (sub and pred and obj) or sub.lower() == obj.lower():
            continue
        if any(b in obj.lower() for b in GENERIC_BANNED_ENTITIES) or any(b in sub.lower() for b in GENERIC_BANNED_ENTITIES):
            continue

        cleaned_triples.append({"subject": sub, "predicate": pred, "object": obj})
    data["triples"] = cleaned_triples

    valid_loops = []
    t_lower = transcript.lower()
    commitment_verbs = ["promise", "will bring", "will send", "will drop", "owe", "lend", "borrow", "agreed to"]

    for loop in data.get("open_loops", []):
        target = resolve_canonical_name(people_dir, loop.get("target", "").strip())
        commitment = loop.get("commitment", "").strip()
        direction = loop.get("direction", "i_owe_them").lower()

        if not target or not commitment or target.lower() in {"elliot", "elliot waigh", "athena", "me"} or target.startswith("<"):
            continue
        if any(w in commitment.lower() for w in ["job", "work", "unemployed", "feel", "search"]):
            continue
        if not any(v in t_lower for v in commitment_verbs):
            continue

        valid_loops.append({"target": target, "commitment": commitment, "direction": direction})
    data["open_loops"] = valid_loops

    return data

def find_file_case_insensitive(folder: Path, base_name: str) -> Path:
    """Finds an existing markdown file in a folder matching exact stem or unique prefix."""
    if not folder.exists():
        folder.mkdir(parents=True, exist_ok=True)
        return folder / f"{base_name}.md"

    canonical = resolve_canonical_name(folder, base_name)
    direct = folder / f"{canonical}.md"
    if direct.exists():
        return direct

    clean_target = base_name.lower().replace(" ", "").replace(".", "")
    for f in folder.glob("*.md"):
        f_clean = f.stem.lower().replace(" ", "").replace(".", "")
        if f_clean == clean_target:
            return f
    return folder / f"{canonical}.md"

def get_elliot_note(people_dir: Path) -> Path:
    """Deterministically finds Elliot's personal markdown note."""
    people_dir.mkdir(parents=True, exist_ok=True)
    for target in ["Elliot.md", "Elliot Waigh.md"]:
        candidate = people_dir / target
        if candidate.exists():
            return candidate
    for f in people_dir.glob("*.md"):
        if f.stem.lower() in {"elliot", "elliot waigh"}:
            return f
    return people_dir / "Elliot Waigh.md"

def load_template(template_filename: str) -> str:
    t_path = TEMPLATES_DIR / template_filename
    if t_path.exists():
        return t_path.read_text(encoding="utf-8")
    return ""

def provision_new_person(name: str, initial_trivia: List[str] = None) -> Path:
    """Provisions a new person note from Person_Template.md with known info."""
    clean_name = name.strip()
    
    # HARD GUARD: Reject placeholders like <Person name> from becoming files
    if not clean_name or clean_name.startswith("<") or clean_name.endswith(">") or clean_name.lower() in GENERIC_BANNED_ENTITIES:
        return None

    people_dir = VAULT_DIR / "People"
    people_dir.mkdir(parents=True, exist_ok=True)
    person_file = people_dir / f"{clean_name}.md"

    if person_file.exists():
        return person_file

    template = load_template("Person_Template.md")
    today_str = datetime.now().strftime("%d.%m.%y")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    if template:
        content = template.replace("{{title}}", clean_name)
    else:
        content = (
            f"---\ntype: person\n---\n\n# {clean_name}\n\n"
            f"- **Role/Title:** \n- **Company:** \n- **Met:** {datetime.now().strftime('%Y-%m-%d')}\n\n"
            f"### Relationships\n\n### Trivia & Info Dump\n\n### ATHENA Log\n"
        )

    if initial_trivia:
        trivia_lines = "\n".join([f"- [[{today_str}]]: {t}" for t in initial_trivia])
        log_lines = "\n".join([f"• **{timestamp} (Session Ingestion):** {t}" for t in initial_trivia])
        
        if "### Trivia & Info Dump" in content:
            content = content.replace("### Trivia & Info Dump", f"### Trivia & Info Dump\n{trivia_lines}")
        if "## ATHENA Log" in content:
            content = content.replace("## ATHENA Log", f"## ATHENA Log\n{log_lines}")
        elif "### ATHENA Log" in content:
            content = content.replace("### ATHENA Log", f"### ATHENA Log\n{log_lines}")

    person_file.write_text(content, encoding="utf-8")
    print(f"[Vault] 👤 Provisioned new contact note: {person_file.name}")

    if DB_PATH.exists():
        try:
            conn = sqlite3.connect(DB_PATH, timeout=10.0)
            cur = conn.cursor()
            cur.execute(
                "INSERT OR IGNORE INTO entities (id, type, folder, file_path) VALUES (?, 'person', 'People', ?);",
                (clean_name, f"People/{person_file.name}")
            )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[Vault DB Error] Could not register new person in entities: {e}")

    return person_file

def update_vault_note(file_path: Path, section_name: str, new_entry: str, bullet_style="- "):
    """Finds or creates any Markdown heading and inserts the entry cleanly beneath it."""
    if not file_path or not file_path.exists():
        return

    content = file_path.read_text(encoding="utf-8")
    if new_entry in content:
        return

    parts = re.split(r"(?m)^(#{1,6}\s+.*$|^\*\*[^*]+\*\*\s*$)", content)
    target_idx = None
    clean_target = section_name.lower().strip()

    for i, part in enumerate(parts):
        header_text = re.sub(r"[#*]", "", part).strip().lower()
        if header_text == clean_target:
            target_idx = i + 1
            break

    if target_idx is not None and target_idx < len(parts):
        parts[target_idx] = f"\n{bullet_style}{new_entry}" + parts[target_idx]
        file_path.write_text("".join(parts), encoding="utf-8")
    else:
        file_path.write_text(content.rstrip() + f"\n\n## {section_name}\n{bullet_style}{new_entry}\n", encoding="utf-8")

    print(f"[Vault] ✍️ Updated '{section_name}' in {file_path.name}")

def append_place_associated_person(place_file: Path, field_name: str, people_to_add: List[str]):
    """Appends people wikilinks to '- **<field_name>:**' in Place notes without duplicates."""
    if not place_file or not place_file.exists() or not people_to_add:
        return

    content = place_file.read_text(encoding="utf-8")
    pattern = rf"(?im)^([ \t]*[-*•]\s*\*\*{re.escape(field_name)}:\*\*\s*)(.*)$"
    match = re.search(pattern, content)

    valid_people = [p for p in people_to_add if not p.startswith("<")]
    if not valid_people:
        return

    clean_additions = [ensure_wikilinks(p) if not p.startswith("[[") else p for p in valid_people]

    if match:
        prefix = match.group(1)
        raw_current = match.group(2).strip()

        existing_items = [
            item.strip() 
            for item in raw_current.split(",") 
            if item.strip() and item.strip() not in {"[[ ]]", "[[]]"}
        ]
        existing_names = {re.sub(r"[\[\]]", "", item).strip().lower() for item in existing_items}

        added = False
        for person_link in clean_additions:
            name_clean = re.sub(r"[\[\]]", "", person_link).strip()
            if name_clean.lower() not in existing_names:
                existing_items.append(f"[[{name_clean}]]")
                existing_names.add(name_clean.lower())
                added = True

        if added:
            new_line = f"{prefix}{', '.join(existing_items)}"
            content = content[:match.start()] + new_line + content[match.end():]
            place_file.write_text(content, encoding="utf-8")
            print(f"[Vault] 👥 Updated '{field_name}' in {place_file.name}")
    else:
        field_str = ", ".join(clean_additions)
        update_vault_note(place_file, "Associated People", f"**{field_name}:** {field_str}")

def update_athena_log(summary: str, details: List[str]):
    """Appends a timestamped consolidation record to Brain/System/ATHENA Update Log.md."""
    log_dir = VAULT_DIR / "System"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "ATHENA Update Log.md"

    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    date_display = now.strftime("%d.%m.%y")

    entry_lines = [
        f"\n### [{timestamp}] Session Consolidation — [[{date_display}]]",
        f"- **Summary:** {summary}"
    ]
    if details:
        entry_lines.append("- **Key Updates:**")
        for d in details:
            entry_lines.append(f"  - {d}")

    if not log_file.exists():
        log_file.write_text("# ATHENA System Update Log\n\nAutomated post-session knowledge graph consolidation ledger.\n", encoding="utf-8")

    current_log = log_file.read_text(encoding="utf-8")
    log_file.write_text(current_log.rstrip() + "\n" + "\n".join(entry_lines) + "\n", encoding="utf-8")
    print("[Vault] 📜 Master ATHENA Update Log updated.")

def apply_deconstructed_turn(data: Dict[str, Any]):
    """
    Applies an atomically deconstructed turn into SQLite and Obsidian vault files.
    Used by multi_stage_processor.py to persist clean facts, places, orgs, and loops.
    """
    if not isinstance(data, dict):
        return

    today_str = datetime.now().strftime("%d.%m.%y")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    people_dir = VAULT_DIR / "People"
    places_dir = VAULT_DIR / "Places"
    people_dir.mkdir(parents=True, exist_ok=True)
    places_dir.mkdir(parents=True, exist_ok=True)

    # 1. Deterministically resolve Elliot's note
    elliot_file = get_elliot_note(people_dir)

    conn = sqlite3.connect(DB_PATH, timeout=10.0) if DB_PATH.exists() else None
    cur = conn.cursor() if conn else None

    # 2. Places Visited & Contextual Activities
    for pl in data.get("places_visited", []):
        raw_venue = pl.get("venue", "").strip()
        visitors = pl.get("visitors", [])
        activity_notes = pl.get("activity_notes", "").strip()

        if not raw_venue or raw_venue.startswith("<"):
            continue

        place_name = resolve_canonical_name(places_dir, raw_venue)
        place_file = find_file_case_insensitive(places_dir, place_name)

        clean_visitors = [
            resolve_canonical_name(people_dir, v) for v in visitors
            if v and v.lower() not in {"elliot", "elliot waigh", "i", "me"} and not v.startswith("<")
        ]

        if not place_file.exists():
            template = load_template("Place_Template.md")
            comp_str = ", ".join([f"[[{v}]]" for v in clean_visitors]) if clean_visitors else "[[Elliot Waigh]]"
            if template:
                content = template.replace("{{title}}", place_name)
                content = content.replace("- **Visited with:** [[ ]]", f"- **Visited with:** {comp_str}")
            else:
                content = (
                    f"---\ntype: place\ncity: Brisbane\ntags:\n  - place\n---\n\n"
                    f"# {place_name}\n\n### Associated People\n"
                    f"- **Favorites of:** [[ ]]\n"
                    f"- **Recommended by:** [[ ]]\n"
                    f"- **Visited with:** {comp_str}\n\n"
                    f"### Notes & Trivia\n"
                )
            place_file.write_text(content, encoding="utf-8")
            print(f"[Vault] 📝 Created place note: {place_file.name}")

        # Ensure Elliot and companions are recorded in 'Visited with'
        all_visitors = ["Elliot Waigh"] + clean_visitors
        append_place_associated_person(place_file, "Visited with", all_visitors)

        # Write rich activity note in the Place's note
        companion_links = ", ".join([f"[[{v}]]" for v in clean_visitors])
        if companion_links:
            base_desc = f"Visited with {companion_links}"
        else:
            base_desc = "Visited by [[Elliot Waigh]]"

        full_place_entry = f"{base_desc} — {activity_notes}" if activity_notes else base_desc
        update_vault_note(place_file, "Notes & Trivia", f"[[{today_str}]]: {full_place_entry}")

        # Update Elliot's personal note with explicit [[Place]] wikilinks
        if elliot_file and elliot_file.exists():
            elliot_visit_entry = f"Visited [[{place_name}]]: {activity_notes}" if activity_notes else f"Visited [[{place_name}]]"
            if companion_links:
                elliot_visit_entry += f" with {companion_links}"
            update_vault_note(elliot_file, "Trivia & Info Dump", f"[[{today_str}]]: {elliot_visit_entry}")
            update_vault_note(elliot_file, "ATHENA Log", f"**{timestamp} (Session Ingestion):** {elliot_visit_entry}", bullet_style="• ")

        if cur:
            cur.execute(
                "INSERT OR IGNORE INTO entities (id, type, folder, file_path) VALUES (?, 'place', 'Places', ?);",
                (place_name, f"Places/{place_file.name}")
            )
            for v in all_visitors:
                cur.execute(
                    "INSERT OR REPLACE INTO triples (subject, predicate, object, source_file) VALUES (?, 'visited', ?, ?);",
                    (v, place_name, f"Places/{place_file.name}")
                )

    # 3. Recommendations
    for rec in data.get("recommendations", []):
        v = rec.get("venue", "").strip()
        src = rec.get("source_person", "").strip()
        note = rec.get("note", "").strip()
        if not v or v.startswith("<"):
            continue

        place_name = resolve_canonical_name(places_dir, v)
        place_file = find_file_case_insensitive(places_dir, place_name)
        canonical_src = resolve_canonical_name(people_dir, src) if src and not src.startswith("<") else None
        src_link = f"[[{canonical_src}]]" if canonical_src and canonical_src.lower() not in {"she", "he", "they"} else src

        if place_file.exists():
            rec_line = f"[[{today_str}]]: Recommended by {src_link}: {note}" if src_link else f"[[{today_str}]]: {note}"
            update_vault_note(place_file, "Notes & Trivia", rec_line)
            if canonical_src and canonical_src.lower() not in {"she", "he", "they"}:
                append_place_associated_person(place_file, "Recommended by", [canonical_src])

        if cur and canonical_src and canonical_src.lower() not in {"she", "he", "they"}:
            cur.execute(
                "INSERT OR REPLACE INTO triples (subject, predicate, object, source_file) VALUES (?, 'recommends', ?, ?);",
                (canonical_src, place_name, f"Places/{place_file.name}")
            )

    # 4. People Mentions & Durable Facts (Filtered from Banter)
    for m in data.get("people_mentions", []):
        raw_name = m.get("name", "").strip()
        fact = m.get("fact", "").strip()
        if not raw_name or not fact or raw_name.startswith("<") or raw_name.lower() in GENERIC_BANNED_ENTITIES:
            continue

        canonical_name = resolve_canonical_name(people_dir, raw_name)
        formatted_fact = ensure_wikilinks(fact)

        if canonical_name.lower() in {"elliot", "elliot waigh"}:
            if elliot_file and elliot_file.exists():
                update_vault_note(elliot_file, "Trivia & Info Dump", f"[[{today_str}]]: {formatted_fact}")
                update_vault_note(elliot_file, "ATHENA Log", f"**{timestamp} (Session Ingestion):** {formatted_fact}", bullet_style="• ")
            continue

        person_file = find_file_case_insensitive(people_dir, canonical_name)
        if not person_file.exists():
            person_file = provision_new_person(canonical_name)

        if person_file:
            update_vault_note(person_file, "Trivia & Info Dump", f"[[{today_str}]]: {formatted_fact}")
            update_vault_note(person_file, "ATHENA Log", f"**{timestamp} (Session Ingestion):** {formatted_fact}", bullet_style="• ")

    # 5. Organization Updates
    for o in data.get("organization_updates", []):
        raw_p = o.get("person", "").strip()
        org = o.get("organization", "").strip()
        status = o.get("status", "works_at").strip().lower().replace(" ", "_")
        if not raw_p or not org or raw_p.startswith("<") or org.startswith("<"):
            continue

        canonical_person = resolve_canonical_name(people_dir, raw_p)
        person_file = find_file_case_insensitive(people_dir, canonical_person)
        if not person_file.exists():
            person_file = provision_new_person(canonical_person)

        if person_file:
            org_note = f"{status.replace('_', ' ').capitalize()} [[{org}]]"
            update_vault_note(person_file, "Trivia & Info Dump", f"[[{today_str}]]: {org_note}")
            update_vault_note(person_file, "ATHENA Log", f"**{timestamp} (Session Ingestion):** {org_note}", bullet_style="• ")

        if cur:
            cur.execute(
                "INSERT OR REPLACE INTO triples (subject, predicate, object, source_file) VALUES (?, ?, ?, ?);",
                (canonical_person, status, org, f"People/{person_file.name if person_file else canonical_person + '.md'}")
            )

    if conn:
        conn.commit()
        conn.close()

    # 6. Loops
    try:
        from .loop_manager import sync_loops_to_storage
        sync_loops_to_storage(data.get("open_loops", []), data.get("closed_loops", []))
    except Exception as e:
        print(f"[Loop Ingestion Error] {e}")

def consolidate_session(transcript: str):
    """Legacy session-level consolidator preserved for backward compatibility."""
    if len(transcript.strip()) < 15:
        print("[Brain Consolidation] Session transcript empty or too brief.")
        return

    people_dir = VAULT_DIR / "People"
    places_dir = VAULT_DIR / "Places"
    people_dir.mkdir(parents=True, exist_ok=True)
    places_dir.mkdir(parents=True, exist_ok=True)

    print("\n[Brain Consolidation] Analyzing session with 7B engine...")
    prompt = EXTRACTION_PROMPT.replace("{transcript}", transcript)
    try:
        res = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL_NAME,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.0}
            },
            timeout=90
        )
        if res.status_code != 200:
            print(f"[Consolidation Error] Ollama HTTP {res.status_code}")
            return

        payload = sanitize_extracted_payload(json.loads(res.json().get("response", "{}")), transcript, people_dir, places_dir)
    except Exception as e:
        print(f"[Consolidation Exception] {e}")
        return

    places = payload.get("new_places", [])
    place_names = [pl.get("name") for pl in places if pl.get("name")]

    people = payload.get("people_updates", [])
    people_names = [p.get("name") for p in people if p.get("name")]
    summary = ensure_wikilinks(payload.get("episodic_summary", ""), people_names, place_names)
    triples = payload.get("triples", [])
    loops = payload.get("open_loops", [])

    has_meaningful_data = bool(places or any(p.get("trivia") or p.get("visited_place") for p in people) or triples or loops)
    if not has_meaningful_data and not summary:
        print("[Brain Consolidation] No new factual updates extracted. Skipping vault write.")
        return

    print("\n" + "=" * 65)
    print(" 🧠 ATHENA CONSOLIDATION REPORT")
    print("=" * 65)
    
    if summary:
        print(f"\n📌 Episodic Summary:\n   {summary}")

    if places:
        print(f"\n📍 Places Ingested:")
        for pl in places:
            print(f"   • [{pl.get('category', 'place')}] {pl.get('name')}")

    if people:
        print(f"\n👤 People & Trivia Updates:")
        for p in people:
            if p.get("trivia") or p.get("visited_place"):
                print(f"   • {p.get('name')}:")
                for t in p.get("trivia", []):
                    print(f"     - {ensure_wikilinks(t, people_names, place_names)}")

    if triples:
        print(f"\n🔗 Relationships & Triples:")
        for t in triples:
            print(f"   • {t.get('subject')} --[{t.get('predicate')}]--> {t.get('object')}")

    if loops:
        print(f"\n⏳ Commitments & Open Loops:")
        for l in loops:
            print(f"   • [{l.get('direction').upper()}] {l.get('target')}: {l.get('commitment')}")
    else:
        print(f"\n⏳ Commitments & Open Loops:\n   (None - no promises detected)")

    print("=" * 65 + "\n")

    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    cur = conn.cursor()
    today_str = datetime.now().strftime("%d.%m.%y")
    log_details = []

    # 1. Places
    for pl in places:
        place_name = pl.get("name", "").strip()
        category = pl.get("category", "spot").strip()
        if not place_name or place_name.startswith("<"):
            continue

        place_file = find_file_case_insensitive(places_dir, place_name)
        
        actual_companions = [
            p.get("name") for p in people 
            if p.get("visited_place") and p.get("visited_place").lower() == place_name.lower()
            and p.get("name", "").lower() not in {"elliot", "elliot waigh"} and not p.get("name", "").startswith("<")
        ]
        companion_links = [f"[[{name}]]" for name in actual_companions]
        companions_str = ", ".join(companion_links) if companion_links else "[[ ]]"

        recommenders = [ensure_wikilinks(r, people_names, place_names) for r in pl.get("recommended_by", []) if not r.startswith("<")]
        recommenders_str = ", ".join(recommenders) if recommenders else "[[ ]]"

        if not place_file.exists():
            template = load_template("Place_Template.md")
            if template:
                content = template.replace("{{title}}", place_name)
                content = content.replace("- **Category:**", f"- **Category:** {category}")
                content = content.replace("- **Visited with:** [[ ]]", f"- **Visited with:** {companions_str}")
                content = content.replace("- **Recommended by:** [[ ]]", f"- **Recommended by:** {recommenders_str}")
            else:
                content = (
                    f"---\ntype: place\ncategory: {category}\ncity: Brisbane\ntags:\n  - place\n---\n\n"
                    f"# {place_name}\n\n### Associated People\n"
                    f"- **Favorites of:** [[ ]]\n"
                    f"- **Recommended by:** {recommenders_str}\n"
                    f"- **Visited with:** {companions_str}\n\n"
                    f"### Notes & Trivia\n"
                )
            place_file.write_text(content, encoding="utf-8")
            print(f"[Vault] 📝 Created place note: {place_file.name}")
            log_details.append(f"Created Place: [[{place_file.stem}]]")

        if actual_companions:
            append_place_associated_person(place_file, "Visited with", actual_companions)
        if recommenders:
            append_place_associated_person(place_file, "Recommended by", recommenders)

        if summary:
            update_vault_note(place_file, "Notes & Trivia", f"[[{today_str}]]: {summary}")

        cur.execute(
            "INSERT OR IGNORE INTO entities (id, type, folder, file_path) VALUES (?, 'place', 'Places', ?);",
            (place_name, f"Places/{place_file.name}")
        )

    # 2. External People
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    external_contacts = [p for p in people if p.get("name", "").lower() not in {"elliot", "elliot waigh"} and not p.get("name", "").startswith("<")]

    for p in external_contacts:
        name = p["name"]
        person_file = find_file_case_insensitive(people_dir, name)

        if not person_file.exists():
            person_file = provision_new_person(name)
            if person_file:
                log_details.append(f"Created Person: [[{person_file.stem}]]")

        if not person_file:
            continue

        v_place = p.get("visited_place")
        if v_place:
            encounter_note = f"[[{today_str}]]: Caught up with [[Elliot Waigh]] at [[{v_place}]]"
            update_vault_note(person_file, "Trivia & Info Dump", encounter_note)
            update_vault_note(person_file, "ATHENA Log", f"**{timestamp} (Session Ingestion):** Visited [[{v_place}]] with [[Elliot Waigh]]", bullet_style="• ")

        for trivia in p.get("trivia", []):
            clean_trivia_lower = trivia.lower()
            if clean_trivia_lower.startswith("visited ") or "went to " in clean_trivia_lower:
                if any(pl_name.lower() in clean_trivia_lower for pl_name in place_names):
                    continue

            formatted_trivia = ensure_wikilinks(trivia, people_names, place_names)
            update_vault_note(person_file, "Trivia & Info Dump", f"[[{today_str}]]: {formatted_trivia}")
            log_details.append(f"[[{person_file.stem}]] Trivia: {formatted_trivia}")
            update_vault_note(person_file, "ATHENA Log", f"**{timestamp} (Session Ingestion):** {formatted_trivia}", bullet_style="• ")

    # 3. Personal Note (Elliot Waigh / Elliot)
    elliot_file = get_elliot_note(people_dir)

    if elliot_file.exists():
        visited_places_this_run = set()
        for pl in places:
            p_name = pl.get("name", "").strip()
            if not p_name or p_name.startswith("<"):
                continue

            visited_places_this_run.add(p_name.lower())
            companions = [
                p.get("name") for p in external_contacts 
                if p.get("visited_place") and p.get("visited_place").lower() == p_name.lower()
            ]

            if companions:
                comp_str = ", ".join([f"[[{c}]]" for c in companions])
                visit_note = f"[[{today_str}]]: Caught up with {comp_str} at [[{p_name}]]"
            else:
                visit_note = f"[[{today_str}]]: Visited [[{p_name}]]"

            update_vault_note(elliot_file, "Trivia & Info Dump", visit_note)
            update_vault_note(elliot_file, "ATHENA Log", f"**{timestamp} (Session Ingestion):** {visit_note.replace(f'[[{today_str}]]: ', '')}", bullet_style="• ")

        for p in people:
            if p.get("name", "").lower() in {"elliot", "elliot waigh"}:
                for trivia in p.get("trivia", []):
                    clean_trivia_lower = trivia.lower()
                    if clean_trivia_lower.startswith("visited ") or "went to " in clean_trivia_lower:
                        if any(vp in clean_trivia_lower for vp in visited_places_this_run):
                            continue

                    formatted_trivia = ensure_wikilinks(trivia, people_names, place_names)
                    update_vault_note(elliot_file, "Trivia & Info Dump", f"[[{today_str}]]: {formatted_trivia}")
                    update_vault_note(elliot_file, "ATHENA Log", f"**{timestamp} (Session Ingestion):** {formatted_trivia}", bullet_style="• ")

    # 4. Triples
    for trip in triples:
        sub, pred, obj = trip["subject"], trip["predicate"], trip["object"]
        cur.execute("INSERT OR IGNORE INTO triples (subject, predicate, object, source_file) VALUES (?, ?, ?, 'chat_session');", (sub, pred, obj))

    # 5. Commitments
    for loop in loops:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS open_loops (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target TEXT NOT NULL,
                commitment TEXT NOT NULL,
                direction TEXT NOT NULL,
                status TEXT DEFAULT 'open',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(target, commitment)
            );
        """)
        cur.execute(
            "INSERT OR IGNORE INTO open_loops (target, commitment, direction) VALUES (?, ?, ?);",
            (loop["target"], loop["commitment"], loop["direction"])
        )
        log_details.append(f"Commitment [{loop['direction']}]: [[{loop['target']}]] -> {loop['commitment']}")

    conn.commit()
    conn.close()

    # 6. ATHENA System Log
    if summary or log_details:
        update_athena_log(summary, log_details)

    print("[✓] Obsidian notes, personal ATHENA logs, SQLite graph, and system log updated cleanly.")