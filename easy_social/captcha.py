from __future__ import annotations

import base64
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html import escape
from random import SystemRandom

from flask import current_app, session
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db
from .models import CaptchaChallengeRecord

SESSION_KEY = "registration_captcha_challenge_id"
DEFAULT_TTL_SECONDS = 10 * 60

_random = SystemRandom()


@dataclass(frozen=True)
class CaptchaChallenge:
    prompt: str
    image_data_uri: str


def _challenge_parts() -> tuple[str, int]:
    if current_app.config.get("TESTING"):
        return "2 + 3", 5

    left = _random.randint(2, 9)
    right = _random.randint(1, 9)
    if _random.choice((True, False)):
        return f"{left} + {right}", left + right

    if right > left:
        left, right = right, left
    return f"{left} - {right}", left - right


def _svg_data_uri(prompt: str) -> str:
    escaped_prompt = escape(prompt)
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="180" height="58" viewBox="0 0 180 58" role="img" aria-label="CAPTCHA challenge">
  <rect width="180" height="58" rx="8" fill="#eef1f4"/>
  <path d="M8 44 C42 12, 72 68, 116 18 S156 36, 172 14" fill="none" stroke="#b8c4ce" stroke-width="3"/>
  <path d="M14 18 L166 45" stroke="#d5dde4" stroke-width="2"/>
  <text x="90" y="38" text-anchor="middle" font-family="Arial, sans-serif" font-size="28" font-weight="700" fill="#1c232b">{escaped_prompt}</text>
</svg>"""
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def create_captcha_challenge() -> CaptchaChallenge:
    prompt, answer = _challenge_parts()
    now = datetime.now(timezone.utc)
    db.session.query(CaptchaChallengeRecord).filter(
        CaptchaChallengeRecord.expires_at <= now
    ).delete(synchronize_session=False)

    challenge_id = secrets.token_urlsafe(32)
    ttl_seconds = current_app.config.get("CAPTCHA_TTL_SECONDS", DEFAULT_TTL_SECONDS)
    db.session.add(
        CaptchaChallengeRecord(
            id=challenge_id,
            answer_hash=generate_password_hash(str(answer)),
            expires_at=now + timedelta(seconds=ttl_seconds),
        )
    )
    db.session.commit()
    session[SESSION_KEY] = challenge_id
    return CaptchaChallenge(prompt=prompt, image_data_uri=_svg_data_uri(prompt))


def verify_captcha_response(response: str) -> bool:
    challenge_id = session.pop(SESSION_KEY, None)
    if not challenge_id:
        return False

    challenge = db.session.get(CaptchaChallengeRecord, challenge_id)
    if not challenge:
        return False

    expires_at = challenge.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    is_valid = expires_at > datetime.now(timezone.utc) and check_password_hash(
        challenge.answer_hash, response.strip()
    )
    db.session.delete(challenge)
    db.session.commit()
    return is_valid
