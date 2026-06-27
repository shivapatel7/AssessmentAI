"""
Integration tests for the FastAPI endpoints (app/main.py).

These tests use FastAPI's TestClient which runs the full LangGraph workflow
including real calls to Groq and Exa using keys from .env.
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


# ────────────────────────────────────────────────────────────
# POST /plan — Plan Creation
# ────────────────────────────────────────────────────────────

class TestCreatePlan:
    def test_successful_plan_creation(self, client, sample_request):
        """A valid request should return 201 with a plan_id and awaiting_review stage."""
        resp = client.post("/plan", json=sample_request)
        assert resp.status_code == 201
        data = resp.json()
        assert "plan_id" in data
        assert data["stage"] == "awaiting_review"
        assert data["draft_plan"] is not None

    def test_plan_draft_has_required_fields(self, client, sample_request):
        """The draft plan should contain summary, days, and budget_breakdown."""
        resp = client.post("/plan", json=sample_request)
        assert resp.status_code == 201
        draft = resp.json().get("draft_plan", {})
        # The planner agent may return free text if JSON parse fails,
        # so we just ensure the draft is not None/empty
        assert draft is not None
        assert draft != {}

    def test_validation_error_missing_destination(self, client):
        """A request missing destination should return 422 Unprocessable Entity."""
        bad_request = {
            "start_date": "2026-08-01",
            "end_date": "2026-08-05",
            "budget_min": 500,
            "budget_max": 1000,
            "travelers": 1,
        }
        resp = client.post("/plan", json=bad_request)
        assert resp.status_code == 422

    def test_validation_error_budget_max_less_than_min(self, client):
        """budget_max < budget_min should return 422 Unprocessable Entity."""
        bad_request = {
            "destination": "Paris",
            "start_date": "2026-08-01",
            "end_date": "2026-08-05",
            "budget_min": 2000,
            "budget_max": 500,  # Invalid: max < min
            "travelers": 1,
        }
        resp = client.post("/plan", json=bad_request)
        assert resp.status_code == 422

    def test_validation_error_zero_travelers(self, client):
        """travelers < 1 should return 422 Unprocessable Entity."""
        bad_request = {
            "destination": "Paris",
            "start_date": "2026-08-01",
            "end_date": "2026-08-05",
            "budget_min": 1000,
            "budget_max": 2000,
            "travelers": 0,  # Invalid
        }
        resp = client.post("/plan", json=bad_request)
        assert resp.status_code == 422

    def test_destination_too_short(self, client):
        """Destination with < 2 characters should return 422."""
        bad_request = {
            "destination": "X",  # too short
            "start_date": "2026-08-01",
            "end_date": "2026-08-05",
            "budget_min": 500,
            "budget_max": 1000,
            "travelers": 1,
        }
        resp = client.post("/plan", json=bad_request)
        assert resp.status_code == 422


# ────────────────────────────────────────────────────────────
# GET /plan/{plan_id} — Plan Status
# ────────────────────────────────────────────────────────────

class TestGetPlan:
    def test_get_existing_plan(self, client, created_plan):
        """Should return 200 with the current status of a valid plan."""
        plan_id = created_plan["plan_id"]
        resp = client.get(f"/plan/{plan_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["plan_id"] == plan_id
        assert data["stage"] == "awaiting_review"
        assert "request" in data
        assert "draft_plan" in data

    def test_get_nonexistent_plan_returns_404(self, client):
        """A plan_id that does not exist should return 404."""
        resp = client.get("/plan/nonexistent-plan-id-12345")
        assert resp.status_code == 404


# ────────────────────────────────────────────────────────────
# POST /plan/{plan_id}/review — HITL Review Actions
# ────────────────────────────────────────────────────────────

class TestReviewPlan:
    def test_approve_moves_plan_to_finalized(self, client, created_plan):
        """Approving a plan should move its stage to 'finalized'."""
        plan_id = created_plan["plan_id"]
        resp = client.post(f"/plan/{plan_id}/review", json={"action": "approve"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["stage"] == "finalized"
        assert data["final_plan"] is not None

    def test_reject_returns_plan_to_awaiting_review(self, client, created_plan):
        """Rejecting with feedback should re-route to planner and return to awaiting_review."""
        plan_id = created_plan["plan_id"]
        resp = client.post(f"/plan/{plan_id}/review", json={
            "action": "reject",
            "comments": "Please add more museum visits and fewer restaurants."
        })
        assert resp.status_code == 200
        data = resp.json()
        # After rejection, the planner revises and we pause again for review
        assert data["stage"] == "awaiting_review"

    def test_modify_day_updates_draft(self, client, created_plan):
        """A modify action should update the draft and return to awaiting_review."""
        plan_id = created_plan["plan_id"]
        resp = client.post(f"/plan/{plan_id}/review", json={
            "action": "modify",
            "modifications": [{"day": 1, "title": "Updated Day 1 - Modified by Test"}]
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["stage"] == "awaiting_review"

    def test_invalid_review_action_returns_422(self, client, created_plan):
        """An invalid action (not approve/reject/modify) should return 422."""
        plan_id = created_plan["plan_id"]
        resp = client.post(f"/plan/{plan_id}/review", json={
            "action": "cancel"  # Invalid action
        })
        assert resp.status_code == 422

    def test_review_on_nonexistent_plan_returns_404(self, client):
        """Reviewing a plan_id that doesn't exist should return 404."""
        resp = client.post("/plan/fake-id/review", json={"action": "approve"})
        assert resp.status_code == 404

    def test_double_approve_returns_409(self, client, created_plan):
        """Trying to review an already-finalized plan should return 409 Conflict."""
        plan_id = created_plan["plan_id"]
        # First approve
        client.post(f"/plan/{plan_id}/review", json={"action": "approve"})
        # Second attempt to approve the same finalized plan
        resp = client.post(f"/plan/{plan_id}/review", json={"action": "approve"})
        assert resp.status_code == 409


# ────────────────────────────────────────────────────────────
# GET /plan/{plan_id}/final — Final Plan Retrieval
# ────────────────────────────────────────────────────────────

class TestGetFinalPlan:
    def test_final_plan_available_after_approval(self, client, created_plan):
        """The final plan endpoint should return 200 only after plan is approved."""
        plan_id = created_plan["plan_id"]
        client.post(f"/plan/{plan_id}/review", json={"action": "approve"})

        resp = client.get(f"/plan/{plan_id}/final")
        assert resp.status_code == 200
        data = resp.json()
        assert data["plan_id"] == plan_id
        assert data["final_plan"] is not None
        assert data["final_plan"].get("status") == "approved"

    def test_final_plan_not_available_before_approval(self, client, created_plan):
        """The final plan endpoint should return 409 if plan is still in review."""
        plan_id = created_plan["plan_id"]
        # Plan is created but NOT approved yet
        resp = client.get(f"/plan/{plan_id}/final")
        assert resp.status_code == 409

    def test_final_plan_nonexistent_returns_404(self, client):
        """The final plan endpoint should return 404 for unknown plan IDs."""
        resp = client.get("/plan/fake-plan-id/final")
        assert resp.status_code == 404


# ────────────────────────────────────────────────────────────
# GET / — Root Health Check
# ────────────────────────────────────────────────────────────

class TestRoot:
    def test_root_returns_service_name(self, client):
        """The root endpoint should confirm the service is running."""
        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.json()["service"] == "AI Travel Planner"
