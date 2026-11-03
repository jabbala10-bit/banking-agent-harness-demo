SYSTEM_PROMPT = (
    "You are a professional retail banking assistant. Help users check their balance, "
    "find beneficiaries, initiate transfers, and check transfer status. Use tools when needed. "
    "Do not guess transaction outcomes."
)

TOOLS = [
    {
        "type": "function",
        "name": "get_balance",
        "description": "Get current mock account balance.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "find_beneficiaries",
        "description": "List beneficiaries using masked account suffixes.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "initiate_transfer",
        "description": (
            "Validate and prepare a transfer. Never executes or moves funds; "
            "requires separate user approval."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "beneficiary_name": {"type": "string"},
                "amount": {"type": "number"},
            },
            "required": ["beneficiary_name", "amount"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_transfer_status",
        "description": "Get status for a transaction in this session.",
        "parameters": {
            "type": "object",
            "properties": {"transaction_id": {"type": "string"}},
            "required": ["transaction_id"],
            "additionalProperties": False,
        },
    },
]

DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_MAX_TRANSFERS_PER_SESSION = 2
DEFAULT_MAX_TOOL_CALLS_PER_TURN = 6
DEFAULT_AUDIT_PATH = "data/audit.jsonl"
