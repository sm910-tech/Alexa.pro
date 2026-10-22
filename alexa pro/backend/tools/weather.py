"""
tools/weather.py — Retrieve weather from Open-Meteo (free, no API key required)
                   or Open-Meteo + IP geolocation for auto-location.

Falls back to clearly-labelled demo data if any network call fails.

Open-Meteo: https://open-meteo.com/  (free, no API key)
ip-api.com:  https://ip-api.com/      (free tier, 45 req/min)
"""

import os
import logging
import httpx

log = logging.getLogger(__name__)

# WMO Weather Codes → (emoji, description)
WMO_CODES: dict[int, tuple[str, str]] = {
    0:  ("☀️",  "Clear sky"),
    1:  ("🌤",  "Mainly clear"),
    2:  ("⛅",  "Partly cloudy"),
    3:  ("☁️",  "Overcast"),
    45: ("🌫",  "Foggy"),
    48: ("🌫",  "Icy fog"),
    51: ("🌦",  "Light drizzle"),
    53: ("🌦",  "Drizzle"),
    55: ("🌧",  "Heavy drizzle"),
    61: ("🌧",  "Slight rain"),
    63: ("🌧",  "Rain"),
    65: ("🌧",  "Heavy rain"),
    71: ("🌨",  "Slight snow"),
    73: ("❄️",  "Snow"),
    75: ("❄️",  "Heavy snow"),
    80: ("🌦",  "Rain showers"),
    81: ("🌧",  "Heavy showers"),
    85: ("🌨",  "Snow showers"),
    95: ("⛈",  "Thunderstorm"),
    99: ("⛈",  "Severe thunderstorm"),
}

DEMO_DATA = {
    "icon":        "⛅",
    "temp":        "22°C",
    "description": "Partly cloudy (demo data — add location for live weather)",
    "location":    "Demo City",
    "extra":       "Humidity: 60%  ·  Wind: 12 km/h",
    "demo":        True,
}


async def get_weather(lat: float | None = None, lon: float | None = None) -> dict:
    """
    Return a weather dict ready for the frontend.

    If lat/lon are not provided, attempts to detect location via ip-api.com.
    Falls back to demo data on any failure.
    """
    # Allow override via environment variables (useful in production)
    lat = lat or _env_float("WEATHER_LAT")
    lon = lon or _env_float("WEATHER_LON")

    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            # ── Auto-locate if no coords supplied ──
            if lat is None or lon is None:
                lat, lon, city = await _geolocate(client)
            else:
                city = os.getenv("WEATHER_CITY", "Your Location")

            # ── Fetch from Open-Meteo ──
            url = (
                "https://api.open-meteo.com/v1/forecast"
                f"?latitude={lat}&longitude={lon}"
                "&current_weather=true"
                "&hourly=relativehumidity_2m,windspeed_10m"
                "&forecast_days=1"
                "&timezone=auto"
            )
            res = await client.get(url)
            res.raise_for_status()
            data = res.json()

        cw   = data["current_weather"]
        code = int(cw.get("weathercode", 2))
        icon, desc = WMO_CODES.get(code, ("⛅", "Unknown"))

        temp_c  = round(cw["temperature"])
        wind    = round(cw["windspeed"])

        # Humidity from first hourly entry
        humidity = None
        try:
            humidity = data["hourly"]["relativehumidity_2m"][0]
        except (KeyError, IndexError):
            pass

        extra = f"Wind: {wind} km/h"
        if humidity is not None:
            extra = f"Humidity: {humidity}%  ·  {extra}"

        return {
            "icon":        icon,
            "temp":        f"{temp_c}°C",
            "description": desc,
            "location":    city,
            "extra":       extra,
            "demo":        False,
        }

    except Exception as exc:
        log.warning("Weather fetch failed (%s) — returning demo data", exc)
        return DEMO_DATA.copy()


# ── Helpers ───────────────────────────────────────────────────────

async def _geolocate(client: httpx.AsyncClient) -> tuple[float, float, str]:
    """Return (lat, lon, city) using ip-api.com's free endpoint."""
    res  = await client.get("http://ip-api.com/json/?fields=lat,lon,city,status")
    data = res.json()
    if data.get("status") == "success":
        return data["lat"], data["lon"], data.get("city", "Your Location")
    raise RuntimeError("Geolocation failed")


def _env_float(key: str) -> float | None:
    try:
        return float(os.environ[key])
    except (KeyError, ValueError):
        return None
