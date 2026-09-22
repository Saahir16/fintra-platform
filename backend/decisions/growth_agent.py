from fastapi import APIRouter, Query
from datetime import datetime
import uuid
import hashlib

router = APIRouter()

# threshold
DEMAND_DROP_THRESHOLD_PERCENT = 0.15  # 15% drop gives alert
MINIMUM_TRANSACTION_FLOOR = 50  # Ignore drops below 50 transactions to prevent false alarms
DEFAULT_SPEND_CAP = 500.00  # Default max campaign budget


def evaluate_demand_drop(current_volume: int, base_volume: int) -> dict:
    if base_volume < MINIMUM_TRANSACTION_FLOOR:
        return {
            "status": "NORMAL",
            "reason": "The volume is below the minimum threshold so no drop",
            "drop_percentage": 0.0
        }

    drop_percent = (base_volume - current_volume) / base_volume

    if drop_percent >= DEMAND_DROP_THRESHOLD_PERCENT:
        return {
            "status": "ALERT_TRIGGERED",
            "reason": f"Demand drop of {round(drop_percent * 100, 2)}% is past threshold of {int(DEMAND_DROP_THRESHOLD_PERCENT * 100)}%.",
            "drop_percentage": round(drop_percent, 4)
        }

    return {
        "status": "NORMAL",
        "reason": "Demand levels within acceptable parameters.",
        "drop_percentage": round(drop_percent, 4)
    }


@router.get("/growth/check-demand")
def check_demand_metrics(
    current_volume: int = Query(default=140),
    base_volume: int = Query(default=200),
    max_spending_cap: float = Query(default=DEFAULT_SPEND_CAP)
):
    """Continuous check endpoint"""
    evaluate_result = evaluate_demand_drop(current_volume, base_volume)
    
    trace_id = f"TRACE-GROWTH-{uuid.uuid4().hex[:8].upper()}"
    timestamp = datetime.utcnow().isoformat()
    
    campaign_status = "INACTIVE"
    allocated_spending = 0.0

    if evaluate_result["status"] == "ALERT_TRIGGERED":
        campaign_status = "TRIGGERED"
        allocated_spending = min(150.00, max_spending_cap)

    log_payload = {
        "trace_id": trace_id,
        "timestamp": timestamp,
        "metrics_evaluated": {
            "base_volume": base_volume,
            "current_volume": current_volume,
            "drop_percentage": evaluate_result["drop_percentage"]
        },
        "evaluation": evaluate_result,
        "action_taken": {
            "campaign_status": campaign_status,
            "allocated_spend": allocated_spending,
            "spend_cap_enforced": max_spending_cap
        }
    }

    # MD5 hash for auditing
    log_hash = hashlib.md5(str(log_payload).encode('utf-8')).hexdigest()
    log_payload["artifact_hash"] = log_hash

    return log_payload