from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt
from app.state import PlanState
from app.agents import run_research, run_planner


def research_node(state: PlanState) -> dict:
    research = run_research(state["request"])
    return {"research": research, "stage": "planning"}


def plan_node(state: PlanState) -> dict:
    draft = run_planner(state["request"], state["research"], state.get("feedback"))
    return {
        "draft_plan": draft,
        "stage": "awaiting_review",
        "revisions": state.get("revisions", 0) + (1 if state.get("feedback") else 0),
    }


def human_review_node(state: PlanState) -> dict:
    feedback = interrupt({"draft_plan": state["draft_plan"]})
    return {"feedback": feedback}


def modify_node(state: PlanState) -> dict:
    draft = dict(state["draft_plan"])
    days = list(draft.get("days", []))
    for mod in state["feedback"].get("modifications") or []:
        if "day" in mod:
            target = mod["day"]
            for i, d in enumerate(days):
                if d.get("day") == target:
                    days[i] = {**d, **{k: v for k, v in mod.items() if k != "day"}}
                    break
        else:
            draft.update(mod)
    draft["days"] = days
    return {"draft_plan": draft, "stage": "awaiting_review"}


def finalize_node(state: PlanState) -> dict:
    final = dict(state["draft_plan"])
    final["status"] = "approved"
    return {"final_plan": final, "stage": "finalized"}


def route_review(state: PlanState) -> str:
    action = state["feedback"].get("action")
    if action == "approve":
        return "finalize"
    if action == "reject":
        return "plan"
    return "modify"


def build_graph():
    g = StateGraph(PlanState)
    g.add_node("research", research_node)
    g.add_node("plan", plan_node)
    g.add_node("human_review", human_review_node)
    g.add_node("modify", modify_node)
    g.add_node("finalize", finalize_node)

    g.add_edge(START, "research")
    g.add_edge("research", "plan")
    g.add_edge("plan", "human_review")
    g.add_conditional_edges(
        "human_review",
        route_review,
        {"finalize": "finalize", "plan": "plan", "modify": "modify"},
    )
    g.add_edge("modify", "human_review")
    g.add_edge("finalize", END)

    return g.compile(checkpointer=MemorySaver())


graph = build_graph()
