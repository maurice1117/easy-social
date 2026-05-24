from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import desc, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload, selectinload

from .extensions import db
from .media import save_media
from .models import Comment, PollOption, PollVote, Post, User, followers

bp = Blueprint("social", __name__)


def _post_query():
    return Post.query.options(
        joinedload(Post.author),
        joinedload(Post.repost_of).joinedload(Post.author),
        selectinload(Post.poll_options),
        joinedload(Post.repost_of).selectinload(Post.poll_options),
    )


def _comment_counts_for_posts(posts: list[Post]) -> dict[int, int]:
    post_ids = {post.display_post.id for post in posts}
    if not post_ids:
        return {}

    counts = dict.fromkeys(post_ids, 0)
    rows = (
        db.session.query(Comment.post_id, func.count(Comment.id))
        .filter(Comment.post_id.in_(post_ids))
        .group_by(Comment.post_id)
        .all()
    )
    counts.update({post_id: count for post_id, count in rows})
    return counts


def _poll_summaries_for_posts(posts: list[Post]) -> dict[int, dict]:
    post_ids = {post.display_post.id for post in posts}
    if not post_ids:
        return {}

    vote_counts = {
        option_id: count
        for option_id, count in db.session.query(PollVote.option_id, func.count(PollVote.id))
        .filter(PollVote.post_id.in_(post_ids))
        .group_by(PollVote.option_id)
        .all()
    }
    voted_option_ids = {
        post_id: option_id
        for post_id, option_id in db.session.query(PollVote.post_id, PollVote.option_id)
        .filter(
            PollVote.post_id.in_(post_ids),
            PollVote.user_id == current_user.id,
        )
        .all()
    }

    summaries = {}
    for post in posts:
        content = post.display_post
        if not content.poll_options:
            continue
        total_votes = sum(vote_counts.get(option.id, 0) for option in content.poll_options)
        summaries[content.id] = {
            "counts": vote_counts,
            "total_votes": total_votes,
            "voted_option_id": voted_option_ids.get(content.id),
        }
    return summaries


def _poll_option_bodies() -> list[str]:
    option_bodies = []
    for raw_option in request.form.getlist("poll_options"):
        option = raw_option.strip()
        if option and option not in option_bodies:
            option_bodies.append(option)
    return option_bodies


def _followed_user_ids(users: list[User]) -> set[int]:
    user_ids = [user.id for user in users]
    if not user_ids:
        return set()

    return {
        followed_id
        for (followed_id,) in db.session.query(followers.c.followed_id)
        .filter(
            followers.c.follower_id == current_user.id,
            followers.c.followed_id.in_(user_ids),
        )
        .all()
    }


@bp.route("/")
@login_required
def feed():
    followed_ids = db.session.query(followers.c.followed_id).filter(
        followers.c.follower_id == current_user.id
    )
    posts = (
        _post_query()
        .filter(or_(Post.author_id == current_user.id, Post.author_id.in_(followed_ids)))
        .order_by(desc(Post.created_at))
        .limit(100)
        .all()
    )
    return render_template(
        "social/feed.html",
        posts=posts,
        comment_counts=_comment_counts_for_posts(posts),
        poll_summaries=_poll_summaries_for_posts(posts),
    )


@bp.route("/explore")
@login_required
def explore():
    posts = _post_query().order_by(desc(Post.created_at)).limit(100).all()
    users = User.query.filter(User.id != current_user.id).order_by(User.username).limit(50).all()
    return render_template(
        "social/explore.html",
        posts=posts,
        users=users,
        comment_counts=_comment_counts_for_posts(posts),
        poll_summaries=_poll_summaries_for_posts(posts),
        followed_user_ids=_followed_user_ids(users),
    )


