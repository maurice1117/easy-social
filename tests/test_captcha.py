from __future__ import annotations

import pytest
from flask import session

from easy_social.captcha import SESSION_KEY, create_captcha_challenge, verify_captcha_response
from easy_social.extensions import db
from easy_social.models import CaptchaChallengeRecord

pytestmark = pytest.mark.unit


def test_captcha_challenge_stores_only_challenge_id_in_session(app):
    with app.test_request_context("/auth/register"):
        challenge = create_captcha_challenge()
        challenge_id = session[SESSION_KEY]
        stored_challenge = db.session.get(CaptchaChallengeRecord, challenge_id)

        assert challenge.prompt == "2 + 3"
        assert challenge.image_data_uri.startswith("data:image/svg+xml;base64,")
        assert stored_challenge is not None
        assert stored_challenge.answer_hash != "5"


def test_captcha_verification_consumes_answer(app):
    with app.test_request_context("/auth/register"):
        create_captcha_challenge()

        assert verify_captcha_response("5")
        assert SESSION_KEY not in session
        assert CaptchaChallengeRecord.query.count() == 0


def test_captcha_rejects_missing_or_wrong_answer(app):
    with app.test_request_context("/auth/register"):
        create_captcha_challenge()

        assert not verify_captcha_response("4")
        assert SESSION_KEY not in session
        assert CaptchaChallengeRecord.query.count() == 0
