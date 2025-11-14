# Tools/weather.py
import os
import json
import re
import requests
from pathlib import Path

# -------------------------------
# Config / Defaults
# -------------------------------
DEFAULT_CITY = "Brisbane"
WEATHERBIT_BASE = "https://api.weatherbit.io/v2.0"

def _load_api_key():
    """
    Loads Weatherbit API key from credentials.json in the Bot root folder.
    Expected format:
    {
      "weatherbit_api_key": "your_actual_key_here"
    }
    """
    try:
        # Bot root = parent of this file's directory
        bot_root = Path(__file__).resolve().parents[1]
        cred_path = bot_root / "credentials.json"

        if not cred_path.exists():
            print(f"[WEATHER] ⚠️ credentials.json not found at {cred_path}")
            return None

        with open(cred_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        key = data.get("weatherbit_api_key")
        if not key:
            print("[WEATHER] ⚠️ 'weatherbit_api_key' missing in credentials.json")
        return key
    except Exception as e:
        print(f"[WEATHER] ⚠️ Failed to load API key: {e}")
        return None


API_KEY = _load_api_key()

# -------------------------------
# TOOL SPEC (for ToolRegistry/MSP)
# -------------------------------
TOOL_SPEC = {
    "intent": "weather",
    "description": "Get current weather and short forecasts.",
    "commands": {
        "get_weather_now": {
            "examples": [
                "what's the weather",
                "what is the weather",
                "weather right now",
                "what's the weather like outside",
                "what's the weather in brisbane",
                "weather in sydney"
            ],
            "params": ["city"],      # MSP will expect 'city', but we provide it via resolve_params
            "function": "get_weather_now"
        },
        "get_weather_tomorrow": {
            "examples": [
                "what's the weather tomorrow",
                "weather tomorrow",
                "tomorrow's weather",
                "what will the weather be like tomorrow",
                "weather tomorrow in brisbane",
                "what's the weather tomorrow in tokyo",
                "what is the weather tomorrow in sydney"
            ],
            "params": ["city"],
            "function": "get_weather_tomorrow"
        }
        # You can add 3-day forecast later using the same pattern.
    }
}

# -------------------------------
# Core HTTP helpers
# -------------------------------
def _weatherbit_get(endpoint: str, params: dict) -> dict:
    """
    Simple helper to call Weatherbit API.
    """
    if not API_KEY:
        raise RuntimeError("Weatherbit API key not loaded (check credentials.json).")

    params = dict(params or {})
    params["key"] = API_KEY

    url = f"{WEATHERBIT_BASE}/{endpoint}"
    resp = requests.get(url, params=params, timeout=8)
    resp.raise_for_status()
    return resp.json()

# -------------------------------
# Command implementations
# -------------------------------
def get_weather_now(city: str = None, **_) -> str:
    """
    Get current weather for a city.
    If city is None, we fall back to DEFAULT_CITY.
    """
    city = city or DEFAULT_CITY
    try:
        data = _weatherbit_get("current", {"city": city})
        if not data.get("data"):
            return f"I couldn't find weather data for {city}."

        w = data["data"][0]

        display_city = w.get("city_name") or city

        temp = w.get("temp")
        desc = w.get("weather", {}).get("description", "unknown conditions")
        feels = w.get("app_temp")
        return f"It's currently {temp}°C in {display_city}, {desc} (feels like {feels}°C)."
    except Exception as e:
        return f"Error fetching current weather for {city}: {e}"

def get_weather_tomorrow(city: str = None, **_) -> str:
    """
    Get daily forecast for tomorrow (day 2) for a city.
    """
    city = city or DEFAULT_CITY
    try:
        data = _weatherbit_get("forecast/daily", {"city": city, "days": 2})
        if not data.get("data"):
            return f"I couldn't find forecast data for {city}."

        display_city = data.get("city_name") or city

        # index 1 = tomorrow
        tomorrow = data["data"][1]
        max_t = tomorrow.get("max_temp")
        min_t = tomorrow.get("min_temp")
        desc = tomorrow.get("weather", {}).get("description", "unknown conditions")

        return f"Tomorrow in {display_city}: {desc}, between {min_t}°C and {max_t}°C."
    except Exception as e:
        return f"Error fetching forecast for {city}: {e}"

# -------------------------------
# Param resolution (NO hard-coded list in entity_extractor)
# -------------------------------
def resolve_params(text: str, **_) -> dict:
    """
    Extracts 'city' from the user text if present.
    Otherwise falls back to DEFAULT_CITY.

    Examples it handles:
      - "what's the weather in sydney"
      - "weather in melbourne tomorrow"
      - "what's the weather right now"
      - "weather here"

    No massive hard-coded city list – just pattern detection.
    """
    t = text.lower().strip()

    # 1) Explicit "in <city>" pattern
    #    e.g. "what's the weather in sydney", "weather tomorrow in melbourne"
    m = re.search(r"\bin\s+([a-z\s]+)", t)
    if m:
        raw_city = m.group(1)
        # strip trailing keywords like "today", "tomorrow", "now", etc.
        raw_city = re.sub(r"\b(today|tomorrow|now|right now|this (morning|afternoon|evening|weekend))\b", "", raw_city)
        raw_city = raw_city.strip()
        if raw_city:
            city = " ".join(w.capitalize() for w in raw_city.split())
            return {"city": city}

    # 2) "weather in brisbane" / "brisbane weather"
    #    simple fallback for when "in" pattern fails
    m2 = re.search(r"weather\s+(in|for|at)\s+([a-z\s]+)", t)
    if m2:
        raw_city = m2.group(2).strip()
        city = " ".join(w.capitalize() for w in raw_city.split())
        return {"city": city}

    # 3) If user explicitly mentions "brisbane" anywhere
    if "brisbane" in t:
        return {"city": "Brisbane"}

    # 4) Words like "here", "outside" -> interpret as default city
    if any(word in t for word in ["here", "outside", "right now", "my place"]):
        return {"city": DEFAULT_CITY}

    # 5) Fallback: always default city
    return {"city": DEFAULT_CITY}
