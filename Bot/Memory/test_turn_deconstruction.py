import json
import re
import sqlite3
from pathlib import Path
from typing import Dict, Any, List
import requests

SCRIPT_DIR = Path(__file__).resolve().parent
DB_PATH = SCRIPT_DIR / "athena.db"

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen2.5:7b"

GENERIC_VENUES = {
    "coffee shop", "cafe", "bar", "pub", "restaurant", "brewery", 
    "the place", "somewhere", "home", "work", "office", "omitted", 
    "none", "null", "hospital", "gym", "airport", "not specified"
}

USER_TOKENS = {
    "i", "me", "my", "myself", "narrator", "the user", "elliot", 
    "elliot waigh", "the speaker", "we", "us"
}

GENERIC_PRONOUNS = {
    "he", "she", "they", "him", "her", "them", "someone", "guy", 
    "mate", "omitted", "none", "null"
}

LOOP_TRIGGER_REGEX = re.compile(
    r"\b(promise|promised|promising|owe|owed|owes|lent|lend|borrow|borrowed|"
    r"give back|gave back|giving back|return|returned|returning|"
    r"transfer|transferred|send|sending|sent|drop off|dropped off|"
    r"bring|bringing|brought|pay back|paid back|repay|repaid)\b",
    re.IGNORECASE
)

# -------------------------------------------------------------------------
# 1. DATABASE STATE INTROSPECTION
# -------------------------------------------------------------------------
def dump_database_state() -> Dict[str, Any]:
    if not DB_PATH.exists():
        return {"entities": [], "properties": [], "triples": [], "open_loops": []}

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, type, folder, file_path FROM entities;")
    entities = cur.fetchall()
    cur.execute("SELECT entity_id, key, value FROM properties;")
    properties = cur.fetchall()
    cur.execute("SELECT subject, predicate, object, source_file FROM triples;")
    triples = cur.fetchall()

    try:
        cur.execute("SELECT id, target, commitment, direction, status FROM open_loops;")
        open_loops = cur.fetchall()
    except sqlite3.OperationalError:
        open_loops = []

    conn.close()
    return {
        "entities": entities,
        "properties": properties,
        "triples": triples,
        "open_loops": open_loops
    }

# -------------------------------------------------------------------------
# 2. MICRO-PROMPT 1: PURE ENTITY & FACT EXTRACTION
# -------------------------------------------------------------------------
ENTITY_MICRO_PROMPT = """You are a precise factual linguistic extractor.
Extract visited venues, recommendations, human contacts, and organizations from the text.

RULES:
1. ONLY extract external people in 'people_mentions'. Never include Elliot or 'I'.
2. If a pronoun like 'he' or 'she' clearly refers to the only person mentioned, assign the fact to that person's name directly.
3. Only put 'unresolved_pronouns' if 'he'/'she'/'they' is genuinely ambiguous between multiple people.
4. Only include named physical venues in 'places_visited'. Omit generic venues ('bar', 'coffee shop').
5. Never list an item loan, errand, or meeting as a recommendation.

INPUT:
\"\"\"{input_text}\"\"\"

Output strictly valid JSON:
{
  "places_visited": [
    {
      "venue": "<Named venue>",
      "visitors": ["<Person name>"]
    }
  ],
  "recommendations": [
    {
      "venue": "<Venue name>",
      "source_person": "<Person name or pronoun>",
      "note": "<Note>"
    }
  ],
  "people_mentions": [
    {
      "name": "<Person name>",
      "fact": "<Atomic factual assertion about this person>"
    }
  ],
  "unresolved_pronouns": ["<he|she|they>"],
  "organization_updates": [
    {
      "person": "<Person name>",
      "organization": "<Company/Employer/Venue>",
      "status": "<works_at|transferred_to|transferred_from|visited>"
    }
  ]
}"""

