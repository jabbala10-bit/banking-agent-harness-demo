from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from . import audit
from .agent import get_agent
from .config import MAX_TRANSFERS_PER_SESSION
from .harness import Harness
from .store import store

app=FastAPI(title="Banking Agent Harness Demo",version="1.0.0")

agent,agent_mode=get_agent()

harness=Harness()

static=Path(__file__).parent/"static"

class ChatRequest(BaseModel):
    session_id: str=Field(min_length=1,max_length=100)
    message: str=Field(min_length=1,max_length=2000)
class SessionRequest(BaseModel):
    session_id: str=Field(min_length=1,max_length=100)

@app.get("/")
def index(): return FileResponse(static/"index.html")

@app.get("/api/health")
def health(): 
    return {
        "status":"ok",
        "agent_mode":agent_mode
    }

@app.post("/api/chat")
def chat(req:ChatRequest):
    store.session(req.session_id)
    audit.emit(
        "USER_MESSAGE",
        req.session_id,
        details={
            "message_length":len(req.message)
        }
    )
    answer=agent.reply(req.session_id,req.message)
    pending=[t.model_dump() for t in store.transaction_list(req.session_id) if t.status=="AWAITING_APPROVAL"]
    return {
        "answer":answer,
        "pending_transactions":pending,
        "agent_mode":agent_mode,
        "state":state_data(req.session_id)
    }

@app.post("/api/transactions/{tid}/approve")
def approve(tid:str,req:SessionRequest):
    result=harness.approve(req.session_id,tid)
    audit.emit(
        "APPROVAL_ENDPOINT_RESULT",
        req.session_id,tid,
        {
            "status":result.status
        }
    )
    return {
        "result":result.model_dump(),
        "state":state_data(req.session_id)
    }

@app.post("/api/transactions/{tid}/reject")
def reject(tid:str,req:SessionRequest):
    result=harness.reject(req.session_id,tid)
    audit.emit(
        "REJECTION_ENDPOINT_RESULT",
        req.session_id,tid,
        {
            "status":result.status
        }
    )
    return {
        "result":result.model_dump(),
        "state":state_data(req.session_id)
    }

@app.get("/api/state")
def state(session_id:str="demo-session"): 
    return state_data(session_id)

@app.get("/api/audit")
def audit_events(limit:int=100): 
    return {
        "events":audit.get_events(max(1,min(limit,500)))
    }

@app.post("/api/reset")
def reset():
    store.reset(); audit.clear()
    return {
        "status":"reset",
        "agent_mode":agent_mode
    }

def state_data(sid):
    s=store.session(sid); a=store.account
    return {
        "account":{
            "name":a.name,
            "balance":a.balance,
            "daily_limit":a.daily_limit,
            "transferred_today":a.transferred_today
        },
        "session":{
            "id":sid,
            "transfers_completed":s.completed_count,
            "max_transfers":MAX_TRANSFERS_PER_SESSION
        },
        "transactions":[t.model_dump() for t in store.transaction_list(sid)],
        "beneficiaries":[{"name":b.name,"suffix":b.suffix,"active":b.active} for b in store.beneficiaries]}
