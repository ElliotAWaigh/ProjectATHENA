import re

def extract_entities(text):
    """Simple rule-based entity extractor for ATHENA hybrid memory."""
    entities = {}

    # Detect brightness
    brightness_match = re.search(r'(\d+)\s?%?', text)
    if brightness_match:
        entities["brightness"] = int(brightness_match.group(1))

    # Detect color temperature hints
    if "warmer" in text:
        entities["color_temp"] = "warm"
    elif "cooler" in text or "colder" in text:
        entities["color_temp"] = "cool"

    # Detect device names (match partials)
    for name in ["mushroom light", "top lamp light", "middle lamp light", "bottom lamp light"]:
        if name in text:
            entities["device"] = name

    return entities
