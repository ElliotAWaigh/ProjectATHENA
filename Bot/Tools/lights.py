import asyncio
import re
from pywizlight import wizlight, PilotBuilder

DEVICE_IPS = {
    "bottom lamp light": "192.168.0.153",
    "middle lamp light": "192.168.0.91",
    "mushroom light": "192.168.0.228",
    "top lamp light": "192.168.0.149"
}

TOOL_SPEC = {
    "intent": "light_control",
    "description": "Control WizLights (on/off/brightness/temp)",
    "commands": {
        "turn_on": {
            "examples": ["turn on", "switch on", "pump the lights", "lights on", "illuminate", "fire up"],
            "params": ["device"],
            "defaults": {"device": "all"},
            "function": "turn_on"
        },
        "turn_off": {
            "examples": ["turn off", "switch off", "blackout", "kill lights", "lights out", "douse"],
            "params": ["device"],
            "defaults": {"device": "all"},
            "function": "turn_off"
        },
        "set_brightness": {
            "examples": [
                "dim lights", "brighten", "set brightness to 50", "crank the lights",
                "drop the lights low", "make my lights dimmer", "make my lights brighter"
            ],
            "params": ["device", "brightness"],
            "defaults": {"device": "all", "brightness": 128},
            "function": "set_brightness"
        },
        "set_color_temp": {
            "examples": ["make it warmer", "make it cooler", "set color temperature", "ice out the room", "cozy vibes"],
            "params": ["device", "color_temp"],
            "defaults": {"device": "all", "color_temp": "warm"},
            "function": "set_color_temp"
        }
    }
}

def _targets(device):
    """
    Resolves targets using bidirectional matching so variations like
    'mushroom', 'mushroom lamp', 'top lamp', and 'all' match correctly.
    """
    if not device or str(device).strip().lower() in ["all", "room", "lights", "everything"]:
        return list(DEVICE_IPS.items())
    
    dev = str(device).lower().strip()
    # Strip common noise words the LLM might append
    cleaned_dev = re.sub(r"\b(light|lamp)\b", "", dev).strip()
    
    matches = []
    for name, ip in DEVICE_IPS.items():
        cleaned_name = re.sub(r"\b(light|lamp)\b", "", name).strip()
        if dev in name or name in dev or (cleaned_dev and cleaned_dev in cleaned_name):
            matches.append((name, ip))
            
    return matches if matches else list(DEVICE_IPS.items())


async def turn_on(device="all", **_):
    targets = _targets(device)
    tasks = []
    for name, ip in targets:
        bulb = wizlight(ip)
        tasks.append(bulb.turn_on(PilotBuilder()))
        print(f"[LIGHTS] ON → {name} ({ip})")
    
    if tasks:
        await asyncio.gather(*tasks)
    return f"Turned on {device}."


async def turn_off(device="all", **_):
    targets = _targets(device)
    tasks = []
    for name, ip in targets:
        bulb = wizlight(ip)
        tasks.append(bulb.turn_off())
        print(f"[LIGHTS] OFF → {name} ({ip})")
    
    if tasks:
        await asyncio.gather(*tasks)
    return f"Turned off {device}."


async def set_brightness(device="all", brightness=128, **_):
    # Sanitize string inputs (e.g. "50%" -> 50)
    if isinstance(brightness, str):
        match = re.search(r"\d+", brightness)
        brightness = int(match.group(0)) if match else 128

    if brightness is None:
        brightness = 128

    # Scale percentages (<= 100) to 0-255 range
    if brightness <= 100:
        val = int(round((brightness / 100.0) * 255))
    else:
        val = int(brightness)

    val = max(10, min(255, val))

    targets = _targets(device)
    tasks = []
    for name, ip in targets:
        bulb = wizlight(ip)
        tasks.append(bulb.turn_on(PilotBuilder(brightness=val)))
        print(f"[LIGHTS] Brightness {val}/255 ({int(round(val/255*100))}%) → {name}")
    
    if tasks:
        await asyncio.gather(*tasks)
    return f"Set brightness of {device} to {int(round(val/255*100))}%."


async def set_color_temp(device="all", color_temp="warm", **_):
    # Default warm amber
    kelvin = 2700
    
    if isinstance(color_temp, str):
        ct = color_temp.lower()
        if any(w in ct for w in ["cool", "cold", "daylight", "ice", "white", "hospital"]):
            kelvin = 6000
        elif any(w in ct for w in ["warm", "cozy", "amber", "candle", "soft"]):
            kelvin = 2700
        else:
            match = re.search(r"\d{4}", ct)
            if match:
                kelvin = int(match.group(0))
    elif isinstance(color_temp, (int, float)):
        kelvin = int(color_temp)

    # WiZ bulbs typically operate between 2200K and 6500K
    kelvin = max(2200, min(6500, kelvin))

    targets = _targets(device)
    tasks = []
    for name, ip in targets:
        bulb = wizlight(ip)
        tasks.append(bulb.turn_on(PilotBuilder(colortemp=kelvin)))
        print(f"[LIGHTS] Temp {kelvin}K → {name}")
    
    if tasks:
        await asyncio.gather(*tasks)
    return f"Set color temperature of {device} to {kelvin}K."