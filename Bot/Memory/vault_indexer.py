import os
import re
import sqlite3
from pathlib import Path
import yaml

SCRIPT_DIR = Path(__file__).resolve().parent

# Target DB lives directly alongside this script inside Bot/Memory/athena.db
DB_PATH = SCRIPT_DIR / "athena.db"

# Resolve Brain directory (00ATHENA/Brain)
VAULT_DIR = SCRIPT_DIR.parents[1] / "Brain"
if not VAULT_DIR.exists():
    VAULT_DIR = SCRIPT_DIR.parent / "Brain"
if not VAULT_DIR.exists():
    VAULT_DIR = SCRIPT_DIR / "Brain"

TARGET_FOLDERS = ["People", "Schools", "Places", "Organisations", "Events", "Spots", "Circles"]

WIKILINK_PATTERN = re.compile(r"\[\[(.*?)\]\]")
BOLD_FIELD_PATTERN = re.compile(r"^[*-]\s+\*\*([A-Za-z0-9 _/()\-]+):\*\*\s*(.+)$", re.MULTILINE)

def clean_target(raw: str) -> str:
    """Strip alias syntax: [[Target|Alias]] -> Target."""
    target = raw.split("|")[0].strip()
    return target.replace("[[", "").replace("]]", "").strip()

def init_db(conn: sqlite3.Connection):
    """Create schema if database tables do not already exist."""
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS entities (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            folder TEXT NOT NULL,
            file_path TEXT NOT NULL
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS properties (
            entity_id TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            PRIMARY KEY (entity_id, key, value),
            FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS triples (
            subject TEXT NOT NULL,
            predicate TEXT NOT NULL,
            object TEXT NOT NULL,
            source_file TEXT NOT NULL,
            PRIMARY KEY (subject, predicate, object)
        );
    """)
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
    cur.execute("CREATE INDEX IF NOT EXISTS idx_triples_sub ON triples(subject);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_triples_obj ON triples(object);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_triples_pred ON triples(predicate);")
    conn.commit()

def parse_markdown_file(file_path: Path, folder_name: str):
    entity_id = file_path.stem.strip()
    entity_type = folder_name.rstrip("s").lower()
    
    properties = []
    triples = []
    
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return entity_id, entity_type, properties, triples

    body = content
    # Parse YAML frontmatter cleanly
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            fm_text = parts[1]
            body = parts[2]
            try:
                fm_data = yaml.safe_load(fm_text) or {}
                if isinstance(fm_data, dict):
                    if "type" in fm_data:
                        entity_type = str(fm_data["type"]).lower()
                    for k, v in fm_data.items():
                        if isinstance(v, list):
                            for item in v:
                                item_str = str(item).strip()
                                wl = WIKILINK_PATTERN.findall(item_str)
                                if wl:
                                    for target in wl:
                                        t_clean = clean_target(target)
                                        triples.append((entity_id, k, t_clean))
                                else:
                                    properties.append((k, item_str))
                        else:
                            val_str = str(v).strip()
                            wl = WIKILINK_PATTERN.findall(val_str)
                            if wl:
                                for target in wl:
                                    t_clean = clean_target(target)
                                    triples.append((entity_id, k, t_clean))
                            else:
                                if val_str and val_str not in ["[[]]", "[]"]:
                                    properties.append((k, val_str))
            except Exception as e:
                print(f"YAML parse error in {file_path.name}: {e}")

    # Parse bold list fields like "- **Attendees:** [[...]]"
    for k, v in BOLD_FIELD_PATTERN.findall(body):
        k_clean = k.strip()
        v_clean = v.strip()
        wl = WIKILINK_PATTERN.findall(v_clean)
        if wl:
            for target in wl:
                t_clean = clean_target(target)
                if t_clean:
                    triples.append((entity_id, k_clean, t_clean))
        else:
            if v_clean:
                properties.append((k_clean, v_clean))

    # Parse Event Narrative sections (e.g. "Standout Incidents / What Happened")
    if "## Standout Incidents" in body:
        section_text = body.split("## Standout Incidents", 1)[1].strip()
        lines = [line.strip("- *% \t") for line in section_text.splitlines() if line.strip("- *% \t")]
        clean_narrative = " ".join(lines)
        if clean_narrative:
            properties.append(("Summary / Incidents", clean_narrative))
            for wl in WIKILINK_PATTERN.findall(clean_narrative):
                t_clean = clean_target(wl)
                if t_clean and t_clean != entity_id:
                    triples.append((entity_id, "mentioned", t_clean))

    # Parse generic inline fields: Key:: Value
    for k, v in re.findall(r"^(?:[-*]\s*)?([A-Za-z0-9 _/()\-]+)::\s*(.+)$", body, re.MULTILINE):
        k_clean = k.strip()
        v_clean = v.strip()
        wl = WIKILINK_PATTERN.findall(v_clean)
        if wl:
            for target in wl:
                t_clean = clean_target(target)
                triples.append((entity_id, k_clean, t_clean))
        else:
            if v_clean:
                properties.append((k_clean, v_clean))

    return entity_id, entity_type, properties, triples

def crawl_vault():
    print(f"[*] Target SQLite Database: {DB_PATH}")
    print(f"[*] Starting crawl of Obsidian Brain at: {VAULT_DIR}")
    
    if not VAULT_DIR.exists():
        print(f"[!] Vault directory does not exist at: {VAULT_DIR}")
        return

    # Ensure Bot/Memory/ directory exists
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    init_db(conn)
    cur = conn.cursor()

    # Clear cached graph tables to prevent duplicates (preserves open_loops)
    cur.execute("DELETE FROM properties;")
    cur.execute("DELETE FROM triples;")
    cur.execute("DELETE FROM entities;")
    conn.commit()

    total_entities = 0
    total_props = 0
    total_triples = 0

    for folder_name in TARGET_FOLDERS:
        target_path = VAULT_DIR / folder_name
        if not target_path.exists():
            continue

        for root, _, files in os.walk(target_path):
            for file in files:
                if not file.endswith(".md"):
                    continue

                full_path = Path(root) / file
                rel_path = full_path.relative_to(VAULT_DIR)
                entity_id, entity_type, props, trips = parse_markdown_file(full_path, folder_name)

                cur.execute(
                    "INSERT OR REPLACE INTO entities (id, type, folder, file_path) VALUES (?, ?, ?, ?);",
                    (entity_id, entity_type, folder_name, str(rel_path))
                )
                total_entities += 1

                for k, v in props:
                    cur.execute(
                        "INSERT OR IGNORE INTO properties (entity_id, key, value) VALUES (?, ?, ?);",
                        (entity_id, k, v)
                    )
                    total_props += 1

                for sub, pred, obj in trips:
                    cur.execute(
                        "INSERT OR IGNORE INTO triples (subject, predicate, object, source_file) VALUES (?, ?, ?, ?);",
                        (sub, pred, obj, str(rel_path))
                    )
                    total_triples += 1

    conn.commit()
    conn.close()

    print(f"[✓] Scrape complete:")
    print(f"    - Total Entities:   {total_entities}")
    print(f"    - Total Properties: {total_props}")
    print(f"    - Total Triples:    {total_triples}")
    print(f"[✓] SQLite database ready at: {DB_PATH}")

# Alias so both crawl_vault() and reindex_vault() can be invoked seamlessly
reindex_vault = crawl_vault

if __name__ == "__main__":
    crawl_vault()