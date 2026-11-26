import json
import os
import re
import time
from collections.abc import Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from http.client import HTTPException
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener


API = "https://api.x.com/2"
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
PAGE_SIZE = 20
ID = re.compile(r"[1-9][0-9]{0,18}")
HANDLE = re.compile(r"[A-Za-z0-9_]{1,15}")


class XSourceError(RuntimeError):
    def __init__(self, message: str, *, retry_after: int | None = None, invalid_cursor: bool = False):
        super().__init__(message)
        self.retry_after = retry_after
        self.invalid_cursor = invalid_cursor


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _wait_seconds(headers) -> int | None:
    retry = headers.get("Retry-After", "").strip()
    now = int(time.time())
    waits = []
    if re.fullmatch(r"[0-9]{1,10}", retry):
        waits.append(int(retry))
    elif retry:
        try:
            stamp = parsedate_to_datetime(retry)
            if stamp.tzinfo:
                waits.append(int(stamp.timestamp()) - now)
        except (TypeError, ValueError, OverflowError, OSError):
            pass
    reset = headers.get("x-rate-limit-reset", "").strip()
    if re.fullmatch(r"[0-9]{1,10}", reset):
        waits.append(int(reset) - now)
    return max(1, *waits) if waits else None


def _http_error(error: HTTPError, paginated: bool) -> XSourceError:
    status = error.code
    if status == 429:
        return XSourceError("X API 已限流，请稍后同步", retry_after=_wait_seconds(error.headers) or 900)
    if status == 503:
        return XSourceError("X API 当前不可用", retry_after=_wait_seconds(error.headers))
    if status in (400, 422) and paginated:
        return XSourceError("X 时间线分页参数无效", invalid_cursor=True)
    message = {
        401: "X API 凭证无效，请检查 Bearer Token",
        402: "X API 读取额度不足，请检查开发者账户余额",
        403: "此 X API 凭证没有读取该资源的权限",
        404: "找不到此 X 账号或时间线",
    }.get(status, f"X API 请求失败（HTTP {status}）")
    return XSourceError(message)


def _post(row: dict, user_id: str) -> dict | None:
    if row.get("author_id") != user_id:
        return None
    references = row.get("referenced_posts") or row.get("referenced_tweets") or []
    if any(isinstance(ref, dict) and ref.get("type") == "retweeted" for ref in references):
        return None
    note = row.get("note_post") or row.get("note_tweet")
    text = note.get("text") if isinstance(note, dict) else None
    text = text or row.get("text")
    post_id = row.get("id")
    if not isinstance(post_id, str) or not ID.fullmatch(post_id) or not isinstance(text, str) or not text.strip():
        raise XSourceError("X 帖子缺少编号或正文")
    try:
        stamp = datetime.fromisoformat(row["created_at"])
        if stamp.tzinfo is None:
            raise ValueError
        published = stamp.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    except (TypeError, ValueError, KeyError, OverflowError):
        raise XSourceError("X 帖子缺少有效的发布时间") from None
    return {"id": post_id, "text": text, "publishedAt": published}


class XProvider:
    def __init__(self, token: Callable[[], str | None] | None = None):
        self._opener = build_opener(_NoRedirect())
        self._token = token or (lambda: os.environ.get("PANTARHEI_X_BEARER_TOKEN", "").strip())

    @property
    def configured(self) -> bool:
        return bool(self._token())

    def _get(self, path: str, params: dict[str, str]) -> dict:
        token = self._token()
        if not token:
            raise XSourceError("请配置 X API Bearer Token，可在连接配置中填写或使用 PANTARHEI_X_BEARER_TOKEN")
        request = Request(f"{API}/{path}?{urlencode(params)}", headers={"Accept": "application/json"})
        request.add_unredirected_header("Authorization", f"Bearer {token}")
        try:
            deadline = time.monotonic() + 12
            body = bytearray()
            with self._opener.open(request, timeout=6) as response:
                while chunk := response.read1(65536):
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE_BYTES:
                        raise XSourceError("X API 响应过大")
                    if time.monotonic() >= deadline:
                        raise XSourceError("读取 X API 响应超时")
            result = json.loads(body)
        except HTTPError as exc:
            with exc:
                raise _http_error(exc, "pagination_token" in params) from None
        except (OSError, HTTPException, UnicodeError, ValueError, RecursionError):
            raise XSourceError("无法读取 X API 响应，请检查网络和接口配置") from None
        if not isinstance(result, dict):
            raise XSourceError("X API 返回了无效的响应格式")
        if result.get("errors") and not result.get("data"):
            raise XSourceError("X 账号不存在、受限或暂时无法读取")
        return result

    def resolve(self, handle: str) -> str:
        if not HANDLE.fullmatch(handle):
            raise XSourceError("X 用户名格式无效")
        data = self._get(f"users/by/username/{handle}", {"user.fields": "id,username"}).get("data")
        if isinstance(data, dict) and str(data.get("username", "")).lower() == handle.lower():
            user_id = data.get("id")
            if isinstance(user_id, str) and ID.fullmatch(user_id):
                return user_id
        raise XSourceError("X 未返回与用户名匹配的账号")

    def timeline(self, user_id: str, since_id: str | None = None,
                 pagination_token: str | None = None) -> tuple[list[dict], str | None]:
        if not ID.fullmatch(user_id) or (since_id is not None and not ID.fullmatch(since_id)):
            raise XSourceError("X 账号或帖子编号无效")
        params = {"max_results": str(PAGE_SIZE), "exclude": "retweets", "expansions": "author_id",
                  "post.fields": "id,text,created_at,note_post"}
        if since_id is not None:
            params["since_id"] = since_id
        if pagination_token is not None:
            params["pagination_token"] = pagination_token
        result = self._get(f"users/{user_id}/tweets", params)
        meta = result.get("meta")
        if not isinstance(meta, dict):
            raise XSourceError("X 未返回有效的时间线分页信息")
        rows = result.get("data", [] if meta.get("result_count") == 0 else None)
        token = meta.get("next_token")
        if not isinstance(rows, list) or (token is not None and (not isinstance(token, str) or not 0 < len(token) <= 4096)):
            raise XSourceError("X 未返回有效的时间线")
        posts = []
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("author_id"), str):
                raise XSourceError("X 帖子缺少作者信息")
            post = _post(row, user_id)
            if post is not None:
                posts.append(post)
        return posts, token
