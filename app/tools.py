import os
import requests
from langchain_core.tools import tool
from exa_py import Exa


def _exa() -> Exa:
    return Exa(os.getenv("EXA_API_KEY"))


@tool
def web_search(query: str) -> str:
    """Search the web for real-time travel information about a destination."""
    try:
        results = _exa().search_and_contents(
            query, num_results=5, text={"max_characters": 600}
        )
        chunks = []
        for r in results.results:
            chunks.append(f"- {r.title}\n  {r.url}\n  {(r.text or '').strip()}")
        return "\n\n".join(chunks) if chunks else "No results found."
    except Exception as e:
        return f"Web search unavailable: {e}"


@tool
def get_weather(destination: str) -> str:
    """Get the current weather and a short forecast for a destination city."""
    try:
        geo = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": destination, "count": 1},
            timeout=10,
        ).json()
        if not geo.get("results"):
            return f"No weather data found for {destination}."
        loc = geo["results"][0]
        fc = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": loc["latitude"],
                "longitude": loc["longitude"],
                "current": "temperature_2m,weather_code",
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                "forecast_days": 5,
                "timezone": "auto",
            },
            timeout=10,
        ).json()
        cur = fc.get("current", {})
        daily = fc.get("daily", {})
        lines = [
            f"Location: {loc['name']}, {loc.get('country', '')}",
            f"Current temperature: {cur.get('temperature_2m')}C",
            "5-day outlook:",
        ]
        for i, day in enumerate(daily.get("time", [])):
            lines.append(
                f"  {day}: {daily['temperature_2m_min'][i]}C-{daily['temperature_2m_max'][i]}C, "
                f"rain {daily['precipitation_probability_max'][i]}%"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Weather lookup unavailable: {e}"


@tool
def allocate_budget(total_budget: float, days: int, travelers: int) -> dict:
    """Split a total trip budget across lodging, food, activities, transport, and a buffer."""
    days = max(days, 1)
    weights = {
        "lodging": 0.40,
        "food": 0.25,
        "activities": 0.20,
        "local_transport": 0.10,
        "buffer": 0.05,
    }
    breakdown = {k: round(total_budget * w, 2) for k, w in weights.items()}
    return {
        "total_budget": round(total_budget, 2),
        "travelers": travelers,
        "days": days,
        "per_day": round(total_budget / days, 2),
        "per_person": round(total_budget / max(travelers, 1), 2),
        "breakdown": breakdown,
    }


@tool
def generate_packing_list(destination: str, interests: list[str], season: str = "") -> list[str]:
    """Generate a packing list tailored to a destination, interests, and season."""
    base = [
        "Passport / ID",
        "Phone and charger",
        "Travel adapter",
        "Reusable water bottle",
        "Basic medication and first-aid",
        "Comfortable walking shoes",
    ]
    season = (season or "").lower()
    if "winter" in season or "cold" in season:
        base += ["Warm jacket", "Gloves and beanie", "Thermal layers"]
    elif "summer" in season or "hot" in season:
        base += ["Sunscreen", "Sunglasses", "Light breathable clothing", "Hat"]
    else:
        base += ["Light jacket", "Layered clothing"]
    joined = " ".join(interests).lower()
    if "beach" in joined:
        base += ["Swimwear", "Beach towel"]
    if "hiking" in joined or "nature" in joined:
        base += ["Daypack", "Trekking shoes"]
    if "photography" in joined:
        base += ["Camera and spare batteries"]
    return base
