# Poll Post Database Design

## Tables

### `post`

Poll posts reuse the existing `post` table. A post is considered a poll when it has related rows in `poll_option`.

Relevant fields:

- `id`: primary key.
- `body`: poll question text.
- `author_id`: poll creator.
- `created_at`: ordering timestamp.
- `repost_of_id`: reposts point at the original poll post.

### `poll_option`

Stores up to four selectable choices for a poll post.

- `id`: primary key.
- `post_id`: foreign key to `post.id`.
- `body`: option label, up to 280 characters.
- `position`: display order.

Constraints:

- `uq_poll_option_position` prevents duplicate option positions within the same poll.

### `poll_vote`

Stores one selected option per user per poll post.

- `id`: primary key.
- `post_id`: foreign key to `post.id`.
- `option_id`: foreign key to `poll_option.id`.
- `user_id`: foreign key to `user.id`.
- `created_at`: vote timestamp.

Constraints:

- `uq_poll_vote_post_user` prevents a user from voting more than once in the same poll.

## Relationships

- `Post.poll_options` has many `PollOption` rows.
- `PollOption.votes` has many `PollVote` rows.
- `PollVote.post` points to the poll post for uniqueness checks and aggregation.
- `PollVote.option` points to the selected option.
- `PollVote.user` points to the voter.

## Validation

The application accepts poll posts with 2 to 4 non-empty, unique options. Vote percentages are calculated from `poll_vote` counts after the user votes.

## SQL Schema Reference

```sql
CREATE TABLE poll_option (
    id INTEGER PRIMARY KEY,
    post_id INTEGER NOT NULL REFERENCES post(id),
    body VARCHAR(280) NOT NULL,
    position INTEGER NOT NULL,
    CONSTRAINT uq_poll_option_position UNIQUE (post_id, position)
);

CREATE INDEX ix_poll_option_post_id ON poll_option (post_id);

CREATE TABLE poll_vote (
    id INTEGER PRIMARY KEY,
    post_id INTEGER NOT NULL REFERENCES post(id),
    option_id INTEGER NOT NULL REFERENCES poll_option(id),
    user_id INTEGER NOT NULL REFERENCES user(id),
    created_at TIMESTAMP NOT NULL,
    CONSTRAINT uq_poll_vote_post_user UNIQUE (post_id, user_id)
);

CREATE INDEX ix_poll_vote_post_id ON poll_vote (post_id);
CREATE INDEX ix_poll_vote_option_id ON poll_vote (option_id);
CREATE INDEX ix_poll_vote_user_id ON poll_vote (user_id);
```
