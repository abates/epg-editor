"""FastAPI routers.

Thin HTTP layer: validates input/output via Pydantic models and delegates
to `app.services`. Must not contain business logic or talk to storage/
SchedulesDirect directly (see CLAUDE.md's backend module layout).
"""
