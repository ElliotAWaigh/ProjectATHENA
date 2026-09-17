import sys
from pathlib import Path

# Resolve pathing
BOT_DIR = Path(__file__).resolve().parent
if str(BOT_DIR) not in sys.path:
    sys.path.append(str(BOT_DIR))

from multi_stage_processor import MultiStageProcessor
from Memory.vault_indexer import reindex_vault

def run_chat():
    print("=" * 60)
    print(" 🦉 ATHENA V5: Offline Dual-Engine Intelligence")
    print("=" * 60)

    # 1. Sync Obsidian Vault to SQLite Knowledge Graph before boot
    try:
        reindex_vault()
    except Exception as e:
        print(f"[Warning] Vault indexing encountered an issue: {e}")

    # 2. Initialize Core Processor
    processor = MultiStageProcessor()

    print("\n[Online] Ready. Type your message below. (Type 'exit' or 'end' to consolidate and close)\n")

    while True:
        try:
            user_input = input("Elliot > ").strip()
            if not user_input:
                continue

            response, should_exit = processor.process_query(user_input)
            print(f"\n{response}\n")

            if should_exit:
                break

        except KeyboardInterrupt:
            print("\n\n[Interrupt] Consolidating and shutting down...")
            processor.process_query("end")
            break
        except Exception as e:
            print(f"\n[System Error] {e}\n")

if __name__ == "__main__":
    run_chat()