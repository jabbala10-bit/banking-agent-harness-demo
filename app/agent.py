import json, re
from .audit import emit
from .constants import SYSTEM_PROMPT, TOOLS
from .config import OPENAI_API_KEY, OPENAI_MODEL, MAX_TOOL_CALLS_PER_TURN
from .harness import Harness
from .store import store

harness = Harness()

def dispatch(sid, name, args):
    emit("TOOL_CALL", sid, details={"tool":name,"arguments":args})
    if name == "get_balance":
        a=store.account
        return {
            "status":"SUCCESS",
            "balance":a.balance,
            "currency":"INR",
            "account_name":a.name
        }
    
    if name == "find_beneficiaries":
        q=str(args.get("query","")).casefold()
        return {
            "status":"SUCCESS",
            "beneficiaries":[{"name":b.name,"suffix":b.suffix,"active":b.active} for b in store.beneficiaries if not q or q in b.name.casefold()]
        }
    
    if name == "initiate_transfer":
        return harness.initiate(sid, str(args.get("beneficiary_name","")), float(args.get("amount",0))).model_dump()
    
    if name == "get_transfer_status":
        t=store.transactions.get(str(args.get("transaction_id","")))
        if not t or t.session_id != sid: 
            return {
                "status":"NOT_FOUND",
                "message":"No transaction found for this session."
            }
        return {
            "status":t.status,
            "transaction_id":t.id,
            "beneficiary":t.beneficiary,
            "amount":t.amount,
            "verified":t.status in ("COMPLETED","FAILED","REJECTED")
        }
    return {
        "status":"REJECTED",
        "message":"Unknown tool"
    }

class DemoAgent:
    def reply(self,sid,msg):
        low=msg.casefold().strip()
        if any(x in low for x in ("balance","how much money","funds do i have")):
            r=dispatch(sid,"get_balance",{}); return f"Your current balance is ₹{r['balance']:,.2f}."
        if any(x in low for x in ("beneficiar","contacts")):
            r=dispatch(sid,"find_beneficiaries",{"query":""})
            return "Your beneficiaries are:\n" + "\n".join(f"- {b['name']} (•••• {b['suffix']}) — {'active' if b['active'] else 'blocked'}" for b in r["beneficiaries"])
        sm=re.search(r"(?:status of|status for|status)\s+(TXN-[A-Z0-9]+)",msg,re.I)
        if sm:
            r=dispatch(sid,"get_transfer_status",{"transaction_id":sm.group(1).upper()})
            return f"Transaction status: {r['status']}. {r.get('message','')}"
        m=re.search(r"(?:transfer|send|pay)\s+(?:₹|rs\.?\s*)?(-?\d+(?:\.\d{1,2})?)\s+(?:to\s+)?(.+)",msg,re.I)
        if m:
            name=re.sub(r"\s+(please|now|for me)$","",m.group(2).strip().rstrip("?.!"),flags=re.I)
            r=dispatch(sid,"initiate_transfer",{"beneficiary_name":name,"amount":float(m.group(1))})
            status=r.get("status")
            if status=="NEEDS_CLARIFICATION":
                return "Multiple beneficiaries match. Please specify one:\n"+ "\n".join(f"- {b['name']} (•••• {b['suffix']})" for b in r["data"]["matches"])
            if status=="PENDING_CONFIRMATION":
                d=r["data"]; return f"Transfer of ₹{d['amount']:,.2f} to {d['beneficiary']} (account ending {d['suffix']}) awaits your explicit approval. Transaction ID: {d['transaction_id']}. No funds have moved."
            return r.get("message","Transfer not initiated.")
        if any(x in low for x in ("approve","proceed","confirm")):
            return "Use the Approve button on the pending transaction card. The application—not the LLM—handles authorization."
        return "I can check balance, list beneficiaries, initiate a transfer, or check a transaction status. Try “Transfer 10000 to John”."

class OpenAIAgent:
    def __init__(self):
        from openai import OpenAI
        self.client=OpenAI(api_key=OPENAI_API_KEY)
    def reply(self,sid,msg):
        session=store.session(sid)
        emit("USER_MESSAGE",sid,details={"length":len(msg)})
        try:
            kwargs={"model":OPENAI_MODEL,"tools":TOOLS,"instructions":SYSTEM_PROMPT,"parallel_tool_calls":False}
            if session.previous_response_id:
                response=self.client.responses.create(previous_response_id=session.previous_response_id,input=msg,**kwargs)
            else:
                response=self.client.responses.create(input=msg,**kwargs)
            for _ in range(MAX_TOOL_CALLS_PER_TURN):
                calls=[x for x in response.output if getattr(x,"type",None)=="function_call"]
                if not calls:
                    session.previous_response_id=response.id
                    answer=response.output_text or "I could not generate a response."
                    emit("AGENT_RESPONSE",sid,details={"mode":"openai","length":len(answer)})
                    return answer
                outputs=[]
                for c in calls:
                    try: args=json.loads(c.arguments or "{}"); result=dispatch(sid,c.name,args)
                    except Exception: result={"status":"REJECTED","message":"Invalid tool arguments."}
                    outputs.append({"type":"function_call_output","call_id":c.call_id,"output":json.dumps(result,ensure_ascii=False)})
                response=self.client.responses.create(previous_response_id=response.id,input=outputs,**kwargs)
            return "Tool-call limit reached for this turn; please try again."
        except Exception as e:
            emit("MODEL_ERROR",sid,details={"error_type":type(e).__name__})
            return "The model service is unavailable. No transfer can bypass the deterministic Harness."
def get_agent():
    return (OpenAIAgent(),"openai") if OPENAI_API_KEY else (DemoAgent(),"demo")
