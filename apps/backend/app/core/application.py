import os
import sys
from collections.abc import Sequence
from pathlib import Path
from secrets import compare_digest

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .database import Database
from .plugins import Plugin, install_plugins


def default_data_dir() -> Path:
    if directory := os.environ.get("PANTARHEI_DATA_DIR"):
        return Path(directory)
    if sys.platform == "win32":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    elif sys.platform == "darwin":
        root = Path.home() / "Library/Application Support"
    else:
        root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    return root / "PantaRhei"


def create_application(plugins: Sequence[Plugin], *, data_dir: Path | None = None, token: str | None = None) -> FastAPI:
    if token is None:
        token = os.environ.get("PANTARHEI_TOKEN", "")
    expected = f"Bearer {token}".encode()

    def authorize(authorization: str = Header(default="")):
        if token and not compare_digest(authorization.encode(), expected):
            raise HTTPException(401, "本地会话验证失败", headers={"WWW-Authenticate": "Bearer"})

    app = FastAPI(title="Panta Rhei", docs_url=None, redoc_url=None, openapi_url=None, dependencies=[Depends(authorize)])

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError):
        try:
            return await request_validation_exception_handler(request, exc)
        except ValueError:
            # The default response echoes the input; a JSON number like 1e309 has no finite float encoding.
            return JSONResponse(status_code=422, content={"detail": "请求参数超出有效范围"})

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    install_plugins(app, Database(data_dir or default_data_dir()), plugins)
    return app
