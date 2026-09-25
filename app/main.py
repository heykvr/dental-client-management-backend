from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.database import DbDep, create_client, ping
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging
from app.repositories.case_sheet_repo import CaseSheetRepository
from app.repositories.counter_repo import CounterRepository
from app.repositories.patient_repo import PatientRepository


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    client = create_client(settings)
    app.state.db = client[settings.mongodb_db_name]
    await CounterRepository(app.state.db).ensure_patient_counter()
    await PatientRepository(app.state.db).ensure_indexes()
    await CaseSheetRepository(app.state.db).ensure_indexes()
    yield
    await client.close()


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.environment)

    app = FastAPI(title="Dental Patient Management API", version="0.1.0", lifespan=lifespan)
    register_exception_handlers(app)

    # expose Retry-After so the frontend can read it on 429 responses
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["Content-Type"],
        expose_headers=["Retry-After"],
    )

    app.include_router(api_router)

    # Not rate limited: it is outside the /api/v1 router (Render checks it constantly)
    @app.get("/health", tags=["health"])
    async def health(db: DbDep) -> JSONResponse:
        if await ping(db):
            return JSONResponse({"status": "ok", "database": "ok"})
        # 503 tells the host (Render) the service is unhealthy
        return JSONResponse({"status": "error", "database": "unavailable"}, status_code=503)

    return app


app = create_app()
