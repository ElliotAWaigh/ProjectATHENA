import importlib
import json
from pathlib import Path
import re

BOT_DIR = Path(__file__).resolve().parent
TOOLS_CONFIG = BOT_DIR / "config" / "tools.json"


def _inspect_registered_specs():
    """Dynamically reads tools.json and all tool modules to discover:

    1. All expected parameter names across all tools.
    2. Registered named targets (devices, playlists, locations, etc.).
    3. Command example words to ignore during fallback extraction.
    """
    expected_params = set()
    known_named_entities = set()
    command_tokens = set()

    if not TOOLS_CONFIG.exists():
        return expected_params, known_named_entities, command_tokens

    try:
        with open(TOOLS_CONFIG, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        for module_path in manifest.values():
            try:
                mod = importlib.import_module(module_path)
                spec = getattr(mod, "TOOL_SPEC", None)
                if not spec or "commands" not in spec:
                    continue

                # Ingest parameters and trigger words from each command spec
                for cmd_meta in spec["commands"].values():
                    for p in cmd_meta.get("params", []):
                        expected_params.add(p)
                    for ex in cmd_meta.get("examples", []):
                        for word in ex.lower().split():
                            command_tokens.add(word)

                # Dynamically inspect any uppercase dictionary/list/set targets exposed by the tool
                # (e.g., DEVICE_IPS, ROOMS, PRESETS, PLAYLISTS)
                for attr_name in dir(mod):
                    if attr_name.startswith("_") or not attr_name.isupper():
                        continue
                    attr_val = getattr(mod, attr_name)
                    if isinstance(attr_val, dict):
                        known_named_entities.update(str(k).lower() for k in attr_val.keys())
                    elif isinstance(attr_val, (list, set, tuple)):
                        known_named_entities.update(str(item).lower() for item in attr_val)

            except Exception:
                continue
    except Exception:
        pass

    return expected_params, known_named_entities, command_tokens


def extract_entities(text: str) -> dict:
    """Tool-agnostic entity extractor that bridges raw input into parameter slots

    expected by MultiStageProcessor without hardcoded tool logic.
    """
    entities = {}
    lower_text = text.lower().strip()

    expected_params, known_named_entities, command_tokens = _inspect_registered_specs()

    # 1. Numeric Extraction (e.g., '50', '80%', '2500')
    num_match = re.search(r"\b(\d{1,4})\s?%?\b", lower_text)
    if num_match:
        val = int(num_match.group(1))
        # Prioritize assigning the number to an expected parameter slot
        for numeric_slot in ["brightness", "volume", "color_temp", "level", "amount", "percentage"]:
            if numeric_slot in expected_params:
                # If color_temp is expected and value is in Kelvin range, assign it there
                if numeric_slot == "color_temp" and val >= 1000:
                    entities["color_temp"] = val
                    break
                elif numeric_slot != "color_temp":
                    entities[numeric_slot] = val
                    break
        else:
            entities["value"] = val

    # 2. Descriptive Color Temperature / Tone Hints
    if "color_temp" in expected_params or "temperature" in expected_params:
        if any(w in lower_text for w in ["warmer", "warm", "cozy", "amber"]):
            entities["color_temp"] = "warm"
        elif any(c in lower_text for c in ["cooler", "cool", "colder", "daylight", "white"]):
            entities["color_temp"] = "cool"

    # 3. Quoted Strings (e.g., play "Bohemian Rhapsody", search "quantum theory")
    quote_match = re.search(r"[\"'](.*?)[\"']", text)
    if quote_match:
        quoted_val = quote_match.group(1).strip()
        for text_slot in ["query", "song", "track", "title", "name", "message"]:
            if text_slot in expected_params:
                entities[text_slot] = quoted_val
                break

    # 4. Target Entity Match (devices, channels, playlists, items)
    if known_named_entities:
        # Match longest phrases first to prevent partial substrings from cutting off full names
        sorted_entities = sorted(known_named_entities, key=len, reverse=True)
        for entity_name in sorted_entities:
            if entity_name in lower_text:
                for target_slot in ["device", "target", "item", "room", "channel", "playlist"]:
                    if target_slot in expected_params:
                        entities[target_slot] = entity_name
                        break
                else:
                    entities["target"] = entity_name
                break

    # 5. Fallback Target Extraction (if a tool expects a target/device but no known keyword was matched)
    if any(slot in expected_params for slot in ["device", "target", "query"]):
        target_key = next((k for k in ["device", "target", "query"] if k in expected_params), None)
        if target_key and target_key not in entities:
            # Strip out command action verbs and numbers, take whatever remains
            tokens = lower_text.split()
            remaining = [t for t in tokens if t not in command_tokens and not t.isdigit()]
            if remaining:
                entities[target_key] = " ".join(remaining)

    return entities