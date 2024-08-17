import re

class EntityExtractor:
    def __init__(self):
        pass

    def extract_entities(self, user_input, context_definitions):
        entities = {}
        #print("Processing", user_input, context_definitions)

        for entity_type, possible_values in context_definitions.items():
            if possible_values:
                # For predefined possible values, check if any of them exist in the user input
                for value in possible_values:
                    if re.search(rf"\b{re.escape(value)}\b", user_input, re.IGNORECASE):
                        entities[entity_type] = value
                        break  # Stop checking once a match is found
            else:
                # For open-ended types, capture the whole user input
                entities[entity_type] = user_input.strip()

        return entities
