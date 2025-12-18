"""Telegram Mini App (WebApp) initData validation helpers."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl


class WebAppAuthError(RuntimeError):
    pass


@dataclass(frozen=True)
class WebAppAuthResult:
    user: dict[str, Any]
    auth_date: int
    raw: dict[str, str]


def validate_webapp_init_data(init_data: str, *, bot_token: str, max_age_seconds: int = 86400) -> WebAppAuthResult:
    """
    Validate Telegram WebApp initData using the official HMAC scheme.

    Notes:
    - initData must be validated server-side; initDataUnsafe is not trusted.
    - secret_key = HMAC_SHA256(key="WebAppData", msg=bot_token)
    - data_check_string = key=value lines sorted by key, joined with "\\n" (excluding "hash")
    """
    init_data = (init_data or "").strip()
    if not init_data:
        raise WebAppAuthError("initData is missing")

    try:
        raw_pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
    except ValueError as e:
        raise WebAppAuthError("initData is invalid") from e
    raw: dict[str, str] = {k: v for k, v in raw_pairs}

    provided_hash = raw.get("hash")
    if not provided_hash:
        raise WebAppAuthError("initData hash is missing")

    auth_date_str = raw.get("auth_date") or "0"
    try:
        auth_date = int(auth_date_str)
    except Exception as e:
        raise WebAppAuthError("initData auth_date is invalid") from e

    if max_age_seconds > 0:
        now = int(time.time())
        if auth_date <= 0 or now - auth_date > int(max_age_seconds):
            raise WebAppAuthError("initData is expired")

    check_pairs = [(k, v) for k, v in raw.items() if k != "hash"]
    check_pairs.sort(key=lambda kv: kv[0])
    data_check_string = "\n".join(f"{k}={v}" for k, v in check_pairs)

    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated_hash, provided_hash):
        raise WebAppAuthError("initData hash mismatch")

    user_json = raw.get("user")
    if not user_json:
        raise WebAppAuthError("initData user is missing")

    try:
        user = json.loads(user_json)
    except Exception as e:
        raise WebAppAuthError("initData user is invalid JSON") from e

    if not isinstance(user, dict) or "id" not in user:
        raise WebAppAuthError("initData user is invalid")

    return WebAppAuthResult(user=user, auth_date=auth_date, raw=raw)
