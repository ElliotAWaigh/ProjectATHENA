import asyncio
from pywizlight import wizlight, PilotBuilder

TOOL_SPEC = {
    "intent": "light_control",
    "description": "Control WizLights (on/off/brightness/temp)",
    "commands": {
        "turn_on": {
            "examples": ["turn on", "switch on", "turn on my lights", "lights on", "illuminate"],
            "params": ["device"],
            "function": "turn_on"
        },
        "turn_off": {
            "examples": ["turn off", "switch off", "turn off my lights", "lights off", "kill lights"],
            "params": ["device"],
            "function": "turn_off"
        },
        "set_brightness": {
            "examples": [
                "dim lights", "brighten", "set brightness", "make it brighter",
                "increase brightness", "decrease brightness",
                "make my lights dimmer", "make my lights brighter"
            ],
            "params": ["device", "brightness"],
            "function": "set_brightness"
        },
        "set_color_temp": {
            "examples": ["make it warmer", "make it cooler", "set color temperature", "change tone"],
            "params": ["device", "color_temp"],
            "function": "set_color_temp"
        }
    }
}

# ----------------------------- DEVICE MAP -----------------------------
DEVICE_IPS = {
    "bottom lamp light": "192.168.0.153",
    "middle lamp light": "192.168.0.91",
    "mushroom light": "192.168.0.228",
    "top lamp light": "192.168.0.149"
}

# ----------------------------- HELPERS -----------------------------
def _normalize_brightness(value):
    """Convert brightness from 0–100% to 10–255 (Wiz range)."""
    try:
        val = int(value)
        val = max(0, min(100, val))
        return int(val * 2.55)
    except Exception:
        return 255

async def _get_bulbs(target_device=None):
    """Return list of (name, wizlight) pairs filtered by device name."""
    bulbs = []
    for name, ip in DEVICE_IPS.items():
        if not target_device or target_device.lower() in name:
            bulbs.append((name, wizlight(ip)))
    return bulbs

# ----------------------------- COMMANDS -----------------------------
async def turn_on(device=None, **_):
    bulbs = await _get_bulbs(device)
    tasks = []
    for name, bulb in bulbs:
        tasks.append(bulb.turn_on(PilotBuilder()))
        print(f"[LIGHTS] ON → {name}")
    await asyncio.gather(*tasks)
    return f"Turning on {device or 'all lights'}."

async def turn_off(device=None, **_):
    bulbs = await _get_bulbs(device)
    tasks = []
    for name, bulb in bulbs:
        tasks.append(bulb.turn_on(PilotBuilder(state=False)))  # ✅ Corrected off command
        print(f"[LIGHTS] OFF → {name}")
    await asyncio.gather(*tasks)
    return f"Turning off {device or 'all lights'}."

async def set_brightness(device=None, brightness=None, **_):
    if not brightness:
        return "Missing brightness value."
    brightness = _normalize_brightness(brightness)
    bulbs = await _get_bulbs(device)
    tasks = []
    for name, bulb in bulbs:
        tasks.append(bulb.turn_on(PilotBuilder(brightness=brightness)))
        print(f"[LIGHTS] Brightness {brightness}/255 → {name}")
    await asyncio.gather(*tasks)
    return f"Set brightness of {device or 'all lights'} to {int(brightness/2.55)}%."

async def set_color_temp(device=None, color_temp=None, **_):
    if not color_temp:
        return "Missing color temperature."
    temp = 2200 if "warm" in color_temp else 6000
    bulbs = await _get_bulbs(device)
    tasks = []
    for name, bulb in bulbs:
        tasks.append(bulb.turn_on(PilotBuilder(colortemp=temp)))
        print(f"[LIGHTS] ColorTemp {temp}K → {name}")
    await asyncio.gather(*tasks)
    return f"Set color temperature of {device or 'all lights'} to {color_temp}."

# ----------------------------- PARAM RESOLUTION -----------------------------
def resolve_params(text):
    """Extract device names from user input."""
    text = text.lower()
    for name in DEVICE_IPS.keys():
        if name in text:
            return {"device": name}
    return {}
