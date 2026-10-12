import pytest
from fastapi import HTTPException
from backend.decisions.spending_cap import (
    SpendPolicy,
    SPEND_POLICIES,
    DAILY_SPEND_TRACKER,
    evaluate_spend_request,
)

@pytest.fixture(autouse=True)
def clear_stores():
    # resetting memory stores
    SPEND_POLICIES.clear()
    DAILY_SPEND_TRACKER.clear()
    yield

def test_spend_within_limits():
    # standard budget under limits should pass
    owner_id = "owner_test_1"
    SPEND_POLICIES[owner_id] = SpendPolicy(
        owner_id=owner_id,
        max_campaign_spending_cap=500.0,
        max_daily_cap=2000.0,
        auto_approve_threshold=150.0
    )

    result = evaluate_spend_request(owner_id=owner_id, proposed_budget=100.0)
    assert result["allowed"] is True
    assert result["cap_type"] == "APPROVED"

def test_single_campaign_cap_violation():
    # requesting a budget higher than the single campaign cap should fail
    owner_id = "owner_test_2"
    SPEND_POLICIES[owner_id] = SpendPolicy(
        owner_id=owner_id,
        max_campaign_spending_cap=200.0,
        max_daily_cap=2000.0
    )

    result = evaluate_spend_request(owner_id=owner_id, proposed_budget=250.0)
    assert result["allowed"] is False
    assert result["cap_type"] == "SINGLE_CAMPAIGN_CAP_EXCEEDED"

def test_daily_aggregate_cap_violation():
    # cumulative spending across multiple campaigns should trigger daily limit
    owner_id = "owner_test_3"
    SPEND_POLICIES[owner_id] = SpendPolicy(
        owner_id=owner_id,
        max_campaign_spending_cap=1000.0,
        max_daily_cap=300.0
    )

    # First campaign takes up $250
    DAILY_SPEND_TRACKER[owner_id] = 250.0

    # Second campaign tries to add 100 dollars which is over the limit
    result = evaluate_spend_request(owner_id=owner_id, proposed_budget=100.0)
    assert result["allowed"] is False
    assert result["cap_type"] == "DAILY_CAP_EXCEEDED"