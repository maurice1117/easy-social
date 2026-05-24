# 投票貼文資料庫設計

## 資料表

### `post`

投票貼文沿用既有的 `post` 資料表。當一篇貼文在 `poll_option` 中有相關資料列時，就會被視為投票。

相關欄位：

- `id`: 主鍵。
- `body`: 投票問題文字。
- `author_id`: 投票建立者。
- `created_at`: 用於排序的時間戳記。
- `repost_of_id`: 轉貼會指向原始投票貼文。

### `poll_option`

儲存一篇投票貼文最多四個可選選項。

- `id`: 主鍵。
- `post_id`: 指向 `post.id` 的外鍵。
- `body`: 選項標籤，最多 280 個字元。
- `position`: 顯示順序。

限制：

- `uq_poll_option_position` 防止同一個投票中出現重複的選項位置。
- `ck_poll_option_position_range` 確保選項位置維持在支援的 1 到 4 範圍內。

### `poll_vote`

儲存每位使用者在每篇投票貼文中選擇的一個選項。

- `id`: 主鍵。
- `post_id`: 指向 `post.id` 的外鍵。
- `option_id`: 指向 `poll_option.id` 的外鍵。
- `user_id`: 指向 `user.id` 的外鍵。
- `created_at`: 投票時間戳記。

限制：

- `uq_poll_vote_post_user` 防止使用者在同一個投票中重複投票。

## 關聯

- `Post.poll_options` 擁有多筆 `PollOption` 資料列。
- `PollOption.votes` 擁有多筆 `PollVote` 資料列。
- `PollVote.post` 指向投票貼文，用於唯一性檢查與彙總。
- `PollVote.option` 指向被選擇的選項。
- `PollVote.user` 指向投票者。

## 驗證

應用程式接受包含 2 到 4 個非空白且不重複選項的投票貼文。使用者投票後，投票百分比會根據 `poll_vote` 的計數計算。

## SQL Schema 參考

```sql
CREATE TABLE poll_option (
    id INTEGER PRIMARY KEY,
    post_id INTEGER NOT NULL REFERENCES post(id),
    body VARCHAR(280) NOT NULL,
    position INTEGER NOT NULL,
    CONSTRAINT ck_poll_option_position_range CHECK (position BETWEEN 1 AND 4),
    CONSTRAINT uq_poll_option_position UNIQUE (post_id, position)
);

CREATE INDEX ix_poll_option_post_id ON poll_option (post_id);

CREATE TABLE poll_vote (
    id INTEGER PRIMARY KEY,
    post_id INTEGER NOT NULL REFERENCES post(id),
    option_id INTEGER NOT NULL REFERENCES poll_option(id),
    user_id INTEGER NOT NULL REFERENCES user(id),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_poll_vote_post_user UNIQUE (post_id, user_id)
);

CREATE INDEX ix_poll_vote_post_id ON poll_vote (post_id);
CREATE INDEX ix_poll_vote_option_id ON poll_vote (option_id);
CREATE INDEX ix_poll_vote_user_id ON poll_vote (user_id);
```
