import sqlite3
import re
from pathlib import Path
from typing import List, Tuple
import requests

SCRIPT_DIR = Path(__file__).resolve().parent
DB_PATH = SCRIPT_DIR / "athena.db"
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen2.5:7b"

MONTH_MAP = {
    "january": "01", "jan": "01", "february": "02", "feb": "02",
    "march": "03", "mar": "03", "april": "04", "apr": "04",
    "may": "05", "june": "06", "jun": "06", "july": "07", "jul": "07",
    "august": "08", "aug": "08", "september": "09", "sep": "09", "sept": "09",
    "october": "10", "oct": "10", "november": "11", "nov": "11", "december": "12", "dec": "12"
}

def extract_dates_and_events(query: str, fallback_entity: str = None) -> List[str]:
    candidates = []

    # 1. Numeric dates: 11.09.26, 11/09/2026, 2026-09-11
    num_dates = re.findall(r"\b\d{1,4}[./\-]\d{1,2}[./\-]\d{2,4}\b", query)
    for nd in num_dates:
        candidates.append(nd)
        clean = re.sub(r"[/\\-]", ".", nd)
        candidates.append(clean)
        parts = clean.split(".")
        if len(parts) == 3:
            d, m, y = parts[0].zfill(2), parts[1].zfill(2), parts[2]
            candidates.append(f"{d}.{m}.{y[-2:]}")
            candidates.append(f"{d}.{m}.20{y[-2:]}" if len(y) == 2 else f"{d}.{m}.{y}")

    # 2. Spelled-out dates: "11th of september", "september 11"
    text_date = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?([a-zA-Z]+)(?:\s+(\d{2,4}))?\b", query, flags=re.IGNORECASE)
    if text_date:
        day = text_date.group(1).zfill(2)
        month_word = text_date.group(2).lower()
        year = text_date.group(3) if text_date.group(3) else "26"
        if month_word in MONTH_MAP:
            m = MONTH_MAP[month_word]
            candidates.append(f"{day}.{m}.{year[-2:]}")
            candidates.append(f"{day}.{m}.20{year[-2:]}" if len(year) == 2 else f"{day}.{m}.{year}")

    # 3. Dynamic Event Phrases
    event_phrases = re.findall(
        r"\b(?:[A-Za-z0-9./\-]+\s+)?(?:Night Out|Dinner|Lunch|Party|Meetup|Drinks|Trip|Event|Breakfast)\b", 
        query, 
        flags=re.IGNORECASE
    )
    for ep in event_phrases:
        candidates.append(ep.strip())

    # 4. Standard Entity Tokens and N-grams
    clean = re.sub(
        r"\b(what|where|who|when|how|is|are|the|does|do|did|have|has|about|event|happened|on|at|in|s|tell|me|of|had|a)\b", 
        " ", 
        query, 
        flags=re.IGNORECASE
    )
    tokens = [t.strip("'\".,!?") for t in clean.split() if len(t.strip("'\".,!?")) > 1]
    for i in range(len(tokens)):
        for j in range(i + 1, min(i + 4, len(tokens) + 1)):
            candidates.append(" ".join(tokens[i:j]))
    candidates.extend(tokens)

    # 5. Temporal / Recency Keywords
    if any(w in query.lower() for w in ["recent", "latest", "last"]):
        candidates.append("__LATEST_EVENT__")

    # 6. Conversational Pronoun Fallback
    if any(p in query.lower().split() for p in ["he", "him", "his", "she", "her", "they", "them"]):
        if fallback_entity:
            candidates.append(fallback_entity)

    # Deduplicate preserving priority
    seen = set()
    deduped = []
    for c in candidates:
        if c.lower() not in seen:
            seen.add(c.lower())
            deduped.append(c)
    return deduped

def get_entity_context(raw_query: str, fallback_entity: str = None) -> Tuple[str, str]:
    if not DB_PATH.exists():
        return "", ""

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    candidates = extract_dates_and_events(raw_query, fallback_entity)
    matched_entities = []
    lines = []
    primary_entity = ""

    for cand in candidates:
        matched_rows = []

        # Recency resolution
        if cand == "__LATEST_EVENT__":
            cur.execute("""
                SELECT id, type, folder FROM entities 
                WHERE type = 'event' OR folder = 'Events' OR id LIKE '%Night Out%' 
                ORDER BY id DESC LIMIT 1;
            """)
            matched_rows = cur.fetchall()
        else:
            # Match Entity ID
            cur.execute("SELECT id, type, folder FROM entities WHERE LOWER(id) LIKE ?;", (f"%{cand.lower()}%",))
            matched_rows = cur.fetchall()

            # Fallback to Property Match
            if not matched_rows:
                cur.execute("SELECT entity_id FROM properties WHERE LOWER(value) LIKE ? LIMIT 1;", (f"%{cand.lower()}%",))
                prop_match = cur.fetchone()
                if prop_match:
                    cur.execute("SELECT id, type, folder FROM entities WHERE id = ?;", (prop_match[0],))
                    matched_rows = cur.fetchall()

        if matched_rows:
            matched_entity = matched_rows[0][0]
            if matched_entity in matched_entities:
                continue

            matched_entities.append(matched_entity)
            if not primary_entity:
                primary_entity = matched_entity

            ent_type = matched_rows[0][1]
            lines.append(f"[Verified Facts for {matched_entity} ({ent_type.upper()})]:")

            cur.execute("SELECT key, value FROM properties WHERE entity_id = ?;", (matched_entity,))
            for k, v in cur.fetchall():
                lines.append(f"  • {k}: {v}")

            cur.execute("SELECT predicate, object FROM triples WHERE subject = ?;", (matched_entity,))
            sub_trips = cur.fetchall()
            if sub_trips:
                lines.append(f"\n[Outgoing Connections / Relationships]:")
                for pred, obj in sub_trips:
                    lines.append(f"  • {matched_entity} --[{pred}]--> {obj}")

            cur.execute("SELECT subject, predicate FROM triples WHERE object = ?;", (matched_entity,))
            obj_trips = cur.fetchall()
            if obj_trips:
                lines.append(f"\n[Incoming Connections / Mentions]:")
                for sub, pred in obj_trips:
                    lines.append(f"  • {sub} --[{pred}]--> {matched_entity}")

            cur.execute("SELECT commitment, direction, status FROM open_loops WHERE LOWER(target) = ?;", (matched_entity.lower(),))
            loops = cur.fetchall()
            if loops:
                lines.append(f"\n[Open Commitments]:")
                for c, d, s in loops:
                    lines.append(f"  • [{d.upper()}] {c} ({s})")

            # Max 2 matched entities to keep context tight
            if len(matched_entities) >= 2:
                break

    conn.close()
    return ("\n".join(lines) if lines else ""), primary_entity

def ask_brain_7b(question: str, context: str) -> str:
    """Exact system prompt from your verified quiz_graph harness."""
    prompt = f"""You are ATHENA, Elliot's personal AI companion.
Speak naturally, calmly, and directly. Use the verified ground-truth facts below to answer the user's question.
If the information is not present in the verified facts, state clearly and concisely that you don't have that on record.
NEVER invent or extrapolate facts, dates, venues, drinks, or relationships.

VERIFIED FACTS:
\"\"\"
{context}
\"\"\"

QUESTION: {question}

ATHENA'S ANSWER:"""

    try:
        res = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL_NAME,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.2}
            },
            timeout=60
        )
        if res.status_code == 200:
            return res.json().get("response", "").strip()
        return f"Brain connection error: HTTP {res.status_code}"
    except Exception as e:
        return f"Brain unavailable: {e}"