# -------------------------------------------------------------------------
# 3. MICRO-PROMPT 2: ISOLATED LOOP & COMMITMENT PARSER
# -------------------------------------------------------------------------
LOOP_MICRO_PROMPT = """You are an interpersonal commitment parser.
Extract loans, debts, borrowed items, and promises between Elliot (the user) and another person.

CRITICAL RULES:
1. BORROWING/LOANS:
   - If someone lent Elliot an item, or Elliot borrowed an item -> open_loop (direction: 'i_owe_them', commitment: 'return <item>').
   - If Elliot lent someone an item -> open_loop (direction: 'they_owe_me', commitment: 'return <item>').
2. PROMISES:
   - If the OTHER PERSON promised/agreed to send or do something -> open_loop (direction: 'they_owe_me').
   - If ELLIOT promised/agreed to send or do something -> open_loop (direction: 'i_owe_them').
3. SETTLEMENTS (CLOSED LOOPS):
   - Items or money explicitly returned, paid back, or settled in the past tense (e.g., 'gave him back his camera', 'he transferred the $50').
   - IMPORTANT: If MULTIPLE items or debts were settled in the sentence, list EACH one as a separate entry in 'closed_loops'.
   - Do NOT mark an item as an open loop if it was already settled in this statement.
4. EXCLUSIONS:
   - Private personal departures ('pick up car', 'head home') are NOT commitments.

INPUT:
\"\"\"{input_text}\"\"\"

Output strictly valid JSON:
{
  "open_loops": [
    {
      "target": "<External contact name>",
      "commitment": "<Action or item owed/promised/borrowed>",
      "direction": "i_owe_them|they_owe_me"
    }
  ],
  "closed_loops": [
    {
      "target": "<External contact name>",
      "settled_item": "<Settled item or money>"
    }
  ]
}"""

def call_ollama(prompt: str) -> Dict[str, Any]:
    try:
        res = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL_NAME,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.0, "top_p": 0.1}
            },
            timeout=40
        )
        if res.status_code == 200:
            return json.loads(res.json().get("response", "{}"))
    except Exception as e:
        print(f"[!] Ollama Call Error: {e}")
    return {}

# -------------------------------------------------------------------------
# 4. DECONSTRUCTION PIPELINE
# -------------------------------------------------------------------------
def deconstruct_turn(statement: str) -> Dict[str, Any]:
    # Micro-Pass 1: Entities & Venues
    entity_result = call_ollama(ENTITY_MICRO_PROMPT.replace("{input_text}", statement))

    # Sanitize places
    valid_places = []
    for pl in entity_result.get("places_visited", []):
        v = pl.get("venue", "").strip()
        if v and v.lower() not in GENERIC_VENUES:
            valid_visitors = [
                vis for vis in pl.get("visitors", []) 
                if vis.lower() not in USER_TOKENS and vis.lower() not in GENERIC_PRONOUNS
            ]
            pl["visitors"] = valid_visitors
            valid_places.append(pl)
    entity_result["places_visited"] = valid_places

    # Sanitize recommendations
    valid_recs = []
    for r in entity_result.get("recommendations", []):
        v = r.get("venue", "").strip()
        note = r.get("note", "").lower()
        if v and v.lower() not in GENERIC_VENUES:
            if not any(tok in note for tok in ["lent", "borrowed", "camera", "gimbal", "trip", "lunch", "coffee"]):
                valid_recs.append(r)
    entity_result["recommendations"] = valid_recs

    # Sanitize mentions
    clean_mentions = []
    for m in entity_result.get("people_mentions", []):
        name = m.get("name", "").strip()
        name_lower = name.lower()
        if any(tok in name_lower for tok in ["the person who", "speaker", "narrator", "user", "myself"]):
            continue
        if name_lower in USER_TOKENS or name_lower in GENERIC_PRONOUNS:
            continue
        clean_mentions.append(m)
    entity_result["people_mentions"] = clean_mentions

    # Sanitize orgs
    clean_orgs = []
    for o in entity_result.get("organization_updates", []):
        p = o.get("person", "").strip()
        org = o.get("organization", "").strip()
        if p.lower() in USER_TOKENS or org.lower() in GENERIC_VENUES or not org:
            continue
        clean_orgs.append(o)
    entity_result["organization_updates"] = clean_orgs

    known_named = [m.get("name") for m in clean_mentions if m.get("name")]
    fallback_target = known_named[0] if len(known_named) == 1 else None

    # Micro-Pass 2: Loops (Conditional)
    open_loops = []
    closed_loops = []

    if LOOP_TRIGGER_REGEX.search(statement):
        loop_result = call_ollama(LOOP_MICRO_PROMPT.replace("{input_text}", statement))
        raw_lower = statement.lower()

        for ol in loop_result.get("open_loops", []):
            target = ol.get("target", "").strip()
            commit = ol.get("commitment", "").strip()

            if target.lower() in GENERIC_PRONOUNS and fallback_target:
                target = fallback_target
                ol["target"] = target

            if not target or target.lower() in USER_TOKENS or target.lower() in GENERIC_PRONOUNS:
                continue
            if any(err in commit.lower() for err in ["pick up car", "go to gym", "head home", "take off", "leave early"]):
                continue

            # Deterministic Direction Anchor
            # If external person promised -> they_owe_me
            target_first = target.split()[0].lower()
            if f"{target_first} promised" in raw_lower or "he promised" in raw_lower or "she promised" in raw_lower:
                ol["direction"] = "they_owe_me"
            elif "i promised" in raw_lower or "i'd drop" in raw_lower or "i will" in raw_lower:
                ol["direction"] = "i_owe_them"

            open_loops.append(ol)

        for cl in loop_result.get("closed_loops", []):
            target = cl.get("target", "").strip()
            item = cl.get("settled_item", "").strip()

            if target.lower() in GENERIC_PRONOUNS and fallback_target:
                target = fallback_target
                cl["target"] = target

            if target and item and target.lower() not in USER_TOKENS and target.lower() not in GENERIC_VENUES:
                closed_loops.append(cl)

    entity_result["open_loops"] = open_loops
    entity_result["closed_loops"] = closed_loops
    return entity_result

