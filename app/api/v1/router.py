from fastapi import APIRouter

from app.api.v1 import case_sheets, chat, dashboard, patients, summaries
from app.core.rate_limit import default_rate_limit

# The default rate limit applies to every /api/v1 endpoint
api_router = APIRouter(prefix="/api/v1", dependencies=[default_rate_limit])
api_router.include_router(patients.router)
api_router.include_router(case_sheets.router)
api_router.include_router(dashboard.router)
api_router.include_router(summaries.router)
api_router.include_router(chat.router)
