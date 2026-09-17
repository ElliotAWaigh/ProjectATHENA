import json
import re
from typing import Dict, Any, List
import requests

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen2.5:7b"

GENERIC_VENUES = {
    "coffee shop", "cafe", "bar", "pub", "restaurant", "brewery", 
    "the place", "somewhere", "home", "work", "office", "omitted", 
    "none", "null", "hospital", "gym", "airport", "not specified",
    "<venue name>", "<named venue>"
}

USER_TOKENS = {
    "i", "me", "my", "myself", "narrator", "the user", "elliot", 
    "elliot waigh", "the speaker", "we", "us"
}

GENERIC_PRONOUNS = {
    "he", "she", "they", "him", "her", "them", "someone", "guy", 
    "mate", "omitted", "none", "null"
}

PLACEHOLDER_TOKENS = {
    "<person name>", "<name>", "<person>", "person name", "unknown", 
    "omitted", "none", "null", "n/a", "<venue name>", "<named venue>"
}

LOOP_TRIGGER_REGEX = re.compile(
    r"\b(promise|promised|promising|owe|owed|owes|lent|lend|borrow|borrowed|"
    r"give back|gave back|giving back|return|returned|returning|"
    r"transfer|transferred|send|sending|sent|drop off|dropped off|"
    r"bring|bringing|brought|pay back|paid back|repay|repaid)\b",
    re.IGNORECASE
)

# -------------------------------------------------------------------------
# 1. INTENT & CLARIFICATION MICRO-PROMPTS
# -------------------------------------------------------------------------
ROUTER_PROMPT = """Classify the user's input into EXACTLY ONE label:
- CHITCHAT: Greetings, banter, jokes, immediate conversation recall, callbacks to what was JUST said in this chat ("hey boss", "what was I talking about", "what did I say I wanted for dinner", "how are you").
- COMMAND: Action commands, device controls, playback, smart home ("turn off the lights", "play music", "open spotify", "mute").
- KNOWLEDGE_QUERY: Inquiries searching historical notes, vault records, past events, people, places in long-term memory ("who is Dylan", "tell me about Felons", "where did we go last month", "what is my dog's name").
- MEMORY_DEBRIEF: Factual statements recounting events, day logs, places visited, solo activities, or promises made ("im at mt gravatt lookout", "Met Toby at Felons", "Dylan lent me his camera").

INPUT: \"\"\"{input_text}\"\"\"

Output strictly JSON:
{
  "intent": "CHITCHAT"|"COMMAND"|"KNOWLEDGE_QUERY"|"MEMORY_DEBRIEF"
}"""

RESOLUTION_PROMPT = """Evaluate the user's response to an ATHENA clarification request.

ATHENA'S QUESTION WAS ABOUT:
- Ambiguous names: {ambiguous_names}
- Novel contacts: {unknown_contacts}

USER REPLY: \"\"\"{input_text}\"\"\"

Determine:
1. "decision":
   - "REJECT": User said no, told not to do it, changed subject, declined, or cancelled ("no", "dont do that", "nah leave it", "cancel", "neither", "forget it", "hell no").
   - "AFFIRM": User confirmed or approved spinning up/recording ("yes", "yeah", "spin it up", "sure", "go for it", "please do").
   - "SPECIFY": User chose or clarified one of the ambiguous options.
2. "selected_name": The exact option the user chose if SPECIFY, or null.

Output strictly JSON:
{
  "decision": "REJECT"|"AFFIRM"|"SPECIFY",
  "selected_name": "<name or null>"
}"""

