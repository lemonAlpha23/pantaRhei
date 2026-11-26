import io
import json
import sys
from base64 import urlsafe_b64encode
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.core import Database, create_application
from app.plugins.xmonitor import create_xmonitor_plugin, protected_values, provider, settings_routes
from app.plugins.xmonitor.delivery import DeliveryResult, WebhookTarget
from app.plugins.xmonitor.protected_values import _native_key as real_native_key
from app.plugins.xmonitor.settings import XSettings


BASE = "/api/x-monitor/settings"
X_TOKEN = "fixture-x-token-secret"
URL = "https://receiver.example/private-hook?key=fixture-path-secret"
HOOK_TOKEN = "fixture-hook-token-secret"


@pytest.fixture(autouse=True)
def synthetic_env(monkeypatch):
    for key in ("PANTARHEI_X_BEARER_TOKEN", "PANTARHEI_X_WEBHOOK_URL", "PANTARHEI_X_WEBHOOK_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    if protected_values.PLATFORM != "win32":
        def isolated_key(*_):
            raise OSError("no system wallet in tests")
        monkeypatch.setattr(protected_values, "_native_key", isolated_key)


def client_for(path):
    app = create_application((create_xmonitor_plugin(),), data_dir=path, token="test-session")
    return TestClient(app, headers={"Authorization": "Bearer test-session"})


def test_invalid_settings_never_echo_credentials(tmp_path):
    client = client_for(tmp_path)
    assert client.get(BASE, headers={"Authorization": ""}).status_code == 401
    assert client.post(BASE + "/test/x", headers={"Authorization": ""}).status_code == 401
    for payload in [
        None, [], {}, {"unknown": X_TOKEN}, {"webhookUrl": "http://receiver.example/" + X_TOKEN},
        {"webhookToken": {"bad": HOOK_TOKEN}}, {"xToken": X_TOKEN + " " + X_TOKEN},
    ]:
        response = client.patch(BASE, json=payload)
        assert response.status_code == 422
        assert all(secret not in response.text for secret in (X_TOKEN, HOOK_TOKEN, "receiver.example"))
    response = client.patch(BASE, content=('{"xToken":"' + X_TOKEN).encode())
    assert response.status_code == 422 and X_TOKEN not in response.text
    assert not client.get(BASE).json()["xToken"]["configured"]


def test_effective_environment_connections_are_read_only_and_tests_do_not_enqueue(tmp_path, monkeypatch):
    monkeypatch.setenv("PANTARHEI_X_BEARER_TOKEN", X_TOKEN)
    monkeypatch.setenv("PANTARHEI_X_WEBHOOK_URL", URL)
    monkeypatch.setenv("PANTARHEI_X_WEBHOOK_TOKEN", HOOK_TOKEN)
    requests, events = [], []

    class SyntheticAPI:
        def open(self, request, timeout):
            requests.append(request)
            return io.BytesIO(b'{"data":{"id":"42","username":"X"}}')

    def receive(target, key, payload):
        events.append((target, key, json.loads(payload)))
        return DeliveryResult(True, 204, None)

    monkeypatch.setattr(provider, "build_opener", lambda *_: SyntheticAPI())
    monkeypatch.setattr(settings_routes, "send_webhook", receive)
    client = client_for(tmp_path)
    status = client.get(BASE)
    assert status.json()["webhookUrl"] == {"configured": True, "source": "environment", "host": "receiver.example"}
    for target in ("x", "webhook", "webhook"):
        response = client.post(BASE + "/test/" + target)
        assert response.json()["ok"] and datetime.fromisoformat(response.json()["testedAt"]).tzinfo
        assert all(secret not in response.text + status.text for secret in (X_TOKEN, HOOK_TOKEN, URL, "fixture-path-secret"))
    assert len(requests) == 1 and requests[0].get_method() == "GET"
    assert requests[0].full_url.startswith("https://api.x.com/2/users/by/username/X?")
    assert requests[0].get_header("Authorization") == "Bearer " + X_TOKEN
    for target, key, event in events:
        assert target == WebhookTarget(URL, HOOK_TOKEN)
        assert event["event"] == "x.connection_test" and key == event["eventId"] and key.startswith("x:test:")
        assert "signal" not in event and "postId" not in event
    assert events[0][1] != events[1][1]
    monkeypatch.delenv("PANTARHEI_X_WEBHOOK_URL")
    assert not client.post(BASE + "/test/webhook").json()["ok"]
    with Database(tmp_path).connection() as db:
        assert db.execute("SELECT count(*) FROM x_deliveries").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM x_connection_settings").fetchone()[0] == 0


@pytest.mark.skipif(sys.platform != "win32", reason="Windows DPAPI")
def test_os_protected_overrides_survive_restart_and_do_not_cross_destinations(tmp_path, monkeypatch):
    env_url = "https://receiver.example/another-hook"
    monkeypatch.setenv("PANTARHEI_X_WEBHOOK_URL", env_url)
    monkeypatch.setenv("PANTARHEI_X_WEBHOOK_TOKEN", "env-fake-secret")
    client = client_for(tmp_path)
    settings = XSettings(Database(tmp_path))
    # Simultaneous edits of separate fields must both survive.
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda patch: client.patch(BASE, json=patch).status_code,
                                [{"xToken": X_TOKEN}, {"webhookUrl": URL}]))
    assert results == [200, 200]
    assert settings.webhook_target() == WebhookTarget(URL, None)
    assert settings.x_token() == X_TOKEN
    state = client.patch(BASE, json={"webhookToken": HOOK_TOKEN})
    assert state.json()["webhookToken"]["source"] == "saved" and settings.webhook_target() == WebhookTarget(URL, HOOK_TOKEN)
    for secret in (URL, X_TOKEN, HOOK_TOKEN, "fixture-path-secret"):
        assert secret not in state.text and secret.encode() not in Database(tmp_path).path.read_bytes()
    assert client_for(tmp_path).get(BASE).json() == state.json()
    assert settings.webhook_target() == WebhookTarget(URL, HOOK_TOKEN)
    client.patch(BASE, json={"webhookUrl": "https://new.example/target"}).raise_for_status()
    assert settings.webhook_target() == WebhookTarget("https://new.example/target", None)
    client.patch(BASE, json={"webhookUrl": None}).raise_for_status()
    assert settings.webhook_target() == WebhookTarget(env_url, "env-fake-secret")
    client.patch(BASE, json={"webhookToken": HOOK_TOKEN}).raise_for_status()
    monkeypatch.setenv("PANTARHEI_X_WEBHOOK_URL", "https://new-environment.example/target")
    assert settings.webhook_target().token != HOOK_TOKEN
    monkeypatch.delenv("PANTARHEI_X_WEBHOOK_URL")
    response = client.patch(BASE, json={"xToken": "rollback-token", "webhookToken": HOOK_TOKEN})
    assert response.status_code == 422 and settings.x_token() == X_TOKEN


