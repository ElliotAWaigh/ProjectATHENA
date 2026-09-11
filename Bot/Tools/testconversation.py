TOOL_SPEC = {
    "intent": "conversation",
    "description": "Saying hello",
    "commands": {
        "hello": {
            "examples": ["hello there", "hi", "are you there", "hello maam", "whats up"],
            "params": ["What do you want"],
            "defaults": {},
            "function": "say_hello"
        },
    }
}

def say_hello():
    return "Sup Boss"