import json

from fastapi.testclient import TestClient
from app.main import app
from app.store import store
from app.audit import clear, get_events
from app.harness import Harness
import pytest

client=TestClient(app)
@pytest.fixture(autouse=True)
def reset():
    store.reset(); clear()
    yield

def test_ambiguous_beneficiary():
    r=Harness().initiate("s1","John",10000)
    assert r.status=="NEEDS_CLARIFICATION" and len(r.data["matches"])==2
    assert not store.transactions

def test_blocked_beneficiary():
    r=Harness().initiate("s1","Nick Anderson",25000)
    assert r.status=="REJECTED" and r.data["code"]=="BENEFICIARY_INACTIVE"

def test_negative_amount():
    assert Harness().initiate("s1","John Smith",-1).data["code"]=="INVALID_AMOUNT"

@pytest.mark.parametrize("amount", [float("inf"), float("-inf"), float("nan")])
def test_non_finite_amount(amount):
    result = Harness().initiate("s1", "John Smith", amount)
    assert result.status == "REJECTED"
    assert result.data["code"] == "INVALID_AMOUNT"
    assert result.data["checks"][-1] == {
        "rule": "amount_positive_and_finite",
        "passed": False,
        "code": "INVALID_AMOUNT",
    }
    event = next(event for event in get_events() if event["event"] == "TRANSFER_VALIDATION")
    json.dumps(event, allow_nan=False)

def test_daily_limit():
    assert Harness().initiate("s1","John Smith",80000).data["code"]=="DAILY_LIMIT_EXCEEDED"

def test_identical_pending_transfer_is_rejected_with_decision_trace():
    harness = Harness()
    first = harness.initiate("s1", "John Smith", 10000)
    second = harness.initiate("s1", "John Smith", 10000)

    assert first.status == "PENDING_CONFIRMATION"
    assert second.status == "REJECTED"
    assert second.data["code"] == "DUPLICATE_PENDING_TRANSFER"
    assert second.data["checks"][-1] == {
        "rule": "no_duplicate_pending_transfer",
        "passed": False,
        "code": "DUPLICATE_PENDING_TRANSFER",
    }
    assert len(store.transactions) == 1

def test_pending_transfer_reserves_available_balance():
    store.account.balance = 15000
    harness = Harness()
    assert harness.initiate("s1", "John Smith", 10000).status == "PENDING_CONFIRMATION"

    result = harness.initiate("s1", "Priya Shah", 6000)

    assert result.data["code"] == "INSUFFICIENT_FUNDS"
    assert result.data["available_balance"] == 5000

def test_pending_transfer_reserves_daily_limit():
    store.account.daily_limit = 40000
    harness = Harness()
    assert harness.initiate("s1", "John Smith", 10000).status == "PENDING_CONFIRMATION"

    result = harness.initiate("s1", "Priya Shah", 6000)

    assert result.data["code"] == "DAILY_LIMIT_EXCEEDED"
    assert result.data["daily_exposure"] == 41000

def test_pending_transfers_reserve_session_capacity():
    harness = Harness()
    assert harness.initiate("s1", "John Smith", 10000).status == "PENDING_CONFIRMATION"
    assert harness.initiate("s1", "Priya Shah", 20000).status == "PENDING_CONFIRMATION"

    result = harness.initiate("s1", "John Lewis", 1000)

    assert result.data["code"] == "SESSION_TRANSFER_LIMIT"
    assert result.data["reserved"] == 2

def test_pending_reservation_is_released_as_approved_transfers_complete():
    harness = Harness()
    first = harness.initiate("s1", "John Smith", 10000)
    second = harness.initiate("s1", "Priya Shah", 20000)

    assert harness.approve("s1", first.data["transaction_id"]).status == "COMPLETED"
    assert harness.approve("s1", second.data["transaction_id"]).status == "COMPLETED"

def test_validation_audit_event_includes_ordered_policy_checks():
    result = Harness().initiate("s1", "John Smith", 10000)
    event = next(event for event in get_events() if event["event"] == "TRANSFER_VALIDATION")

    assert result.status == "PENDING_CONFIRMATION"
    assert event["details"]["status"] == "VALIDATED"
    assert event["details"]["checks"] == result.data["checks"]
    assert all(check["passed"] for check in event["details"]["checks"])

def test_requires_approval_and_verifies():
    h=Harness(); r=h.initiate("s1","John Smith",10000)
    assert r.status=="PENDING_CONFIRMATION" and store.account.balance==200000
    done=h.approve("s1",r.data["transaction_id"])
    assert done.status=="COMPLETED" and done.data["verified"] is True
    assert store.account.balance==190000
    assert h.approve("s1",r.data["transaction_id"]).status=="REJECTED"

def test_session_binding():
    h=Harness(); r=h.initiate("s1","John Smith",10000)
    assert h.approve("s2",r.data["transaction_id"]).status=="REJECTED"
    assert store.account.balance==200000

def test_transfer_limit():
    h=Harness()
    for name,amount in [("John Smith",10000),("Priya Shah",20000)]:
        r=h.initiate("s1",name,amount)
        assert h.approve("s1",r.data["transaction_id"]).status=="COMPLETED"
    r=h.initiate("s1","John Smith",1000)
    assert r.status=="REJECTED" and r.data["code"]=="SESSION_TRANSFER_LIMIT"

def test_chat_api():
    r=client.post("/api/chat",json={"session_id":"api","message":"What is my balance?"})
    assert r.status_code==200 and "200,000" in r.json()["answer"]
