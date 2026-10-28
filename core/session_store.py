import base64
import ctypes
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from ctypes import wintypes


SESSION_TTL = timedelta(hours=48)
SESSION_DIRECTORY = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
    "KixyStudio4K",
)
SESSION_PATH = os.path.join(SESSION_DIRECTORY, "session.json")


class SessionStorageError(RuntimeError):
    pass


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte)),
    ]


def _protect_api_key(api_key: str) -> str:
    if os.name != "nt":
        raise SessionStorageError(
            "Secure API-key persistence is currently supported on Windows only."
        )

    plain_data = api_key.encode("utf-8")
    plain_buffer = ctypes.create_string_buffer(plain_data)
    input_blob = _DataBlob(
        len(plain_data),
        ctypes.cast(plain_buffer, ctypes.POINTER(ctypes.c_byte)),
    )
    output_blob = _DataBlob()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(_DataBlob),
        wintypes.LPCWSTR,
        ctypes.POINTER(_DataBlob),
        wintypes.LPVOID,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(_DataBlob),
    ]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel32.LocalFree.restype = wintypes.HLOCAL

    if not crypt32.CryptProtectData(
        ctypes.byref(input_blob),
        "KixyStudio 4K API key",
        None,
        None,
        None,
        0,
        ctypes.byref(output_blob),
    ):
        raise SessionStorageError(
            f"Windows could not protect the API key (error {ctypes.get_last_error()})."
        )

    try:
        encrypted = ctypes.string_at(output_blob.pbData, output_blob.cbData)
        return base64.b64encode(encrypted).decode("ascii")
    finally:
        kernel32.LocalFree(output_blob.pbData)


def _unprotect_api_key(encrypted_key: str) -> str:
    if os.name != "nt":
        raise SessionStorageError(
            "Secure API-key retrieval is currently supported on Windows only."
        )

    try:
        encrypted_data = base64.b64decode(encrypted_key, validate=True)
    except (ValueError, TypeError) as error:
        raise SessionStorageError("The saved API key is malformed.") from error

    encrypted_buffer = ctypes.create_string_buffer(encrypted_data)
    input_blob = _DataBlob(
        len(encrypted_data),
        ctypes.cast(encrypted_buffer, ctypes.POINTER(ctypes.c_byte)),
    )
    output_blob = _DataBlob()
    description = wintypes.LPWSTR()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_DataBlob),
        ctypes.POINTER(wintypes.LPWSTR),
        ctypes.POINTER(_DataBlob),
        wintypes.LPVOID,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(_DataBlob),
    ]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel32.LocalFree.restype = wintypes.HLOCAL

    if not crypt32.CryptUnprotectData(
        ctypes.byref(input_blob),
        ctypes.byref(description),
        None,
        None,
        None,
        0,
        ctypes.byref(output_blob),
    ):
        raise SessionStorageError(
            f"Windows could not unlock the saved API key (error {ctypes.get_last_error()})."
        )

    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData).decode("utf-8")
    finally:
        kernel32.LocalFree(output_blob.pbData)
        if description:
            kernel32.LocalFree(description)


def save_session(url: str, api_key: str, now: datetime = None) -> datetime:
    if not url.strip() or not api_key.strip():
        raise SessionStorageError("A video link and API key are required to save the session.")

    saved_at = now or datetime.now(timezone.utc)
    if saved_at.tzinfo is None:
        saved_at = saved_at.replace(tzinfo=timezone.utc)
    expires_at = saved_at.astimezone(timezone.utc) + SESSION_TTL
    data = {
        "url": url.strip(),
        "api_key_protected": _protect_api_key(api_key.strip()),
        "saved_at": saved_at.astimezone(timezone.utc).isoformat(),
        "expires_at": expires_at.isoformat(),
    }

    os.makedirs(SESSION_DIRECTORY, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=SESSION_DIRECTORY,
            prefix=".session-",
            suffix=".tmp",
            delete=False,
        ) as session_file:
            temp_path = session_file.name
            json.dump(data, session_file)
            session_file.flush()
            os.fsync(session_file.fileno())
        os.replace(temp_path, SESSION_PATH)
    except OSError as error:
        raise SessionStorageError(f"Unable to save the local session: {error}") from error
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)

    return expires_at


def load_session(now: datetime = None) -> dict:
    if not os.path.exists(SESSION_PATH):
        return None

    try:
        with open(SESSION_PATH, "r", encoding="utf-8") as session_file:
            data = json.load(session_file)
        if not isinstance(data, dict):
            raise SessionStorageError("The saved local session has an invalid format.")
        if not isinstance(data.get("url"), str) or not isinstance(
            data.get("api_key_protected"), str
        ):
            raise SessionStorageError("The saved link or protected API key is invalid.")
        expires_at = datetime.fromisoformat(data["expires_at"])
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        current_time = now or datetime.now(timezone.utc)
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)

        if current_time >= expires_at:
            clear_session()
            return None

        return {
            "url": data["url"],
            "api_key": _unprotect_api_key(data["api_key_protected"]),
            "expires_at": expires_at.astimezone(timezone.utc),
        }
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise SessionStorageError(f"Unable to load the saved local session: {error}") from error


def clear_session():
    try:
        os.remove(SESSION_PATH)
    except FileNotFoundError:
        return
    except OSError as error:
        raise SessionStorageError(f"Unable to clear the saved local session: {error}") from error
