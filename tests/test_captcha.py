from __future__ import annotations

import pytest
from flask import session

from easy_social.captcha import SESSION_KEY, create_captcha_challenge, verify_captcha_response

pytestmark = pytest.mark.unit


def test_captcha_challenge_stores_expected_answer(app):
    with app.test_request_context("/auth/register"):
        challenge = create_captcha_challenge()

        assert challenge.prompt == "2 + 3"
        assert challenge.image_data_uri.startswith("data:image/svg+xml;base64,")
        assert session[SESSION_KEY] == "5"


def test_captcha_verification_consumes_answer(app):
    with app.test_request_context("/auth/register"):
        session[SESSION_KEY] = "5"

        assert verify_captcha_response("5")
        assert SESSION_KEY not in session


def test_captcha_rejects_missing_or_wrong_answer(app):
    with app.test_request_context("/auth/register"):
        session[SESSION_KEY] = "5"

        assert not verify_captcha_response("4")
        assert SESSION_KEY not in session
