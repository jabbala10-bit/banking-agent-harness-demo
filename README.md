# Banking Agent Harness Demo

A runnable project showing deterministic controls around a banking AI agent: policy enforcement, explicit approval, transaction verification, execution limits, and audit logs. Uses fictional in-memory data only; **not for real banking or production use**.

## Setup and run

Requires Python 3.11+, [uv](https://docs.astral.sh/uv/), and [Just](https://just.systems/).

```bash
just setup
# Start the local development server with reload:
just run
# Or run the installed application entry point without reload:
just start
# Run tests or build a wheel and source distribution:
just test
just build
```

The equivalent commands can be run directly with uv: `uv sync --locked`,
`uv run uvicorn app.main:app --reload`, `uv run pytest -q`, and `uv build`.

Open http://127.0.0.1:8000. Without an API key, a deterministic intent parser makes the demo reproducible. With `OPENAI_API_KEY`, the OpenAI Responses API is used with function tools; the system prompt remains short and unchanged.

To run with model-backed tool calling, copy `.env.example` to `.env` and set `OPENAI_API_KEY`.

## Demo scenarios

- `What is my balance?`
- `Find beneficiaries`
- `Transfer 10000 to John` → ambiguity; must clarify between John Smith and John Lewis.
- `Transfer 10000 to John Smith` → creates pending transfer; click Approve to execute.
- `Transfer 25000 to Nick Anderson` → rejected (blocked beneficiary).
- `Transfer -10000 to John Smith` → rejected.
- Complete two transfers in the same session, then try a third → session execution limit.
- Start a transfer, then repeat the same beneficiary and amount before approval → duplicate pending transfer is rejected.
- Start transfers whose combined pending amount would exceed available balance or daily/session limits → the later transfer is rejected.
- Check status with `status TXN-...`.

Mock account: ₹200,000 balance, ₹100,000 daily limit, ₹25,000 already transferred today. Beneficiaries: John Smith (1122), John Lewis (3344), Priya Shah (5566), Nick Anderson (7788, blocked).

## API

- `GET /api/health`
- `POST /api/chat` `{ "session_id": "demo-session", "message": "Transfer 10000 to John" }`
- `POST /api/transactions/{id}/approve` `{ "session_id": "demo-session" }`
- `POST /api/transactions/{id}/reject` `{ "session_id": "demo-session" }`
- `GET /api/state?session_id=demo-session`
- `GET /api/audit`
- `POST /api/reset`

## Design decisions

- Business rules live in deterministic Python services, not the system prompt.
- Pending approvals reserve available balance, daily-limit capacity, and session capacity; reservations are released when a transfer is approved or rejected.
- An identical beneficiary-and-amount transfer cannot be initiated twice in the same session while the first is awaiting approval.
- Each policy decision includes ordered rule checks in the result and `TRANSFER_VALIDATION` audit event, including the first failed rule and its policy code.
- Model tools can initiate a transfer but cannot execute it.
- Approval is a separate endpoint bound to the transaction ID and session.
- Policy is rechecked at approval time; transaction state prevents repeat approval.
- The verifier reports actual mock-ledger state, not the model's claim.
- Audit events are structured JSON lines and visible in the UI.
- The app uses in-memory data. Production needs authentication, durable storage, atomic database transactions, secure approval, proper rate limiting, secrets management, and a real provider integration.

Run tests with `just test`.