# -------------------------------------------------------------------------
# 2. ENTITY & VENUE MICRO-PROMPT
# -------------------------------------------------------------------------
ENTITY_MICRO_PROMPT = """You are a precise factual linguistic extractor for a personal knowledge graph.
Extract physical venues visited, descriptions of what happened there, recommendations, and durable biographical facts.

CRITICAL RULES:
1. PLACES VISITED:
   - Extract real named venues/locations (e.g. "Mt Gravatt Lookout", "Felons Brewing Co.").
   - In 'activity_notes', write a concise description of what the person did, experienced, observed, or felt about the place (e.g. "Spent 3 hours here; beautiful spot for photos and walks").
2. DURABLE FACTS ONLY (NO BANTER):
   - Only extract persistent factual claims into 'people_mentions' (e.g. projects, jobs, life changes, tech stacks).
   - Completely ignore conversational banter, pleasantries, mood checks ("living the dream"), polite filler ("thank you for asking"), or vague remarks.
   - If the statement is purely about Elliot visiting a place or spending time somewhere, do NOT duplicate it in 'people_mentions'—it belongs in 'places_visited'.
3. NO PLACEHOLDERS:
   - NEVER output "<Person name>" or "<venue name>". If no external person is mentioned, leave 'people_mentions' empty [].

INPUT:
\"\"\"{input_text}\"\"\"

Output strictly valid JSON:
{
  "places_visited": [
    {
      "venue": "exact venue name",
      "visitors": ["person name"],
      "activity_notes": "concise description of what happened, features, or duration"
    }
  ],
  "recommendations": [
    {
      "venue": "venue name",
      "source_person": "person name",
      "note": "recommendation note"
    }
  ],
  "people_mentions": [
    {
      "name": "person name",
      "fact": "durable biographical or technical fact only"
    }
  ],
  "unresolved_pronouns": [],
  "organization_updates": []
}"""

# -------------------------------------------------------------------------
# 3. LOOP MICRO-PROMPT
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
   - Items or money explicitly returned, paid back, or settled in the past tense.
4. EXCLUSIONS:
   - Solo activities, schedules, or personal departures are NOT commitments.

INPUT:
\"\"\"{input_text}\"\"\"

