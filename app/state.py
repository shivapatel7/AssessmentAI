from typing import TypedDict, Optional, Any
from pydantic import BaseModel, Field, field_validator


class TravelRequest(BaseModel):
    destination: str = Field(..., min_length=2)
    start_date: str
    end_date: str
    budget_min: float = Field(..., ge=0)
    budget_max: float = Field(..., ge=0)
    interests: list[str] = Field(default_factory=list)
    travelers: int = Field(..., ge=1)

    @field_validator("budget_max")
    @classmethod
    def check_budget(cls, v, info):
        if "budget_min" in info.data and v < info.data["budget_min"]:
            raise ValueError("budget_max must be >= budget_min")
        return v


class ReviewRequest(BaseModel):
    action: str
    comments: Optional[str] = None
    modifications: Optional[list[dict]] = None

    @field_validator("action")
    @classmethod
    def check_action(cls, v):
        if v not in ("approve", "reject", "modify"):
            raise ValueError("action must be one of: approve, reject, modify")
        return v


class PlanState(TypedDict):
    request: dict
    research: str
    draft_plan: dict
    feedback: dict
    final_plan: dict
    stage: str
    revisions: int
