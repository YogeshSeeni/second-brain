"""Whoop V2 developer API client — OAuth 2.0 with refresh tokens.

Endpoints (v2):
  GET /v2/cycle                 — recent physiological cycles
  GET /v2/recovery              — recovery per cycle
  GET /v2/activity/sleep        — sleep sessions
  GET /v2/activity/workout      — workouts

Refresh token is stored in AWS Secrets Manager under `brain/whoop_oauth` as a
JSON blob: {"access_token": ..., "refresh_token": ..., "expires_at": <epoch>}.

Poll cadence: piggybacks on brain-tick.py every 15 min (see tick.py Day 3).
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import httpx

from . import db

logger = logging.getLogger(__name__)

WHOOP_BASE = "https://api.prod.whoop.com/developer"
WHOOP_TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
SECRET_NAME = os.environ.get("BRAIN_WHOOP_SECRET", "brain/whoop_oauth")
REGION = os.environ.get("AWS_REGION", "us-west-2")


def _load_creds_from_env() -> dict[str, Any] | None:
    """Fallback for local dev: read creds from BRAIN_WHOOP_OAUTH_JSON env var."""
    raw = os.environ.get("BRAIN_WHOOP_OAUTH_JSON")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("BRAIN_WHOOP_OAUTH_JSON is not valid JSON")
        return None


def _load_creds_from_secrets() -> dict[str, Any] | None:
    """Fetch the OAuth blob from AWS Secrets Manager."""
    try:
        import boto3
    except ImportError:
        logger.warning("boto3 not installed — cannot load whoop creds from secrets")
        return None
    try:
        client = boto3.client("secretsmanager", region_name=REGION)
        resp = client.get_secret_value(SecretId=SECRET_NAME)
        return json.loads(resp["SecretString"])
    except Exception as exc:
        logger.warning("failed to load %s from secrets manager: %s", SECRET_NAME, exc)
        return None


def _load_creds() -> dict[str, Any] | None:
    return _load_creds_from_env() or _load_creds_from_secrets()


async def _refresh(creds: dict[str, Any]) -> dict[str, Any] | None:
    """Exchange a refresh_token for a new access_token."""
    client_id = os.environ.get("BRAIN_WHOOP_CLIENT_ID")
    client_secret = os.environ.get("BRAIN_WHOOP_CLIENT_SECRET")
    if not client_id or not client_secret:
        logger.warning("whoop client creds missing — set BRAIN_WHOOP_CLIENT_ID/SECRET")
        return None
    async with httpx.AsyncClient(timeout=15) as http:
        resp = await http.post(
            WHOOP_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": creds["refresh_token"],
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": "offline",
            },
        )
    if resp.status_code != 200:
        logger.error("whoop refresh failed: %s %s", resp.status_code, resp.text[:300])
        return None
    payload = resp.json()
    return {
        "access_token": payload["access_token"],
        "refresh_token": payload.get("refresh_token", creds["refresh_token"]),
        "expires_at": int(time.time()) + int(payload.get("expires_in", 3600)) - 60,
    }


async def _access_token() -> str | None:
    creds = _load_creds()
    if not creds:
        return None
    if creds.get("expires_at", 0) > time.time() + 30:
        return creds["access_token"]
    refreshed = await _refresh(creds)
    if not refreshed:
        return None
    # NB: persisting refreshed creds back to secrets manager is a Day 3 task;
    # for now, rely on expires_at being short and refreshing each poll.
    return refreshed["access_token"]


async def _get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    token = await _access_token()
    if not token:
        return None
    async with httpx.AsyncClient(timeout=15) as http:
        resp = await http.get(
            f"{WHOOP_BASE}{path}",
            params=params or {},
            headers={"Authorization": f"Bearer {token}"},
        )
    if resp.status_code != 200:
        logger.warning("whoop GET %s failed: %s %s", path, resp.status_code, resp.text[:200])
        return None
    return resp.json()


async def latest_recovery() -> dict[str, Any] | None:
    """Pull the latest recovery record and upsert it into whoop_recovery."""
    payload = await _get("/v2/recovery", {"limit": 1})
    if not payload:
        return None
    records = payload.get("records", [])
    if not records:
        return None
    rec = records[0]
    score = rec.get("score", {}) or {}
    cycle_id = str(rec.get("cycle_id") or rec.get("id") or "")
    if not cycle_id:
        return None

    import aiosqlite

    row = {
        "cycle_id": cycle_id,
        "start_at": _iso_to_epoch(rec.get("created_at")),
        "end_at": _iso_to_epoch(rec.get("updated_at")),
        "recovery_score": score.get("recovery_score"),
        "hrv_ms": score.get("hrv_rmssd_milli"),
        "resting_hr": score.get("resting_heart_rate"),
        "last_seen": int(time.time()),
    }
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute(
            "INSERT INTO whoop_recovery "
            "(cycle_id, start_at, end_at, recovery_score, hrv_ms, resting_hr, last_seen) "
            "VALUES (:cycle_id, :start_at, :end_at, :recovery_score, :hrv_ms, :resting_hr, :last_seen) "
            "ON CONFLICT(cycle_id) DO UPDATE SET "
            "  end_at = excluded.end_at, "
            "  recovery_score = excluded.recovery_score, "
            "  hrv_ms = excluded.hrv_ms, "
            "  resting_hr = excluded.resting_hr, "
            "  last_seen = excluded.last_seen",
            row,
        )
        await conn.commit()
    return row


def _iso_to_epoch(value: Any) -> int:
    if not value:
        return 0
    try:
        from datetime import datetime

        return int(datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp())
    except Exception:
        return 0
