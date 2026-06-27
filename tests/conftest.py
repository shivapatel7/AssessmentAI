"""
Shared pytest fixtures for the AI Travel Planner test suite.
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app, _plans


@pytest.fixture(autouse=True)
def clear_plans():
    """Reset the in-memory plan store before each test to ensure isolation."""
    _plans.clear()
    yield
    _plans.clear()


@pytest.fixture
def client():
    """Provide a FastAPI TestClient."""
    return TestClient(app)


@pytest.fixture
def sample_request():
    """A standard, valid travel request payload."""
    return {
        "destination": "London",
        "start_date": "2026-08-01",
        "end_date": "2026-08-05",
        "budget_min": 1500,
        "budget_max": 2500,
        "interests": ["history", "museums"],
        "travelers": 2,
    }


@pytest.fixture
def created_plan(client, sample_request):
    """Creates a plan and returns the full response body (includes plan_id)."""
    resp = client.post("/plan", json=sample_request)
    assert resp.status_code == 201, f"Setup failed: {resp.text}"
    return resp.json()