# -------------------------------------------------------------------------
# 5. DETERMINISTIC CLARIFICATION EVALUATOR
# -------------------------------------------------------------------------
def evaluate_clarification_rules(parsed_payload: Dict[str, Any], known_people: List[str]) -> List[str]:
    clarifications = []
    
    # Collect all candidate distinct names
    all_names = [m.get("name") for m in parsed_payload.get("people_mentions", []) if m.get("name")]
    for loop in parsed_payload.get("open_loops", []) + parsed_payload.get("closed_loops", []):
        t = loop.get("target")
        if t and t.lower() not in USER_TOKENS and t.lower() not in GENERIC_PRONOUNS:
            all_names.append(t)

    distinct_names = list(dict.fromkeys(all_names))
    unknown_contacts = []

    # 1. Deterministic Name Collision Check (Against SQLite)
    for raw_name in distinct_names:
        parts = raw_name.split()
        if len(parts) == 1:
            first_name = parts[0].lower()
            matches = [p for p in known_people if p.split()[0].lower() == first_name]
            if len(matches) > 1:
                opts = " or ".join(matches)
                clarifications.append(f"got multiple hits for '{raw_name}' ({opts}). Which one did you mean, or is this someone new?")
            elif len(matches) == 0:
                unknown_contacts.append(raw_name)

    # 2. Only check unresolved pronouns if MULTIPLE people could be referred to
    unresolved_pronouns = parsed_payload.get("unresolved_pronouns", [])
    for r in parsed_payload.get("recommendations", []):
        src = r.get("source_person", "").strip().lower()
        if src in GENERIC_PRONOUNS and src not in unresolved_pronouns:
            unresolved_pronouns.append(src)

    if unresolved_pronouns and len(distinct_names) > 1:
        candidates = " or ".join(distinct_names)
        for pron in unresolved_pronouns:
            clarifications.append(f"who did you mean by '{pron}'—was that {candidates}?")

    # 3. Unknown Contacts
    if unknown_contacts:
        deduped = list(dict.fromkeys(unknown_contacts))
        if len(deduped) == 1:
            clarifications.append(f"{deduped[0]} isn't in your records yet. Should I spin up a new note for them?")
        elif len(deduped) == 2:
            clarifications.append(f"{deduped[0]} and {deduped[1]} aren't in your records yet. Should I spin up new notes for them?")
        else:
            names_str = ", ".join(deduped[:-1]) + f", and {deduped[-1]}"
            clarifications.append(f"{names_str} aren't in your records yet. Should I spin up new notes for them?")

    return list(dict.fromkeys(clarifications))

def format_athena_clarification(clarifications: List[str]) -> str:
    if not clarifications:
        return ""
    if len(clarifications) == 1:
        return f"ATHENA: Hold up Boss, {clarifications[0]}"
    return "ATHENA: Quick check Boss—" + " Also, ".join(clarifications)

