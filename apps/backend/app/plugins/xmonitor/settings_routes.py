import asyncio
import json
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request

from .delivery import send_webhook
from .provider import XProvider, XSourceError
from .settings import SettingsConflict, XSettings


def _checked(ok: bool, message: str) -> dict:
    return {"ok": ok, "message": message, "testedAt": datetime.now(UTC).isoformat(timespec="seconds")}


def register_settings_routes(router: APIRouter, settings: XSettings, source: XProvider) -> None:
    router.get("/settings")(settings.status)

    @router.patch("/settings")
    async def change_settings(request: Request):
        # FastAPI's default validation errors include input values. Keep secret material out of all responses.
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > 192 * 1024:
                raise HTTPException(413, "配置内容过长")
            body.extend(chunk)
        try:
            patch = json.loads(body)
        except (ValueError, UnicodeError, RecursionError):
            raise HTTPException(422, "连接配置必须是有效的 JSON 对象") from None
        try:
            return await asyncio.to_thread(settings.patch, patch)
        except SettingsConflict as error:
            raise HTTPException(409, str(error)) from None
        except ValueError as error:
            raise HTTPException(422, str(error)) from None
        except OSError:
            raise HTTPException(503, "系统凭证保护不可用，请检查系统用户或使用环境变量") from None

    @router.post("/settings/test/{target}")
    def test_connection(target: Literal["x", "webhook"]):
        if target == "x":
            try:
                source.resolve("X")
            except XSourceError as error:
                return _checked(False, str(error))
            return _checked(True, "已通过 X API 读取公开账号 @X")
        webhook = settings.webhook_target()
        if not webhook:
            return _checked(False, "请先配置 Webhook 接收地址")
        event_id = "x:test:" + uuid4().hex
        event = {"schemaVersion": 1, "event": "x.connection_test", "eventId": event_id,
                 "sentAt": datetime.now(UTC).isoformat(timespec="seconds")}
        result = send_webhook(webhook, event_id, json.dumps(event))
        if result.ok:
            return _checked(True, f"接收端已响应测试事件（HTTP {result.status}）")
        return _checked(False, result.error or "接收端未接受测试事件")