def test_no_cleartext_fallback_when_os_store_is_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(protected_values, "PLATFORM", "no-system-keyring")
    client = client_for(tmp_path)
    assert not client.get(BASE).json()["storageAvailable"]
    assert client.patch(BASE, json={"xToken": X_TOKEN}).status_code == 503
    assert not XSettings(Database(tmp_path)).x_token()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows DPAPI")
def test_stale_form_cannot_send_a_token_to_a_new_url_on_the_same_host(tmp_path):
    client = client_for(tmp_path)
    assert client.get(BASE).json()["revision"] == 0
    first = client.patch(BASE, json={"expectedRevision": 0, "webhookUrl": URL, "webhookToken": HOOK_TOKEN})
    assert first.json()["revision"] == 1
    another = client_for(tmp_path)
    alternate = "https://receiver.example/another-private-path"
    updated = another.patch(BASE, json={"expectedRevision": 1, "webhookUrl": alternate})
    assert updated.json()["revision"] == 2
    stale = client.patch(BASE, json={"expectedRevision": 1, "webhookToken": HOOK_TOKEN})
    assert stale.status_code == 409 and HOOK_TOKEN not in stale.text
    settings = XSettings(Database(tmp_path))
    assert settings.webhook_target() == WebhookTarget(alternate, None)
    failed = client.patch(BASE, json={"expectedRevision": 2, "webhookUrl": None, "webhookToken": HOOK_TOKEN})
    assert failed.status_code == 422 and settings.webhook_target() == WebhookTarget(alternate, None)
    for version in [None, True, -1, 2.0, "2", 2**53]:
        assert client.patch(BASE, json={"expectedRevision": version, "xToken": X_TOKEN}).status_code == 422
    assert client.patch(BASE, json={"expectedRevision": 2}).status_code == 422
    assert client_for(tmp_path).get(BASE).json() == updated.json()