@bp.post("/posts")
@login_required
def create_post():
    body = request.form.get("body", "").strip()
    poll_enabled = request.form.get("post_type") == "poll"
    poll_options = _poll_option_bodies() if poll_enabled else []

    try:
        media_filename, media_type = save_media(request.files.get("media"))
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(request.referrer or url_for("social.feed"))

    if poll_enabled and not body:
        flash("Add a poll question before posting.", "error")
        return redirect(request.referrer or url_for("social.feed"))
    if poll_enabled and len(poll_options) < 2:
        flash("Poll posts need at least two options.", "error")
        return redirect(request.referrer or url_for("social.feed"))
    if poll_enabled and len(poll_options) > 4:
        flash("Poll posts can have at most four options.", "error")
        return redirect(request.referrer or url_for("social.feed"))
    if not body and not media_filename:
        flash("Add text, an image, or a video before posting.", "error")
        return redirect(request.referrer or url_for("social.feed"))

    post = Post(
        body=body,
        media_filename=media_filename,
        media_type=media_type,
        author=current_user,
    )
    for position, option_body in enumerate(poll_options, start=1):
        post.poll_options.append(PollOption(body=option_body, position=position))
    db.session.add(post)
    db.session.commit()
    return redirect(url_for("social.feed"))


@bp.get("/posts/<int:post_id>")
@login_required
def post_detail(post_id: int):
    post = _post_query().filter(Post.id == post_id).first_or_404()
    comments = post.comments.order_by(Comment.created_at.asc()).all()
    return render_template(
        "social/post_detail.html",
        post=post,
        comments=comments,
        comment_counts={post.display_post.id: len(comments)},
        poll_summaries=_poll_summaries_for_posts([post]),
    )


@bp.post("/posts/<int:post_id>/poll-votes")
@login_required
def vote_poll(post_id: int):
    post = db.get_or_404(Post, post_id).display_post
    option_id = request.form.get("option_id", type=int)
    option = next((poll_option for poll_option in post.poll_options if poll_option.id == option_id), None)
    if not post.poll_options or option is None:
        flash("Choose a valid poll option.", "error")
        return redirect(request.referrer or url_for("social.post_detail", post_id=post.id))

    existing_vote = PollVote.query.filter_by(post_id=post.id, user_id=current_user.id).first()
    if existing_vote:
        flash("You already voted in this poll.", "error")
        return redirect(request.referrer or url_for("social.post_detail", post_id=post.id))

    db.session.add(PollVote(post=post, option=option, user=current_user))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash("You already voted in this poll.", "error")
        return redirect(request.referrer or url_for("social.post_detail", post_id=post.id))
    return redirect(request.referrer or url_for("social.post_detail", post_id=post.id))


@bp.post("/posts/<int:post_id>/comments")
@login_required
def add_comment(post_id: int):
    post = db.get_or_404(Post, post_id)
    body = request.form.get("body", "").strip()
    if not body:
        flash("Comment cannot be empty.", "error")
    else:
        db.session.add(Comment(body=body, author=current_user, post=post))
        db.session.commit()
    return redirect(url_for("social.post_detail", post_id=post.id))


@bp.post("/posts/<int:post_id>/repost")
@login_required
def repost(post_id: int):
    original = db.get_or_404(Post, post_id).display_post
    if original.author_id == current_user.id:
        flash("You cannot repost your own post.", "error")
        return redirect(request.referrer or url_for("social.feed"))

    existing = Post.query.filter_by(author_id=current_user.id, repost_of_id=original.id).first()
    if existing:
        flash("You already reposted this.", "error")
        return redirect(request.referrer or url_for("social.feed"))

    db.session.add(Post(author=current_user, repost_of=original))
    db.session.commit()
    return redirect(request.referrer or url_for("social.feed"))


@bp.route("/users/<username>")
@login_required
def profile(username: str):
    user = User.query.filter_by(username=username).first_or_404()
    posts = (
        _post_query()
        .filter(Post.author_id == user.id)
        .order_by(desc(Post.created_at))
        .all()
    )
    return render_template(
        "social/profile.html",
        profile_user=user,
        posts=posts,
        comment_counts=_comment_counts_for_posts(posts),
        poll_summaries=_poll_summaries_for_posts(posts),
    )


@bp.post("/users/<username>/follow")
@login_required
def follow(username: str):
    user = User.query.filter_by(username=username).first_or_404()
    current_user.follow(user)
    db.session.commit()
    return redirect(request.referrer or url_for("social.profile", username=user.username))


@bp.post("/users/<username>/unfollow")
@login_required
def unfollow(username: str):
    user = User.query.filter_by(username=username).first_or_404()
    current_user.unfollow(user)
    db.session.commit()
    return redirect(request.referrer or url_for("social.profile", username=user.username))
