import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

from .vault_writer import VAULT_DIR, DB_PATH, update_vault_note, find_file_case_insensitive

def sync_loops_to_storage(open_loops: List[Dict[str, Any]], closed_loops: List[Dict[str, Any]]):
    """
    Persists open and closed loops to SQLite open_loops table and appends
    corresponding action items to the target contact's Obsidian note.
    """
    if not DB_PATH.exists():
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS open_loops (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target TEXT NOT NULL,
            commitment TEXT NOT NULL,
            direction TEXT NOT NULL,
            status TEXT DEFAULT 'open',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            settled_at TIMESTAMP
        );
    """)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    # 1. Process New Open Loops
    for ol in open_loops:
        target = ol.get("target")
        commitment = ol.get("commitment")
        direction = ol.get("direction", "i_owe_them")

        if not target or not commitment:
            continue

        cur.execute(
            "SELECT id FROM open_loops WHERE target = ? AND commitment = ? AND status = 'open';",
            (target, commitment)
        )
        if not cur.fetchone():
            cur.execute(
                "INSERT INTO open_loops (target, commitment, direction, status) VALUES (?, ?, ?, 'open');",
                (target, commitment, direction)
            )

            target_file = find_file_case_insensitive(VAULT_DIR / "People", target)
            if target_file:
                arrow = "User ->" if direction == "i_owe_them" else "<- User"
                log_entry = f"**{timestamp} (Loop Opened):** [{arrow}] {commitment}"
                update_vault_note(target_file, "ATHENA Log", log_entry, bullet_style="• ")

    # 2. Process Closed / Settled Loops
    for cl in closed_loops:
        target = cl.get("target")
        settled_item = cl.get("settled_item")

        if not target or not settled_item:
            continue

        cur.execute("""
            UPDATE open_loops 
            SET status = 'closed', settled_at = CURRENT_TIMESTAMP 
            WHERE target = ? AND status = 'open' AND commitment LIKE ?;
        """, (target, f"%{settled_item}%"))

        target_file = find_file_case_insensitive(VAULT_DIR / "People", target)
        if target_file:
            log_entry = f"**{timestamp} (Loop Closed):** Settled/Returned: {settled_item}"
            update_vault_note(target_file, "ATHENA Log", log_entry, bullet_style="• ")

    conn.commit()
    conn.close()