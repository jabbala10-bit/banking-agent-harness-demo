from threading import RLock
from .models import Account, Beneficiary, Session

class Store:
    def __init__(self):
        self.lock = RLock()
        self.reset()
    def reset(self):
        with getattr(self, "lock", RLock()):
            self.account = Account()
            self.beneficiaries = [
                Beneficiary(id="BEN-001", name="John Smith", suffix="1122"),
                Beneficiary(id="BEN-002", name="John Lewis", suffix="3344"),
                Beneficiary(id="BEN-003", name="Priya Shah", suffix="5566"),
                Beneficiary(id="BEN-004", name="Nick Anderson", suffix="7788", active=False),
            ]
            self.transactions = {}
            self.sessions = {}
    def session(self, sid):
        with self.lock:
            if sid not in self.sessions: 
                self.sessions[sid] = Session(id=sid)
            return self.sessions[sid]
    def beneficiary(self, bid):
        return next((b for b in self.beneficiaries if b.id == bid), None)
    def transaction_list(self, sid=None):
        rows = list(self.transactions.values())
        if sid: 
            rows = [x for x in rows if x.session_id == sid]
        return sorted(rows, key=lambda x: x.created_at, reverse=True)

store = Store()
