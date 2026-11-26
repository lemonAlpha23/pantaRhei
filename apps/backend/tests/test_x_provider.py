import io
import json
from email.message import Message
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

import pytest

from app.plugins.xmonitor import provider
from app.plugins.xmonitor.provider import XProvider, XSourceError


@pytest.fixture
def source(monkeypatch):
    monkeypatch.setenv("PANTARHEI_X_BEARER_TOKEN", "test-token")
    return XProvider()


def reply(source, monkeypatch, *bodies):
    requests = []
    bodies = iter(bodies)

    def open_request(request, timeout):
        requests.append(request)
        assert timeout > 0
        return io.BytesIO(json.dumps(next(bodies)).encode())

    monkeypatch.setattr(source._opener, "open", open_request)
    return requests


def test_lookup_and_timeline_request_follow_numeric_identity(source, monkeypatch):
    post = {"id": "103", "author_id": "42", "text": "short…", "created_at": "2026-11-26T09:30:00+08:00",
            "note_post": {"text": "long post"}, "referenced_posts": [{"type": "replied_to", "id": "2"}]}
    previous = {**post, "id": "102", "note_post": None, "note_tweet": {"text": "older long-post field"}}
    requests = reply(source, monkeypatch, {"data": {"username": "Trader_1", "id": "42"}}, {
        "data": [post, previous, {**post, "id": "101", "author_id": "6"},
                 {**post, "id": "100", "referenced_posts": [{"type": "retweeted"}]}],
        "meta": {"next_token": "next_token", "result_count": 4}},
        {"meta": {"result_count": 0}})
    assert source.configured
    assert source.resolve("trader_1") == "42"
    posts, cursor = source.timeline("42", "99")
    assert posts == [
        {"id": "103", "text": "long post", "publishedAt": "2026-11-26T01:30:00.000Z"},
        {"id": "102", "text": "older long-post field", "publishedAt": "2026-11-26T01:30:00.000Z"},
    ]
    assert cursor == "next_token"
    assert source.timeline("42", "99", cursor) == ([], None)
    assert [urlsplit(req.full_url).path for req in requests] == [
        "/2/users/by/username/trader_1", "/2/users/42/tweets", "/2/users/42/tweets"]
    for req in requests:
        assert req.get_method() == "GET"
        assert req.get_header("Authorization") == "Bearer test-token"
        assert req.host == "api.x.com" and req.type == "https" and "test-token" not in req.full_url
    first = parse_qs(urlsplit(requests[1].full_url).query)
    assert first == {"max_results": ["20"], "exclude": ["retweets"], "expansions": ["author_id"],
                     "post.fields": ["id,text,created_at,note_post"], "since_id": ["99"]}
    assert parse_qs(urlsplit(requests[2].full_url).query) == {**first, "pagination_token": ["next_token"]}


def test_rejects_mismatched_accounts_and_malformed_success_responses(source, monkeypatch):
    post = {"author_id": "42", "text": "post", "id": "103", "created_at": "2026-11-24T00:10:21"}
    requests = reply(source, monkeypatch, {"data": {"username": "someone_else", "id": "42"}},
                     {"errors": [{"detail": "private data"}]}, {"meta": {}, "data": [post]},
                     {"meta": {}, "data": [{**post, "author_id": None}]}, {"meta": {"next_token": True}, "data": []})
    with pytest.raises(XSourceError):
        source.resolve("../accounts")
    with pytest.raises(XSourceError):
        source.timeline("42/7")
    with pytest.raises(XSourceError):
        source.timeline("42", "invalid")
    assert not requests
    with pytest.raises(XSourceError, match="用户名匹配"):
        source.resolve("Trader")
    for expected in ["受限", "发布时间", "作者", "时间线"]:
        with pytest.raises(XSourceError, match=expected):
            source.timeline("42")


def test_reports_auth_quota_rate_limits_and_cursor_without_leaking_response(source, monkeypatch):
    monkeypatch.setattr(provider.time, "time", lambda: 100_000)
    headers = Message()
    headers["x-rate-limit-reset"] = "100125"
    headers["Retry-After"] = "31"
    for status, message, cooldown in [(401, "凭证无效", None), (402, "额度不足", None),
                                      (403, "没有读取", None), (404, "找不到", None),
                                      (429, "限流", 125), (503, "不可用", 125),
                                      (422, "分页参数", None)]:
        def fail_request(request, timeout):
            raise HTTPError(request.full_url, status, "test-token", headers, io.BytesIO(b"test-token"))

        monkeypatch.setattr(source._opener, "open", fail_request)
        with pytest.raises(XSourceError, match=message) as exc:
            source.timeline("42", "99", "page")
        assert exc.value.retry_after == cooldown
        assert exc.value.invalid_cursor == (status == 422)
        assert "test-token" not in str(exc.value)
    monkeypatch.delenv("PANTARHEI_X_BEARER_TOKEN")
    assert not source.configured
    with pytest.raises(XSourceError, match="请配置"):
        source.resolve("Trader")
