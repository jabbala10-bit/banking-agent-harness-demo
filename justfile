default:
    @just --list

setup:
    uv sync --locked

run:
    uv run uvicorn app.main:app --reload

start:
    uv run banking-agent-harness

test:
    uv run pytest -q

build:
    uv build
