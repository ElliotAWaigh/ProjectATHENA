import asyncio
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
            "examples": ["turn on", "switch on", "turn on my lights", "lights on", "illuminate"],
            "params": ["device"],
            "defaults": {"device": "all"},        # <-- DEFAULT = all
            "function": "turn_on"
        },
        "turn_off": {
            "examples": ["turn off", "switch off", "turn off my lights", "lights off", "kill lights"],
            "params": ["device"],
            "defaults": {"device": "all"},        # <-- DEFAULT = all
            "function": "turn_off"
        },
        "set_brightness": {
            "examples": [
                "dim lights", "brighten", "set brightness to 50", "make it brighter",
                "increase brightness", "decrease brightness", "make my lights dimmer",
                "make my lights brighter"
            ],
            "params": ["device", "brightness"],
            "defaults": {"device": "all", "brightness": 128},  # sensible defaults
            "function": "set_brightness"
        },
        "set_color_temp": {
            "examples": ["make it warmer", "make it cooler", "set color temperature", "change tone"],
            "params": ["device", "color_temp"],
            "defaults": {"device": "all", "color_temp": "warm"},
            "function": "set_color_temp"
        }
    }
}

def _targets(device):
    if not device or device == "all":
        return list(DEVICE_IPS.items())
    # allow partial matches
    dev = device.lower()
    return [(name, ip) for name, ip in DEVICE_IPS.items() if dev in name]

def resolve_params(text: str):
    t = text.lower()
    out = {}
    # device
    if "all" in t or "my lights" in t or "lights" == t.strip():
        out["device"] = "all"
    else:
        for name in DEVICE_IPS.keys():
            if name in t:
                out["device"] = name
                break
    # brightness (numbers in text)
    m = __import__("re").search(r"(\d+)\s?%?", t)
    if m:
        out["brightness"] = int(m.group(1))
    # color temp
    if "warmer" in t or "warm" in t:
        out["color_temp"] = "warm"
    elif "cooler" in t or "cool" in t or "colder" in t:
        out["color_temp"] = "cool"
    return out

async def turn_on(device=None, **_):
    tasks = []
    for name, ip in _targets(device):
        bulb = wizlight(ip)
        tasks.append(bulb.turn_on(PilotBuilder()))
        print(f"[LIGHTS] ON → {name}")
    await asyncio.gather(*tasks)
    return f"Turning on {device or 'all lights'}."

async def turn_off(device=None, **_):
    tasks = []
    for name, ip in _targets(device):
        bulb = wizlight(ip)
        tasks.append(bulb.turn_off())
        print(f"[LIGHTS] OFF → {name}")
    await asyncio.gather(*tasks)
    return f"Turning off {device or 'all lights'}."

async def set_brightness(device=None, brightness=None, **_):
    # clamp to [10..255] if they gave a 0-100 value, scale to 0-255
    if brightness is None:
        brightness = 128
    if brightness <= 100:
        brightness = int(round((brightness / 100.0) * 255))
    brightness = max(10, min(255, brightness))
    tasks = []
    for name, ip in _targets(device):
        bulb = wizlight(ip)
        tasks.append(bulb.turn_on(PilotBuilder(brightness=brightness)))
        print(f"[LIGHTS] Brightness {brightness}/255 → {name}")
    await asyncio.gather(*tasks)
    pct = int(round(brightness / 255 * 100))
    return f"Set brightness of {device or 'all lights'} to {pct}%."

async def set_color_temp(device=None, color_temp=None, **_):
    # accept warm/cool or raw K values
    K = 3000
    if isinstance(color_temp, str):
        if "warm" in color_temp:
            K = 2700
        elif "cool" in color_temp:
            K = 6000
    elif isinstance(color_temp, (int, float)):
        K = int(color_temp)
    K = max(2200, min(6500, K))
    tasks = []
    for name, ip in _targets(device):
        bulb = wizlight(ip)
        tasks.append(bulb.turn_on(PilotBuilder(colortemp=K)))
        print(f"[LIGHTS] Temp {K}K → {name}")
    await asyncio.gather(*tasks)
    return f"Set color temperature of {device or 'all lights'} to {K}K."
