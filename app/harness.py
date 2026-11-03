import math

from .audit import emit
from .config import MAX_TRANSFERS_PER_SESSION
from .models import Transaction, Result, new_id, now
from .store import store

class PolicyService:
    def validate(self, sid, name, amount, exclude_transaction_id=None):
        checks = []

        def reject(rule, code, message, status="REJECTED", **details):
            checks.append({"rule": rule, "passed": False, "code": code})
            return Result(
                status=status,
                message=message,
                data={"code": code, "checks": checks, **details},
            )

        def pass_check(rule):
            checks.append({"rule": rule, "passed": True})

        name = name.strip()
        if not name:
            return reject(
                "beneficiary_required",
                "BENEFICIARY_REQUIRED",
                "Beneficiary name is required.",
            )
        pass_check("beneficiary_required")

        if not math.isfinite(amount) or amount <= 0:
            return reject(
                "amount_positive_and_finite",
                "INVALID_AMOUNT",
                "Amount must be a finite number greater than zero.",
            )
        pass_check("amount_positive_and_finite")

        if round(amount, 2) != amount:
            return reject(
                "amount_precision",
                "INVALID_AMOUNT_PRECISION",
                "Amount can have at most two decimal places.",
            )
        pass_check("amount_precision")

        a = store.account
        if not a.active:
            return reject(
                "source_account_active",
                "SOURCE_ACCOUNT_INACTIVE",
                "Source account is inactive.",
            )
        pass_check("source_account_active")

        exact = [b for b in store.beneficiaries if b.name.casefold() == name.casefold()]
        matches = exact or [b for b in store.beneficiaries if name.casefold() in b.name.casefold()]
        if not matches:
            return reject(
                "beneficiary_exists",
                "BENEFICIARY_NOT_FOUND",
                "Beneficiary not found.",
            )
        pass_check("beneficiary_exists")

        if len(matches) > 1:
            return reject(
                "beneficiary_unambiguous",
                "AMBIGUOUS_BENEFICIARY",
                "Multiple beneficiaries match; ask the user to choose.",
                status="NEEDS_CLARIFICATION",
                matches=[
                    {"name": b.name, "suffix": b.suffix, "active": b.active}
                    for b in matches
                ],
            )
        b = matches[0]
        pass_check("beneficiary_unambiguous")

        if not b.active:
            return reject(
                "beneficiary_active",
                "BENEFICIARY_INACTIVE",
                "Beneficiary account is blocked or inactive.",
                beneficiary=b.name,
            )
        pass_check("beneficiary_active")

        pending = [
            txn
            for txn in store.transactions.values()
            if txn.status == "AWAITING_APPROVAL"
            and txn.id != exclude_transaction_id
        ]
        duplicate = any(
            txn.session_id == sid
            and txn.beneficiary_id == b.id
            and txn.amount == amount
            for txn in pending
        )
        if duplicate:
            return reject(
                "no_duplicate_pending_transfer",
                "DUPLICATE_PENDING_TRANSFER",
                "An identical transfer is already awaiting approval in this session.",
            )
        pass_check("no_duplicate_pending_transfer")

        pending_amount = sum(txn.amount for txn in pending)
        available_balance = a.balance - pending_amount
        if amount > available_balance:
            return reject(
                "available_balance_includes_pending",
                "INSUFFICIENT_FUNDS",
                "Insufficient available balance after pending transfers.",
                available_balance=available_balance,
                pending_amount=pending_amount,
            )
        pass_check("available_balance_includes_pending")

        daily_exposure = a.transferred_today + pending_amount + amount
        if daily_exposure > a.daily_limit:
            return reject(
                "daily_limit_includes_pending",
                "DAILY_LIMIT_EXCEEDED",
                "Daily transfer limit would be exceeded after pending transfers.",
                daily_exposure=daily_exposure,
                daily_limit=a.daily_limit,
            )
        pass_check("daily_limit_includes_pending")

        session = store.session(sid)
        pending_session_count = sum(
            txn.session_id == sid and txn.status == "AWAITING_APPROVAL"
            for txn in store.transactions.values()
        )
        reserved_session_count = session.completed_count + pending_session_count
        capacity_exceeded = (
            reserved_session_count > MAX_TRANSFERS_PER_SESSION
            if exclude_transaction_id
            else reserved_session_count >= MAX_TRANSFERS_PER_SESSION
        )
        if capacity_exceeded:
            return reject(
                "session_limit_includes_pending",
                "SESSION_TRANSFER_LIMIT",
                "Maximum transfers for this chat session reached, including pending approvals.",
                max=MAX_TRANSFERS_PER_SESSION,
                reserved=reserved_session_count,
            )
        pass_check("session_limit_includes_pending")

        return Result(
            status="VALIDATED",
            message="All deterministic policy checks passed.",
            data={
                "beneficiary_id": b.id,
                "beneficiary": b.name,
                "suffix": b.suffix,
                "checks": checks,
                "available_balance": available_balance,
                "pending_amount": pending_amount,
                "daily_exposure": daily_exposure,
            },
        )

class Verifier:
    def verify(self, txn):
        if txn.status == "COMPLETED" and txn.verification_message:
            emit(
                "TRANSACTION_VERIFIED", 
                txn.session_id, 
                txn.id, 
                {
                    "status":txn.status
                }
            )
            return Result(
                status="COMPLETED", 
                message="Transfer completed and verified by the mock ledger.", 
                data={
                    "verified":True
                }
            )
        if txn.status in ("FAILED","REJECTED"):
            return Result(
                status=txn.status, 
                message=f"Transfer status verified: {txn.status}.", 
                data={
                    "verified":True
                }
            )
        return Result(
            status="PENDING", 
            message="Outcome is not confirmed. Do not claim success or retry blindly.", 
            data={
                "verified":False
            }
        )

