import json
import re
import sqlite3
from pathlib import Path
from typing import Optional, Tuple
import requests

SCRIPT_DIR = Path(__file__).resolve().parent
DB_PATH = SCRIPT_DIR / "athena.db"

# Vault Root Resolution
VAULT_DIR = SCRIPT_DIR.parents[1] / "Brain"
if not VAULT_DIR.exists():
    VAULT_DIR = SCRIPT_DIR.parent / "Brain"
if not VAULT_DIR.exists():
    VAULT_DIR = SCRIPT_DIR / "Brain"

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen2.5:7b"

from .vault_writer import consolidate_session, provision_new_person

STOPWORDS = {
    "now", "tell", "me", "about", "who", "what", "where", "is", "the", "does",
    "did", "how", "when", "can", "you", "a", "an", "and", "or", "to", "at"
}

def get_entity_context(query: str, last_active_entity: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    """
    Resolves entity context against SQLite using exact full names, first names,
    surnames (e.g., 'Durbridge' -> 'Josh Durbridge'), and conversational continuity.
    """
    if not DB_PATH.exists():
        return None, None

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    clean_q = re.sub(r"[^\w\s]", "", query.lower())
    tokens = [w for w in clean_q.split() if w not in STOPWORDS]

    matched_entity = None

    cur.execute("SELECT id, folder, file_path FROM entities;")
    all_entities = cur.fetchall()

    # 1. Exact string match across query
    for ent_id, folder, rel_path in all_entities:
        if ent_id.lower() in clean_q:
            matched_entity = (ent_id, folder, rel_path)
            break

    # 2. Token / Surname / First name matching
    if not matched_entity and tokens:
        for ent_id, folder, rel_path in all_entities:
            parts = [p.lower() for p in ent_id.split()]
            # Match surname or unique distinctive token
            if any(t in parts for t in tokens):
                matched_entity = (ent_id, folder, rel_path)
                break

    # 3. Conversational continuity fallback
    if not matched_entity and last_active_entity:
        cur.execute("SELECT id, folder, file_path FROM entities WHERE id = ?;", (last_active_entity,))
        row = cur.fetchone()
        if row:
            matched_entity = (row[0], row[1], row[2])

    if not matched_entity:
        conn.close()
        return None, None

    entity_id, folder, rel_path = matched_entity

    # Retrieve structured properties and graph triples
    cur.execute("SELECT key, value FROM properties WHERE entity_id = ?;", (entity_id,))
    props = cur.fetchall()

    cur.execute("SELECT predicate, object FROM triples WHERE subject = ?;", (entity_id,))
    out_triples = cur.fetchall()

    cur.execute("SELECT subject, predicate FROM triples WHERE object = ?;", (entity_id,))
    in_triples = cur.fetchall()

    conn.close()

    # Retrieve raw markdown file content directly as source truth
    full_file_path = VAULT_DIR / rel_path
    raw_markdown = ""
    if full_file_path.exists():
        raw_markdown = full_file_path.read_text(encoding="utf-8")

    context_lines = [f"# Verified Entity Record: {entity_id} ({folder})"]
    if props:
        context_lines.append("## Properties:")
        for k, v in props:
            context_lines.append(f"- {k}: {v}")

    if out_triples or in_triples:
        context_lines.append("## Direct Connections:")
        for pred, obj in out_triples:
            context_lines.append(f"- {entity_id} -> {pred} -> {obj}")
        for subj, pred in in_triples:
            context_lines.append(f"- {subj} -> {pred} -> {entity_id}")

    if raw_markdown:
        context_lines.append("\n## Raw Vault Document:")
        context_lines.append(raw_markdown)

    return "\n".join(context_lines), entity_id

def ask_brain_7b(query: str, context: str) -> str:
    """Answers factual questions using strict 0.0 temperature to avoid hallucinations."""
    system_prompt = (
        "You are the analytical memory engine for ATHENA. "
        "Answer the user's factual inquiry strictly using the provided verified entity records. "
        "If a specific detail is not present in the record, state that clearly and candidly. "
        "Never invent, assume, or extrapolate facts beyond what is documented."
    )
    prompt = f"{system_prompt}\n\nRECORDS:\n{context}\n\nQUESTION: {query}\n\nANSWER:"

    try:
        res = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL_NAME,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.0,
                    "top_p": 0.1
                }
            },
            timeout=45
        )
        if res.status_code == 200:
            return res.json().get("response", "").strip()
        return "I hit a snag accessing the 7B memory core, Boss."
    except Exception as e:
        return f"Memory retrieval error: {e}"