# -------------------------------------------------------------------------
# 6. TEST RUNNER
# -------------------------------------------------------------------------
def run_single_test(test_num: int, title: str, statement: str, known_people: List[str]):
    print("\n" + "=" * 80)
    print(f" 🧪 TEST {test_num}: {title}")
    print("=" * 80)
    print(f"INPUT STATEMENT:\n\"{statement}\"")
    print("-" * 80)

    result = deconstruct_turn(statement)
    print("[Raw Output]")
    print(json.dumps(result, indent=2))

    clarifications = evaluate_clarification_rules(result, known_people)

    print("\n[Parsed Structural Breakdown]")
    places = result.get("places_visited", [])
    if places:
        print("• Places Visited:")
        for pl in places:
            print(f"  - {pl.get('venue')} (Visitors: {', '.join(pl.get('visitors', []))})")
    else:
        print("• Places Visited: None")

    recs = result.get("recommendations", [])
    if recs:
        print("• Recommendations:")
        for r in recs:
            print(f"  - {r.get('venue')} (Source: {r.get('source_person')}) -> {r.get('note')}")
    else:
        print("• Recommendations: None")

    mentions = result.get("people_mentions", [])
    if mentions:
        print("• People Mentions:")
        for m in mentions:
            print(f"  - [{m.get('name')}]: {m.get('fact')}")

    orgs = result.get("organization_updates", [])
    if orgs:
        print("• Organization Updates:")
        for o in orgs:
            print(f"  - [{o.get('person')}] -> {o.get('organization')} ({o.get('status')})")
    else:
        print("• Organization Updates: None")

    open_l = result.get("open_loops", [])
    if open_l:
        print("• ⏳ Open Loops (Active Commitments):")
        for ol in open_l:
            print(f"  - [{ol.get('direction').upper()}] Target: {ol.get('target')} | Commitment: {ol.get('commitment')}")
    else:
        print("• ⏳ Open Loops: None detected")

    closed_l = result.get("closed_loops", [])
    if closed_l:
        print("• ✅ Closed Loops (Settled / Returned):")
        for cl in closed_l:
            print(f"  - Target: {cl.get('target')} | Settled: {cl.get('settled_item')}")
    else:
        print("• ✅ Closed Loops: None detected")

    print("\n[Clarification Check]")
    if clarifications:
        print(f"  ⚠️  {format_athena_clarification(clarifications)}")
    else:
        print("  ✓ Clean pass. Ready for deterministic storage.")

def run_suite():
    print("=" * 80)
    print(" 🛠️ RUNNING TURNS DECONSTRUCTION & MULTI-LOOP TEST SUITE")
    print("=" * 80)

    db_state = dump_database_state()
    known_people = [e[0] for e in db_state["entities"] if e[1] == "person" or e[2] == "People"]

    print(f"[DB Extraction Summary]")
    print(f"• Known People ({len(known_people)}): {known_people[:6]}...")

    test_cases = [
        (
            "Multi-Hop Venue Transition + Inbound Item Loan (Open Loop Creation)",
            "Kicked off the afternoon grabbing lunch with Dylan at Felons Brewing Co. where he lent me his Insta360 camera for my trip, then we walked over to Riverland to catch up with Josh."
        ),
        (
            "Settling Old Debt & Returning Item (Closed Loops) + Forward Promise (Open Loop)",
            "Caught up with Dylan at Newmarket Hotel and gave him back his Insta360 camera, plus he transferred me the $50 for concert tickets, but I promised I'd design his portfolio wireframes by Sunday."
        ),
        (
            "Passive Venue Recommendations + Ambiguous Pronoun Disambiguation",
            "Had coffee with Amelia and Sarah. She told me we have to try Agnes Bakery for morning pastries, while Sarah mentioned she accepted an offer at Canva."
        ),
        (
            "Novel Contact Provisioning + External Promise Direction + Company Mapping",
            "Met up with Toby at Alligator Bar. He just got hired as lead engineer at Flight Centre, and he promised he would send over the system architecture diagram tomorrow."
        )
    ]

    for i, (title, statement) in enumerate(test_cases, start=1):
        run_single_test(i, title, statement, known_people)

if __name__ == "__main__":
    run_suite()