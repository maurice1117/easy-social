from __future__ import annotations

from io import BytesIO

import pytest
from sqlalchemy import event

from easy_social.extensions import db
from easy_social.models import Comment, PollOption, PollVote, Post, User
from scripts.import_fake_data import DEFAULT_DATA_DIR, import_fake_data

from conftest import login, logout, register

pytestmark = pytest.mark.integration


def test_register_login_and_create_text_post(client, app):
    response = register(client, "alice")

    assert response.status_code == 200
    assert b"Feed" in response.data

    client.post("/posts", data={"body": "Hello world"}, follow_redirects=True)

    with app.app_context():
        user = User.query.filter_by(username="alice").one()
        post = Post.query.filter_by(author_id=user.id).one()
        assert post.body == "Hello world"
        assert post.media_filename is None


def test_register_rejects_invalid_captcha(client, app):
    client.get("/auth/register")

    response = client.post(
        "/auth/register",
        data={
            "username": "bot",
            "email": "bot@example.com",
            "password": "password",
            "captcha_answer": "999",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"CAPTCHA answer is incorrect" in response.data
    with app.app_context():
        assert User.query.filter_by(username="bot").first() is None


def test_create_image_post(client, app):
    register(client, "alice")

    response = client.post(
        "/posts",
        data={
            "body": "Picture",
            "media": (BytesIO(b"fake-image-data"), "photo.png"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    with app.app_context():
        post = Post.query.one()
        assert post.media_type == "image"
        assert post.media_filename.endswith(".png")


def test_create_poll_post_and_vote(client, app):
    register(client, "alice")

    response = client.post(
        "/posts",
        data={
            "body": "Which feature should ship next?",
            "post_type": "poll",
            "poll_options": ["Polls", "Search", "Bookmarks", ""],
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    with app.app_context():
        post = Post.query.filter_by(body="Which feature should ship next?").one()
        post_id = post.id
        options = PollOption.query.filter_by(post_id=post.id).order_by(PollOption.position).all()
        assert [option.body for option in options] == ["Polls", "Search", "Bookmarks"]

    with app.app_context():
        option_id = PollOption.query.filter_by(post_id=post_id, body="Polls").one().id

    response = client.post(
        f"/posts/{post_id}/poll-votes",
        data={"option_id": option_id},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"100%" in response.data
    assert b"1 vote" in response.data
    with app.app_context():
        assert PollVote.query.count() == 1


def test_poll_rejects_duplicate_vote(client, app):
    register(client, "alice")
    client.post(
        "/posts",
        data={
            "body": "Pick one",
            "post_type": "poll",
            "poll_options": ["A", "B"],
        },
        follow_redirects=True,
    )

    with app.app_context():
        post = Post.query.filter_by(body="Pick one").one()
        post_id = post.id
        option_id = post.poll_options[0].id

    client.post(f"/posts/{post_id}/poll-votes", data={"option_id": option_id})
    response = client.post(
        f"/posts/{post_id}/poll-votes",
        data={"option_id": option_id},
        follow_redirects=True,
    )

    assert b"You already voted in this poll" in response.data
    with app.app_context():
        assert PollVote.query.count() == 1


def test_poll_rejects_more_than_four_options(client, app):
    register(client, "alice")

    response = client.post(
        "/posts",
        data={
            "body": "Too many options",
            "post_type": "poll",
            "poll_options": ["A", "B", "C", "D", "E"],
        },
        follow_redirects=True,
    )

    assert b"Poll posts can have at most four options" in response.data
    with app.app_context():
        assert Post.query.filter_by(body="Too many options").first() is None


def test_following_adds_users_posts_to_feed(client, app):
    register(client, "alice")
    logout(client)
    register(client, "bob")
    client.post("/posts", data={"body": "Bob update"}, follow_redirects=True)
    logout(client)
    login(client, "alice")

    before_follow = client.get("/")
    assert b"Bob update" not in before_follow.data

    client.post("/users/bob/follow", follow_redirects=True)
    after_follow = client.get("/")

    assert b"Bob update" in after_follow.data
    with app.app_context():
        alice = User.query.filter_by(username="alice").one()
        bob = User.query.filter_by(username="bob").one()
        assert alice.is_following(bob)


def test_repost_and_comment(client, app):
    register(client, "alice")
    client.post("/posts", data={"body": "Original"}, follow_redirects=True)
    logout(client)
    register(client, "bob")

    with app.app_context():
        original_id = Post.query.filter_by(body="Original").one().id

    client.post(f"/posts/{original_id}/repost", follow_redirects=True)
    client.post(
        f"/posts/{original_id}/comments",
        data={"body": "Nice post"},
        follow_redirects=True,
    )

    with app.app_context():
        repost = Post.query.filter_by(repost_of_id=original_id).one()
        comment = Comment.query.one()
        assert repost.author.username == "bob"
        assert comment.body == "Nice post"
        assert comment.post_id == original_id


def test_explore_batches_comment_counts_and_follow_state(client, app):
    register(client, "alice")

    with app.app_context():
        alice = User.query.filter_by(username="alice").one()
        for index in range(8):
            user = User(username=f"user{index}", email=f"user{index}@example.com")
            user.set_password("password")
            post = Post(author=user, body=f"Post {index}")
            db.session.add_all([user, post])
            db.session.flush()
            db.session.add(Comment(author=alice, post=post, body=f"Comment {index}"))
            if index % 2 == 0:
                alice.follow(user)
        db.session.commit()

    statements = []

    def track_statement(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    with app.app_context():
        event.listen(db.engine, "before_cursor_execute", track_statement)
        try:
            response = client.get("/explore")
        finally:
            event.remove(db.engine, "before_cursor_execute", track_statement)

    assert response.status_code == 200
    assert b"Post 0" in response.data
    assert len(statements) <= 8


def test_import_fake_data_adds_comments_to_each_seed_post(app):
    with app.app_context():
        first_counts = import_fake_data(DEFAULT_DATA_DIR)
        seeded_posts = Post.query.filter_by(repost_of_id=None).all()

        assert seeded_posts
        assert first_counts["comments_created"] > 0
        for post in seeded_posts:
            assert 3 <= post.comments.count() <= 5

        comment_count = Comment.query.count()
        second_counts = import_fake_data(DEFAULT_DATA_DIR)

        assert second_counts["comments_created"] == 0
        assert Comment.query.count() == comment_count
