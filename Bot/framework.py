import asyncio
import re

def match_command(tool_spec, user_input):
    text = user_input.lower()
    for command, cmd_def in tool_spec["commands"].items():
        for example in cmd_def["examples"]:
            if example in text:
                return command, cmd_def
    return None, None


def extract_params(cmd_def, user_input):
    text = user_input.lower()
    params = {}
    for param in cmd_def.get("params", []):
        # TODO: plug in EntityExtractor for smart slot-filling
        m = re.search(rf"{param}\s+(\w+)", text)
        if m:
            params[param] = m.group(1)
    return params


def execute_command(tool_module, tool_spec, user_input):
    command_name, cmd_def = match_command(tool_spec, user_input)
    if not cmd_def:
        return None

    func_name = cmd_def.get("function")
    func = getattr(tool_module, func_name, None)
    if not func:
        return f"ATHENA: Missing function for {command_name}."

    kwargs = extract_params(cmd_def, user_input)

    try:
        result = asyncio.run(func(**kwargs))
        return f"ATHENA: {result}"
    except Exception as e:
        return f"ATHENA: Error executing {command_name}: {e}"
