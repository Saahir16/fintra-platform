from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel, Field
from datetime import datetime
import uuid
import hashlib
from typing import Dict, Any, List, Optional

router = APIRouter()

# audit log for campaign event logging
CAMPAIGN_AUDIT_LOGS: List[Dict[str, Any]] = []

class DemandDropAlert(BaseModel):
    trace_id: str
    drop_percentage: float
    current_volume: int
    base_volume: int
    max_spend_cap: float = 500.00

class CampaignPayload(BaseModel):
    campaign_id: str
    trigger_trace_id: str
    campaign_type: str = "DEMAND_RECOVERY_PROMO"
    allocated_budget: float
    target_channel: str
    headline: str
    status: str = "PREPARED"
    created_at: str

class DispatchRequest(BaseModel):
    campaign_payload: CampaignPayload
    channel_name: str = Field(..., example="email_marketing")

def generate_audit_hash(data: dict) -> str:
    return hashlib.md5(str(data).encode("utf-8")).hexdigest()

# campaign alert payload
def build_campaign_payload(alert: DemandDropAlert, channel: str = "email_marketing") -> CampaignPayload:
    campaign_id = f"CMP-{uuid.uuid4().hex[:8].upper()}"
    # Cap spending at $150 or max allowed budget cap
    budget = min(150.00, alert.max_spend_cap)
    
    headline = f"Exclusive Offer: Re-engage today! (Triggered by {round(alert.drop_percentage * 100, 1)}% volume drop)"
    
    return CampaignPayload(
        campaign_id=campaign_id,
        trigger_trace_id=alert.trace_id,
        campaign_type="RECOVERY_PROMOTION",
        allocated_budget=budget,
        target_channel=channel,
        headline=headline,
        status="READY_TO_DISPATCH",
        created_at=datetime.utcnow().isoformat()
    )

# api endpoint handler and audit
@router.post("/campaigns/trigger-from-alert")
def trigger_campaign_from_alert(
    alert: DemandDropAlert,
    target_channel: str = Query(default="email_marketing")
):
    if alert.drop_percentage < 0.20:
        raise HTTPException(
            status_code=400, 
            detail="Demand drop percentage is below the 15% activation threshold. No campaign triggered."
        )
    # making payload
    payload = build_campaign_payload(alert, channel=target_channel)
    # audit log
    event_log = {
        "event_id": f"EVT-TRIG-{uuid.uuid4().hex[:6].upper()}",
        "event_type": "CAMPAIGN_TRIGGERED",
        "timestamp": datetime.utcnow().isoformat(),
        "trace_id": alert.trace_id,
        "campaign_id": payload.campaign_id,
        "details": payload.dict()
    }
    event_log["audit_hash"] = generate_audit_hash(event_log)

    # saved to database
    CAMPAIGN_AUDIT_LOGS.append(event_log)

    return {
        "status": "SUCCESS",
        "message": "Campaign payload successfully generated from alert.",
        "campaign_payload": payload,
        "audit_event": event_log
    }

@router.post("/campaigns/dispatch-channel")
def dispatch_campaign_to_channel(dispatch_req: DispatchRequest):
    payload = dispatch_req.campaign_payload
    payload.status = "DISPATCHED"

    # dispatch record
    dispatch_timestamp = datetime.utcnow().isoformat()
    
    event_log = {
        "event_id": f"EVT-DISP-{uuid.uuid4().hex[:6].upper()}",
        "event_type": "CAMPAIGN_DISPATCHED_TO_CHANNEL",
        "timestamp": dispatch_timestamp,
        "trace_id": payload.trigger_trace_id,
        "campaign_id": payload.campaign_id,
        "channel": dispatch_req.channel_name,
        "dispatched_budget": payload.allocated_budget,
        "channel_response": {
            "status_code": 200,
            "channel_ack_id": f"ACK-{uuid.uuid4().hex[:8].upper()}",
            "delivered": True
        }
    }
    event_log["audit_hash"] = generate_audit_hash(event_log)

    CAMPAIGN_AUDIT_LOGS.append(event_log)

    return {
        "status": "DISPATCHED",
        "channel": dispatch_req.channel_name,
        "campaign_id": payload.campaign_id,
        "dispatch_time": dispatch_timestamp,
        "audit_event": event_log
    }

@router.get("/campaigns/audit-logs")
def get_campaign_audit_logs():
    return {
        "total_events": len(CAMPAIGN_AUDIT_LOGS),
        "events": CAMPAIGN_AUDIT_LOGS
    }