def test_workspace_key_protects_portable_ciphertext_without_replacing_a_lost_key(tmp_path, monkeypatch):
    pytest.importorskip("cryptography.fernet", reason="macOS/Linux encryption dependency")
    monkeypatch.setattr(protected_values, "PLATFORM", "linux")
    vaults = {}
    creations = []

    def key(vault, create):
        if create and vault not in vaults:
            creations.append(vault)
            vaults[vault] = urlsafe_b64encode(bytes([len(creations)]) * 32)
        return vaults.get(vault)

    monkeypatch.setattr(protected_values, "_native_key", key)
    client = client_for(tmp_path)
    assert client.get(BASE).json()["storageAvailable"] and not creations
    with ThreadPoolExecutor(2) as pool:
        assert list(pool.map(lambda patch: client.patch(BASE, json=patch).status_code,
                             [{"xToken": X_TOKEN}, {"webhookUrl": URL}])) == [200, 200]
    assert len(creations) == 1
    assert client.patch(BASE, json={"webhookToken": HOOK_TOKEN}).status_code == 200
    assert XSettings(Database(tmp_path)).x_token() == X_TOKEN
    assert client_for(tmp_path).get(BASE).json()["xToken"]["configured"]
    assert X_TOKEN.encode() not in Database(tmp_path).path.read_bytes()
    assert vaults[creations[0]] not in Database(tmp_path).path.read_bytes()
    another = client_for(tmp_path / "other")
    assert another.patch(BASE, json={"xToken": X_TOKEN}).status_code == 200
    assert len(set(creations)) == 2
    vaults.pop(creations[0])
    assert client.get(BASE).json()["xToken"] == {"configured": False, "source": "saved"}
    assert client.get(BASE).json()["webhookToken"] == {"configured": False, "source": "saved"}
    assert client.patch(BASE, json={"xToken": "different-token"}).status_code == 503
    assert len(creations) == 2
    cleared = client.patch(BASE, json={"xToken": None, "webhookUrl": None})
    assert cleared.status_code == 200 and cleared.json()["webhookToken"]["source"] == "none"
    assert client.patch(BASE, json={"xToken": "replacement", "webhookUrl": URL, "webhookToken": HOOK_TOKEN}).status_code == 200
    assert len(creations) == 3 and XSettings(Database(tmp_path)).webhook_target() == WebhookTarget(URL, HOOK_TOKEN)
    assert XSettings(Database(tmp_path)).x_token() == "replacement"


def test_native_key_adapters_use_only_the_named_workspace_and_do_not_unlock(monkeypatch):
    # Simulate both system libraries. No platform keychain or D-Bus connection is opened.
    native_key = real_native_key
    keychain = Mock()
    keychain.get_password.side_effect = [None, "stored"]
    monkeypatch.setitem(sys.modules, "keyring.backends.macOS", SimpleNamespace(Keyring=lambda: keychain))
    security = Mock()
    security.SecKeychainSetUserInteractionAllowed.return_value = 0
    monkeypatch.setattr(protected_values.ctypes, "CDLL", lambda _: security)
    monkeypatch.setattr(protected_values, "PLATFORM", "darwin")
    saved = native_key("vault", True)
    keychain.set_password.assert_called_once_with(protected_values.SERVICE, "vault", saved.decode("ascii"))
    assert native_key("vault", False) == b"stored"
    security.SecKeychainSetUserInteractionAllowed.assert_called_with(0)

    collection = Mock()
    collection.search_items.side_effect = [iter(()), iter([Mock(get_secret=lambda: b"existing")])]
    bus = Mock()
    monkeypatch.setitem(sys.modules, "secretstorage", SimpleNamespace(dbus_init=lambda: bus, Collection=lambda _: collection))
    monkeypatch.setattr(protected_values, "PLATFORM", "linux")
    saved = native_key("vault", True)
    collection.create_item.assert_called_once_with(protected_values.SERVICE,
                                                  {"application": protected_values.SERVICE, "workspace": "vault"}, saved)
    assert native_key("vault", False) == b"existing"
    collection.ensure_not_locked.side_effect = OSError("locked")
    with pytest.raises(OSError):
        native_key("vault", True)
    assert bus.close.call_count == 3 and collection.create_item.call_count == 1
    collection.unlock.assert_not_called()
