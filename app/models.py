from datetime import datetime, timezone
from pydantic import BaseModel, Field
import uuid

def now():
    return datetime.now(timezone.utc).isoformat()

def new_id(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:10].upper()}"

class Beneficiary(BaseModel):
    id: str
    name: str
    suffix: str
    active: bool = True

class Account(BaseModel):
    id: str = "ACC-001"
    name: str = "Everyday Savings"
    balance: float = 200000
    active: bool = True
    daily_limit: float = 100000
    transferred_today: float = 25000

class Transaction(BaseModel):
    id: str
    session_id: str
    beneficiary_id: str
    beneficiary: str
    suffix: str
    amount: float
    status: str = "AWAITING_APPROVAL"
    created_at: str = Field(default_factory=now)
    updated_at: str = Field(default_factory=now)
    approval_used: bool = False
    verification_message: str | None = None

class Session(BaseModel):
    id: str
    completed_count: int = 0
    pending_ids: list[str] = Field(default_factory=list)
    previous_response_id: str | None = None

class Result(BaseModel):
    status: str
    message: str
    data: dict = Field(default_factory=dict)