Output strictly valid JSON:
{
  "open_loops": [
    {
      "target": "external contact name",
      "commitment": "item or action",
      "direction": "i_owe_them|they_owe_me"
    }
  ],
  "closed_loops": [
    {
      "target": "external contact name",
      "settled_item": "settled item or money"
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

def classify_intent(statement: str) -> str:
    """Classifies input into CHITCHAT, COMMAND, KNOWLEDGE_QUERY, or MEMORY_DEBRIEF."""
    res = call_ollama(ROUTER_PROMPT.replace("{input_text}", statement))
    return res.get("intent", "CHITCHAT").upper()

def parse_clarification_reply(reply: str, ambiguous_names: List[str], unknown_contacts: List[str]) -> Dict[str, Any]:
    """Interprets the user's reply to a pending clarification."""
    prompt = (
        RESOLUTION_PROMPT
        .replace("{input_text}", reply)
        .replace("{ambiguous_names}", json.dumps(ambiguous_names))
        .replace("{unknown_contacts}", json.dumps(unknown_contacts))
    )
    res = call_ollama(prompt)
    return {
        "decision": res.get("decision", "REJECT").upper(),
        "selected_name": res.get("selected_name")
    }

def deconstruct_turn(statement: str) -> Dict[str, Any]:
    entity_result = call_ollama(ENTITY_MICRO_PROMPT.replace("{input_text}", statement))

    # 1. Sanitize places & ensure rich activity notes
    valid_places = []
    for pl in entity_result.get("places_visited", []):
        v = pl.get("venue", "").strip()
        if v and v.lower() not in GENERIC_VENUES and v.lower() not in PLACEHOLDER_TOKENS and not v.startswith("<"):
            valid_visitors = [
                vis for vis in pl.get("visitors", []) 
                if vis.lower() not in USER_TOKENS 
                and vis.lower() not in GENERIC_PRONOUNS 
                and vis.lower() not in PLACEHOLDER_TOKENS
                and not vis.startswith("<")
            ]
            pl["visitors"] = valid_visitors

            # FALLBACK: If LLM didn't write activity_notes, extract the user's sentence directly
            act_notes = pl.get("activity_notes", "").strip()
            if not act_notes or act_notes.lower() in {"visited", "none", "n/a"}:
                # Clean the raw statement to use as activity notes
                clean_stmt = statement.strip()
                # Strip leading "im at X", "visited X"
                clean_stmt = re.sub(rf"(?i)^(i'm at|im at|visited|went to)\s+{re.escape(v)}[\.\,\s]*", "", clean_stmt).strip()
                pl["activity_notes"] = clean_stmt if clean_stmt else statement.strip()
            else:
                pl["activity_notes"] = act_notes

            valid_places.append(pl)
    entity_result["places_visited"] = valid_places

    # 2. Sanitize recommendations
    valid_recs = []
    for r in entity_result.get("recommendations", []):
        v = r.get("venue", "").strip()
        note = r.get("note", "").lower()
        if v and v.lower() not in GENERIC_VENUES and v.lower() not in PLACEHOLDER_TOKENS:
            if not any(tok in note for tok in ["lent", "borrowed", "camera", "gimbal", "trip", "lunch", "coffee", "been here"]):
                valid_recs.append(r)
    entity_result["recommendations"] = valid_recs

    # 3. Sanitize mentions (Catch placeholders and filter out bantery/temporary moods)
    clean_mentions = []
    banter_patterns = [
        "living the dream", "thank you for asking", "thanks for asking",
        "good chat", "expressed concern", "chillin", "feeling good", "how are you"
    ]

    for m in entity_result.get("people_mentions", []):
        name = m.get("name", "").strip()
        fact = m.get("fact", "").strip()
        name_lower = name.lower()
        fact_lower = fact.lower()

        if name_lower in PLACEHOLDER_TOKENS or name.startswith("<") or name.endswith(">"):
            continue
        if any(bp in fact_lower for bp in banter_patterns):
            continue

        if any(tok in name_lower for tok in ["the person who", "speaker", "narrator", "user", "myself"]) or name_lower in USER_TOKENS:
            name = "Elliot Waigh"

        m["name"] = name
        clean_mentions.append(m)
    entity_result["people_mentions"] = clean_mentions

    # 4. Sanitize orgs
    clean_orgs = []
    for o in entity_result.get("organization_updates", []):
        p = o.get("person", "").strip()
        org = o.get("organization", "").strip()
        if p.lower() in USER_TOKENS or org.lower() in GENERIC_VENUES or org.lower() in PLACEHOLDER_TOKENS or not org:
            continue
        clean_orgs.append(o)
    entity_result["organization_updates"] = clean_orgs

    known_named = [m.get("name") for m in clean_mentions if m.get("name") and m.get("name") != "Elliot Waigh"]
    fallback_target = known_named[0] if len(known_named) == 1 else None

    # 5. Micro-Pass 2: Loops
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

            if not target or target.lower() in USER_TOKENS or target.lower() in GENERIC_PRONOUNS or target.lower() in PLACEHOLDER_TOKENS:
                continue
            if any(err in commit.lower() for err in ["pick up car", "go to gym", "head home", "take off", "leave early"]):
                continue

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

            if target and item and target.lower() not in USER_TOKENS and target.lower() not in GENERIC_VENUES and target.lower() not in PLACEHOLDER_TOKENS:
                closed_loops.append(cl)

    entity_result["open_loops"] = open_loops
    entity_result["closed_loops"] = closed_loops
    return entity_result

def evaluate_clarification_rules(parsed_payload: Dict[str, Any], known_people: List[str]) -> List[str]:
    clarifications = []
    all_names = [
        m.get("name") for m in parsed_payload.get("people_mentions", []) 
        if m.get("name") and m.get("name") != "Elliot Waigh" and not m.get("name").startswith("<")
    ]
    for loop in parsed_payload.get("open_loops", []) + parsed_payload.get("closed_loops", []):
        t = loop.get("target")
        if t and t.lower() not in USER_TOKENS and t.lower() not in GENERIC_PRONOUNS and not t.startswith("<"):
            all_names.append(t)

    distinct_names = list(dict.fromkeys(all_names))
    unknown_contacts = []

    for raw_name in distinct_names:
        if raw_name.lower() in PLACEHOLDER_TOKENS or raw_name.startswith("<"):
            continue
        parts = raw_name.split()
        if len(parts) == 1:
            first_name = parts[0].lower()
            matches = [p for p in known_people if p.split()[0].lower() == first_name]
            if len(matches) > 1:
                opts = " or ".join(matches)
                clarifications.append(f"got multiple hits for '{raw_name}' ({opts}). Which one did you mean, or is this someone new?")
            elif len(matches) == 0:
                unknown_contacts.append(raw_name)

    unresolved_pronouns = [p for p in parsed_payload.get("unresolved_pronouns", []) if not p.startswith("<")]
    for r in parsed_payload.get("recommendations", []):
        src = r.get("source_person", "").strip().lower()
        if src in GENERIC_PRONOUNS and src not in unresolved_pronouns:
            unresolved_pronouns.append(src)

    if unresolved_pronouns and len(distinct_names) > 1:
        candidates = " or ".join(distinct_names)
        for pron in unresolved_pronouns:
            clarifications.append(f"who did you mean by '{pron}'—was that {candidates}?")

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