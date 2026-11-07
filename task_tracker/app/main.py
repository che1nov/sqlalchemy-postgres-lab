import logging
import secrets
from contextlib import asynccontextmanager

from argon2 import PasswordHasher
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.api import router
from app.db import database_url, make_engine, make_sessions
from app.services import Conflict, InvalidAssignee, NotFound, Unauthorized


def create_app(url: str | None = None, logger: logging.Logger | None = None) -> FastAPI:
    engine = make_engine(url or database_url())
    logger = logger or logging.getLogger("task_tracker")

    @asynccontextmanager
    async def lifespan(app):
        logger.info("Application started")
        yield
        engine.dispose()
        logger.info("Application stopped")

    app = FastAPI(title="Чернов Илья — Итоговое задание — Трекер задач", version="1.0.0", lifespan=lifespan)
    app.state.sessions = make_sessions(engine)
    app.state.engine = engine
    app.state.hasher = PasswordHasher()
    app.state.dummy_hash = app.state.hasher.hash(secrets.token_urlsafe(32))

    async def business_error(request: Request, exc: Exception):
        codes = {NotFound: 404, Conflict: 409, Unauthorized: 401, InvalidAssignee: 422}
        headers = {"WWW-Authenticate": "Bearer"} if isinstance(exc, Unauthorized) else None
        return JSONResponse({"detail": str(exc)}, status_code=codes[type(exc)], headers=headers)

    for error in (NotFound, Conflict, Unauthorized, InvalidAssignee):
        app.add_exception_handler(error, business_error)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Do not echo submitted passwords or other raw input in validation errors.
        errors = [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        return JSONResponse({"detail": errors}, status_code=422)

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request, exc):
        logger.error("Database operation failed", extra={"operation": request.method, "err": type(exc).__name__})
        return JSONResponse({"detail": "База данных временно недоступна"}, status_code=503)

    @app.get("/health", tags=["system"])
    def health():
        from sqlalchemy import text
        with engine.connect() as connection:
            connection.execute(text("SELECT 1 FROM alembic_version"))
        return {"status": "ok"}

    app.include_router(router)
    return app