class Harness:
    def __init__(self):
        self.policy = PolicyService()
        self.verifier = Verifier()

    def initiate(self, sid, name, amount):
        amount_value = float(amount)
        with store.lock:
            result = self.policy.validate(sid, name, amount_value)
            if result.status == "VALIDATED":
                b = store.beneficiary(result.data["beneficiary_id"])
                txn = Transaction(
                    id=new_id("TXN"),
                    session_id=sid,
                    beneficiary_id=b.id,
                    beneficiary=b.name,
                    suffix=b.suffix,
                    amount=amount_value,
                )
                store.transactions[txn.id] = txn
                store.session(sid).pending_ids.append(txn.id)
        emit(
            "TRANSFER_VALIDATION",
            sid,
            details={
                "status": result.status,
                "code": result.data.get("code"),
                "amount": (
                    amount_value
                    if math.isfinite(amount_value)
                    else str(amount_value)
                ),
                "beneficiary_query": name,
                "checks": result.data.get("checks", []),
            },
        )
        if result.status != "VALIDATED":
            return result
        emit(
            "TRANSFER_INITIATED",
            sid,
            txn.id,
            {
                "amount": amount,
                "beneficiary": b.name,
                "status": txn.status,
                "checks": result.data["checks"],
            },
        )
        return Result(
            status="PENDING_CONFIRMATION", 
            message="Validated; explicit approval is required. No funds moved yet.",
            data={
                "transaction_id":txn.id,
                "amount":txn.amount,
                "beneficiary":b.name,
                "suffix":b.suffix,
                "status":txn.status,
                "requires_confirmation":True,
                "checks":result.data["checks"],
                "available_balance":result.data["available_balance"],
                "daily_exposure":result.data["daily_exposure"],
            }
        )

    def approve(self, sid, tid):
        with store.lock:
            txn = store.transactions.get(tid)
            if not txn or txn.session_id != sid:
                return Result(
                    status="REJECTED", 
                    message="Transaction not found for this session.", 
                    data={
                        "code":"TRANSACTION_NOT_FOUND"
                    }
                )
            if txn.status != "AWAITING_APPROVAL" or txn.approval_used:
                return Result(
                    status="REJECTED", 
                    message="Transaction is no longer awaiting approval.", 
                    data={
                        "code":"INVALID_TRANSACTION_STATE",
                        "status":txn.status
                    }
                )
            # Revalidate immediately before execution.
            check = self.policy.validate(
                sid,
                txn.beneficiary,
                txn.amount,
                exclude_transaction_id=tid,
            )
            if check.status != "VALIDATED":
                txn.status = "REJECTED"; txn.updated_at = now()
                emit(
                    "TRANSFER_REJECTED_AT_APPROVAL", 
                    sid, 
                    tid, 
                    {
                        "code":check.data.get("code"),
                        "checks":check.data.get("checks", []),
                    }
                )
                return check
            txn.approval_used = True; txn.status = "EXECUTING"; txn.updated_at = now()
            emit(
                "TRANSFER_APPROVED", 
                sid, 
                tid, 
                {
                    "amount":txn.amount,
                    "beneficiary":txn.beneficiary,
                    "checks":check.data["checks"],
                }
            )
            a = store.account; b = store.beneficiary(txn.beneficiary_id)
            if not b or not b.active or not a.active or txn.amount > a.balance or a.transferred_today + txn.amount > a.daily_limit:
                txn.status = "FAILED"; txn.verification_message = "Execution-time invariant failed."
            else:
                a.balance -= txn.amount; a.transferred_today += txn.amount
                txn.status = "COMPLETED"; txn.verification_message = "Mock ledger updated."
                store.session(sid).completed_count += 1
            txn.updated_at = now()
            verified = self.verifier.verify(txn)
            if tid in store.session(sid).pending_ids: 
                store.session(sid).pending_ids.remove(tid)
            emit(
                "TRANSFER_EXECUTION_RESULT", 
                sid, 
                tid, 
                {
                    "status":txn.status,
                    "verified":verified.data.get("verified")
                }
            )
            return Result(
                status=txn.status, 
                message=verified.message, 
                data={
                    "transaction_id":tid,
                    "status":txn.status,
                    "verified":verified.data.get("verified"),
                    "balance":a.balance
                }
            )

    def reject(self, sid, tid):
        with store.lock:
            txn = store.transactions.get(tid)
            if not txn or txn.session_id != sid:
                return Result(
                    status="REJECTED", 
                    message="Transaction not found for this session.", 
                    data={
                        "code":"TRANSACTION_NOT_FOUND"
                    }
                )
            if txn.status != "AWAITING_APPROVAL":
                return Result(
                    status="REJECTED", 
                    message="Only pending approvals can be rejected.", 
                    data={
                        "code":"INVALID_TRANSACTION_STATE"
                    }
                )
            txn.status = "REJECTED"; txn.updated_at = now()
            if tid in store.session(sid).pending_ids: 
                store.session(sid).pending_ids.remove(tid)
            emit(
                "TRANSFER_REJECTED_BY_USER", sid, tid
            )
            return Result(
                status="REJECTED", 
                message="Transfer rejected. No funds were moved.", 
                data={
                    "transaction_id":tid
                }
            )
