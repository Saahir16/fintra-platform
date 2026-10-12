from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from datetime import datetime
import uuid
import hashlib
from typing import Dict, Any, List, Optional

router = APIRouter()

# data models
class SpendPolicy(BaseModel):
    policy_id: str = Field(default_factory=lambda: f"POL-{uuid.uuid4().hex[:6].upper()}")
    owner_id: str
    max_campaign_spending_cap: float = 500.00   # Max budget per individual campaign
    max_daily_cap: float = 2000.00  # Max total spending across all campaigns per day
    auto_approve_threshold: float = 150.00   # Budget below this is auto approved
    currency: str = "USD"
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

class SpendEvaluationRequest(BaseModel):
    owner_id: str
    proposed_budget: float
    campaign_id: str
    channel: str

# In memory stores
SPEND_POLICIES: Dict[str, SpendPolicy] = {}
SPEND_AUDIT_LOGS: List[Dict[str, Any]] = []
DAILY_SPEND_TRACKER: Dict[str, float] = {}

def get_or_create_policy(owner_id: str) -> SpendPolicy:
    if owner_id not in SPEND_POLICIES:
        SPEND_POLICIES[owner_id] = SpendPolicy(owner_id=owner_id)
    return SPEND_POLICIES[owner_id]

def generate_audit_hash(data: dict) -> str:
    return hashlib.md5(str(data).encode("utf-8")).hexdigest()

# spending enforcement
def evaluate_spend_request(owner_id: str, proposed_budget: float) -> Dict[str, Any]:
    policy = get_or_create_policy(owner_id)
    current_daily_spend = DAILY_SPEND_TRACKER.get(owner_id, 0.0)

    # individual campaign cap violation
    if proposed_budget > policy.max_campaign_spending_cap:
        return {
            "allowed": False, "reason": f"Budget (${proposed_budget}) exceeds single campaign limit of ${policy.max_campaign_spending_cap}.", "cap_type": "SINGLE_CAMPAIGN_CAP_EXCEEDED"
        }
    # cumulative daily cap violation
    if (current_daily_spend + proposed_budget) > policy.max_daily_cap:
        return {
            "allowed": False, "reason": f"Budget (${proposed_budget}) pushes total daily spend (${current_daily_spend + proposed_budget}) over daily limit of ${policy.max_daily_cap}.", "cap_type": "DAILY_CAP_EXCEEDED"
        }
    # auto approved from the system vs manual review from the owner
    needs_review = proposed_budget > policy.auto_approve_threshold

    return {
        "allowed": True, "needs_manual_review": needs_review, "reason": "Spend approved within policy limits.", "cap_type": "APPROVED"
    }

# API endpoints and logging
@router.post("/spend-policy/configure")
def set_spend_policy(policy_data: SpendPolicy):
    SPEND_POLICIES[policy_data.owner_id] = policy_data
    
    event_log = {
        "event_id": f"EVT-POLICY-{uuid.uuid4().hex[:6].upper()}", "event_type": "SPEND_POLICY_UPDATED", "timestamp": datetime.utcnow().isoformat(), "owner_id": policy_data.owner_id, "details": policy_data.dict()
    }
    event_log["audit_hash"] = generate_audit_hash(event_log)
    SPEND_AUDIT_LOGS.append(event_log)
    return {"status": "SUCCESS", "policy": policy_data, "audit_event": event_log}

@router.post("/spend-policy/evaluate")
def evaluate_spend(req: SpendEvaluationRequest):
    result = evaluate_spend_request(req.owner_id, req.proposed_budget)
    
    event_log = {
        "event_id": f"EVT-SPEND-{uuid.uuid4().hex[:6].upper()}", "event_type": "SPEND_EVALUATION", "timestamp": datetime.utcnow().isoformat(), "owner_id": req.owner_id, "campaign_id": req.campaign_id, "proposed_budget": req.proposed_budget, "decision": result["cap_type"], "allowed": result["allowed"]
    }
    event_log["audit_hash"] = generate_audit_hash(event_log)
    SPEND_AUDIT_LOGS.append(event_log)

    if not result["allowed"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail={"error": "SPEND_CAP_VIOLATION", "message": result["reason"], "audit_event": event_log}
        )

    # Record the spending if it's approved
    DAILY_SPEND_TRACKER[req.owner_id] = DAILY_SPEND_TRACKER.get(req.owner_id, 0.0) + req.proposed_budget

    return {
        "status": "APPROVED", "evaluation": result, "current_daily_spend_total": DAILY_SPEND_TRACKER[req.owner_id], "audit_event": event_log
    }

@router.get("/spend-policy/audit-logs")
def get_spend_audit_logs():
    return {"total_events": len(SPEND_AUDIT_LOGS), "events": SPEND_AUDIT_LOGS}