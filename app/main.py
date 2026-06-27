import uuid
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.state import TravelRequest, ReviewRequest
from app.graph import graph

app = FastAPI(title="AI Travel Planner")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_plans: set[str] = set()


def _config(plan_id: str) -> dict:
    return {"configurable": {"thread_id": plan_id}}


def _snapshot(plan_id: str):
    if plan_id not in _plans:
        raise HTTPException(status_code=404, detail="Plan not found")
    return graph.get_state(_config(plan_id))


def _stage(snapshot) -> str:
    values = snapshot.values
    if snapshot.next:
        return "awaiting_review"
    if values.get("final_plan"):
        return "finalized"
    return values.get("stage", "processing")


@app.post("/plan", status_code=201)
def create_plan(req: TravelRequest):
    plan_id = str(uuid.uuid4())
    _plans.add(plan_id)
    graph.invoke(
        {"request": req.model_dump(), "stage": "research", "revisions": 0},
        _config(plan_id),
    )
    snapshot = graph.get_state(_config(plan_id))
    return {
        "plan_id": plan_id,
        "stage": _stage(snapshot),
        "draft_plan": snapshot.values.get("draft_plan"),
    }


@app.get("/plan/{plan_id}")
def get_plan(plan_id: str):
    snapshot = _snapshot(plan_id)
    values = snapshot.values
    return {
        "plan_id": plan_id,
        "stage": _stage(snapshot),
        "request": values.get("request"),
        "research": values.get("research"),
        "draft_plan": values.get("draft_plan"),
        "revisions": values.get("revisions", 0),
    }


@app.post("/plan/{plan_id}/review")
def review_plan(plan_id: str, review: ReviewRequest):
    snapshot = _snapshot(plan_id)
    if not snapshot.next:
        raise HTTPException(status_code=409, detail="Plan is not awaiting review")
    from langgraph.types import Command

    graph.invoke(Command(resume=review.model_dump()), _config(plan_id))
    updated = graph.get_state(_config(plan_id))
    return {
        "plan_id": plan_id,
        "stage": _stage(updated),
        "draft_plan": updated.values.get("draft_plan"),
        "final_plan": updated.values.get("final_plan"),
    }


@app.get("/plan/{plan_id}/final")
def get_final(plan_id: str):
    snapshot = _snapshot(plan_id)
    final = snapshot.values.get("final_plan")
    if not final:
        raise HTTPException(status_code=409, detail="Final plan not available until approved")
    return {"plan_id": plan_id, "final_plan": final}


@app.get("/")
def root():
    return {"service": "AI Travel Planner", "docs": "/docs"}
