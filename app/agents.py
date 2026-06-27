import json
import re
from langgraph.prebuilt import create_react_agent
from app.llm import get_llm
from app.tools import web_search, get_weather, allocate_budget, generate_packing_list


_agents: dict = {}


def _research_agent():
    if "research" not in _agents:
        _agents["research"] = create_react_agent(get_llm(), tools=[web_search, get_weather])
    return _agents["research"]


def _planner_agent():
    if "planner" not in _agents:
        _agents["planner"] = create_react_agent(
            get_llm(), tools=[allocate_budget, generate_packing_list]
        )
    return _agents["planner"]


def _last_text(result) -> str:
    return result["messages"][-1].content


def _run_agent(agent, prompt: str, attempts: int = 3) -> str:
    last_error = None
    for _ in range(attempts):
        try:
            return _last_text(agent.invoke({"messages": [("user", prompt)]}))
        except Exception as e:
            last_error = e
    fallback = (
        f"{prompt}\n\nThe tools are unavailable right now. "
        "Answer directly from your own knowledge instead."
    )
    try:
        return get_llm().invoke(fallback).content
    except Exception:
        raise last_error


def _parse_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return {"summary": text, "days": [], "notes": "Plan returned as free text."}


def run_research(request: dict) -> str:
    prompt = (
        f"You are a travel research agent. Research a trip to {request['destination']} "
        f"from {request['start_date']} to {request['end_date']} for {request['travelers']} "
        f"traveler(s) interested in {', '.join(request['interests']) or 'general sightseeing'}.\n"
        "Use the web_search tool for attractions, local tips, safety, and seasonal advice, "
        "and the get_weather tool for the forecast. "
        "Summarize your findings as concise bullet points covering attractions, food, safety, "
        "weather, and the best areas to stay."
    )
    return _run_agent(_research_agent(), prompt)


def run_planner(request: dict, research: str, feedback: dict | None = None) -> dict:
    revision_note = ""
    if feedback and feedback.get("comments"):
        revision_note = (
            f"\nThis is a REVISION. The reviewer rejected the previous plan with this "
            f"feedback: {feedback['comments']}. Address it directly."
        )
    budget_mid = (request["budget_min"] + request["budget_max"]) / 2
    prompt = (
        f"You are an itinerary planning agent. Build a day-by-day plan for a trip to "
        f"{request['destination']} from {request['start_date']} to {request['end_date']} "
        f"for {request['travelers']} traveler(s), budget around {budget_mid} "
        f"(range {request['budget_min']}-{request['budget_max']}), interests: "
        f"{', '.join(request['interests']) or 'general sightseeing'}.\n\n"
        f"Research findings:\n{research}\n"
        f"{revision_note}\n\n"
        "Use the allocate_budget tool to split the budget and the generate_packing_list tool "
        "for packing suggestions. Then respond with ONLY a JSON object of this shape:\n"
        "{\n"
        '  "summary": "one paragraph overview",\n'
        '  "days": [{"day": 1, "date": "YYYY-MM-DD", "title": "...", '
        '"activities": ["..."], "meals": ["..."], "estimated_cost": 0}],\n'
        '  "budget_breakdown": {},\n'
        '  "packing_list": ["..."],\n'
        '  "notes": "safety and seasonal notes"\n'
        "}\n"
        "Return valid JSON only, no markdown fences, no extra text."
    )
    return _parse_json(_run_agent(_planner_agent(), prompt))
