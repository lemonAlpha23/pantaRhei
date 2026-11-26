"""Keep connection credentials encrypted at rest with keys owned by the OS user."""

import base64
import ctypes
import secrets
import sqlite3
import sys
from contextlib import closing
from ctypes import wintypes


PLATFORM = sys.platform
SERVICE = "Panta Rhei X connections"


class _Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.c_void_p)]


def _convert(data: bytes, encrypt: bool) -> bytes:
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    convert = crypt32.CryptProtectData if encrypt else crypt32.CryptUnprotectData
    convert.argtypes = (ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.POINTER(_Blob), ctypes.c_void_p,
                        ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob))
    convert.restype = wintypes.BOOL
    release = kernel32.LocalFree
    release.argtypes, release.restype = (ctypes.c_void_p,), ctypes.c_void_p
    source = ctypes.create_string_buffer(data)
    input_blob = _Blob(len(data), ctypes.cast(source, ctypes.c_void_p))
    result = _Blob()
    try:
        if not convert(ctypes.byref(input_blob), None, None, None, None, 1, ctypes.byref(result)):
            raise OSError("操作系统无法保护或解锁此配置")
        return ctypes.string_at(result.data, result.size)
    finally:
        if result.data:
            ctypes.memset(result.data, 0, result.size)
            release(result.data)


def _native_key(vault: str, create: bool) -> bytes | None:
    # Called with an immediate SQLite write transaction whenever creation is allowed.
    try:
        if PLATFORM == "darwin":
            from keyring.backends.macOS import Keyring

            security = ctypes.CDLL("/System/Library/Frameworks/Security.framework/Security")
            disable_ui = security.SecKeychainSetUserInteractionAllowed
            disable_ui.argtypes, disable_ui.restype = (ctypes.c_ubyte,), ctypes.c_int32
            if disable_ui(0):
                raise OSError
            keychain = Keyring()
            saved = keychain.get_password(SERVICE, vault)
            if saved is not None or not create:
                return saved.encode("ascii") if saved is not None else None
            key = base64.urlsafe_b64encode(secrets.token_bytes(32))
            keychain.set_password(SERVICE, vault, key.decode("ascii"))
            return key
        if PLATFORM == "linux":
            import secretstorage

            with closing(secretstorage.dbus_init()) as bus:
                # Open the existing default collection. Do not create or unlock one when polling.
                collection = secretstorage.Collection(bus)
                collection.ensure_not_locked()
                attributes = {"application": SERVICE, "workspace": vault}
                item = next(collection.search_items(attributes), None)
                if item is not None:
                    return item.get_secret()
                if create:
                    key = base64.urlsafe_b64encode(secrets.token_bytes(32))
                    collection.create_item(SERVICE, attributes, key)
                    return key
                return None
    except Exception:
        # DBus and Keychain errors may contain system details. Keep the API error stable.
        raise OSError("系统密钥库不可用或已锁定") from None
    raise OSError("当前系统未提供凭证保护")


def _vault(db: sqlite3.Connection) -> str:
    return db.execute("SELECT vault_id FROM x_connection_revision WHERE singleton=1").fetchone()[0]


def available(db: sqlite3.Connection) -> bool:
    if PLATFORM == "win32":
        return True
    try:
        _native_key(_vault(db), False)
        return True
    except OSError:
        return False


def _fernet(db: sqlite3.Connection, write: bool):
    from cryptography.fernet import Fernet

    # A missing key on a copied database must never strand existing ciphertext by generating another key.
    may_create = write and db.execute("SELECT 1 FROM x_connection_settings LIMIT 1").fetchone() is None
    key = _native_key(_vault(db), may_create)
    if key is None:
        raise OSError("系统密钥库中没有此工作区的密钥")
    return Fernet(key)


def protect(db: sqlite3.Connection, value: str) -> bytes:
    if PLATFORM == "win32":
        return _convert(value.encode(), True)
    try:
        return _fernet(db, True).encrypt(value.encode())
    except (ImportError, ValueError):
        raise OSError("系统密钥库不可用或密钥无效") from None


def unprotect(db: sqlite3.Connection, blob: bytes) -> str:
    if PLATFORM == "win32":
        return _convert(blob, False).decode()
    try:
        return _fernet(db, False).decrypt(blob).decode()
    except Exception:
        raise OSError("系统密钥库无法解锁此配置") from None
