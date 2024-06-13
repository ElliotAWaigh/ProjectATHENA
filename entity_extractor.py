import re

class EntityExtractor:
    def __init__(self):
        pass

    def extract_entities(self, user_input, required_context):
        entities = {}
        for entity_type, possible_values in required_context.items():
            found_values = [value for value in possible_values if re.search(rf"\b{value}\b", user_input, re.IGNORECASE)]
            if found_values:
                entities[entity_type] = found_values
        return entities