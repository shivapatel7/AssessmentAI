"""
Unit tests for app/tools.py

These tests are fast, deterministic, and do NOT make any external API calls.
The web_search and get_weather tools are mocked to isolate the logic.
"""
import pytest
from unittest.mock import patch, MagicMock
from app.tools import allocate_budget, generate_packing_list


# ────────────────────────────────────────────────────────────
# allocate_budget tests
# ────────────────────────────────────────────────────────────

class TestAllocateBudget:
    def test_basic_allocation_sums_to_total(self):
        """All budget categories should sum to exactly the total budget."""
        result = allocate_budget.invoke({"total_budget": 2000, "days": 5, "travelers": 2})
        breakdown = result["breakdown"]
        total = sum(breakdown.values())
        assert abs(total - 2000.0) < 0.01, f"Budget breakdown does not sum to 2000: {total}"

    def test_per_day_calculation(self):
        """Per-day budget should equal total / number of days."""
        result = allocate_budget.invoke({"total_budget": 1000, "days": 5, "travelers": 1})
        assert result["per_day"] == 200.0

    def test_per_person_calculation(self):
        """Per-person budget should equal total / number of travelers."""
        result = allocate_budget.invoke({"total_budget": 3000, "days": 3, "travelers": 3})
        assert result["per_person"] == 1000.0

    def test_zero_days_handled(self):
        """Should handle 0 days gracefully (uses max(days, 1) internally)."""
        result = allocate_budget.invoke({"total_budget": 500, "days": 0, "travelers": 1})
        assert result["per_day"] == 500.0

    def test_breakdown_keys_are_correct(self):
        """Breakdown should always contain the five expected categories."""
        result = allocate_budget.invoke({"total_budget": 1000, "days": 3, "travelers": 1})
        expected_keys = {"lodging", "food", "activities", "local_transport", "buffer"}
        assert set(result["breakdown"].keys()) == expected_keys

    def test_lodging_is_largest_category(self):
        """Lodging (40%) should always be the largest single category."""
        result = allocate_budget.invoke({"total_budget": 2000, "days": 4, "travelers": 2})
        breakdown = result["breakdown"]
        assert breakdown["lodging"] == max(breakdown.values())


# ────────────────────────────────────────────────────────────
# generate_packing_list tests
# ────────────────────────────────────────────────────────────

class TestGeneratePackingList:
    def test_base_items_always_present(self):
        """Core essential items should always appear in every packing list."""
        result = generate_packing_list.invoke({
            "destination": "Anywhere",
            "interests": [],
            "season": ""
        })
        assert "Passport / ID" in result
        assert "Phone and charger" in result
        assert "Reusable water bottle" in result

    def test_winter_season_adds_warm_items(self):
        """Winter keyword should trigger warm clothing suggestions."""
        result = generate_packing_list.invoke({
            "destination": "Norway",
            "interests": [],
            "season": "winter"
        })
        assert "Warm jacket" in result
        assert "Gloves and beanie" in result

    def test_summer_season_adds_sun_items(self):
        """Summer keyword should trigger sun protection suggestions."""
        result = generate_packing_list.invoke({
            "destination": "Barcelona",
            "interests": [],
            "season": "summer"
        })
        assert "Sunscreen" in result
        assert "Sunglasses" in result

    def test_beach_interest_adds_swimwear(self):
        """Beach interest should add swimwear and beach towel."""
        result = generate_packing_list.invoke({
            "destination": "Maldives",
            "interests": ["beach", "snorkeling"],
            "season": ""
        })
        assert "Swimwear" in result
        assert "Beach towel" in result

    def test_hiking_interest_adds_gear(self):
        """Hiking interest should add daypack and trekking shoes."""
        result = generate_packing_list.invoke({
            "destination": "Nepal",
            "interests": ["hiking", "nature"],
            "season": ""
        })
        assert "Daypack" in result
        assert "Trekking shoes" in result

    def test_photography_interest_adds_camera(self):
        """Photography interest should add camera gear."""
        result = generate_packing_list.invoke({
            "destination": "Japan",
            "interests": ["photography", "culture"],
            "season": ""
        })
        assert "Camera and spare batteries" in result


# ────────────────────────────────────────────────────────────
# web_search tool (mocked — avoids real API calls)
# ────────────────────────────────────────────────────────────

class TestWebSearch:
    @patch("app.tools._exa")
    def test_returns_formatted_results(self, mock_exa_factory):
        """Should format Exa results into readable bullet points."""
        from app.tools import web_search
        mock_result = MagicMock()
        mock_result.title = "Top 10 Things to Do in London"
        mock_result.url = "https://example.com/london"
        mock_result.text = "Visit the British Museum and Buckingham Palace."

        mock_exa = MagicMock()
        mock_exa.search_and_contents.return_value.results = [mock_result]
        mock_exa_factory.return_value = mock_exa

        result = web_search.invoke({"query": "London travel tips"})

        assert "Top 10 Things to Do in London" in result
        assert "https://example.com/london" in result
        assert "British Museum" in result

    @patch("app.tools._exa")
    def test_handles_api_failure_gracefully(self, mock_exa_factory):
        """Should return an error string, not raise an exception, on API failure."""
        from app.tools import web_search
        mock_exa_factory.side_effect = Exception("Connection refused")
        result = web_search.invoke({"query": "London travel tips"})
        assert "unavailable" in result.lower() or "error" in result.lower()
