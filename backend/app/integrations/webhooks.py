"""Outbound event webhook (n8n, Zapier, Slack relay, custom service, ...).

Events are POSTed as JSON to WEBHOOK_URL with an `event` discriminator, so
routing lives in your automation tool, not here. When WEBHOOK_SECRET is set
every body is signed: header X-Strata-Signature = sha256=<hex HMAC>.
Fire-and-forget: a down receiver never fails a request. Off when unset.

Events:
  file.failed              parsing/indexing failed
  access_request.created   cross-department request awaiting approval
  access_request.decided   approved / denied
"""

import hashlib
import hmac
import json
import logging
from datetime import UTC, datetime

import httpx

from app.config import get_settings

logger = logging.getLogger("strata.webhooks")


def sign(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def notify(event: str, payload: dict) -> None:
    s = get_settings()
    if not s.webhook_url:
        return
    body = json.dumps(
        {"event": event, "sent_at": datetime.now(UTC).isoformat(), "source": s.app_name, **payload},
        default=str,
    ).encode()
    headers = {"Content-Type": "application/json"}
    if s.webhook_secret:
        headers["X-Strata-Signature"] = sign(body, s.webhook_secret)
    try:
        httpx.post(s.webhook_url, content=body, headers=headers, timeout=s.webhook_timeout).raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("webhook %s failed: %s", event, exc)
