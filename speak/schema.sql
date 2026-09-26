-- Schema for the Speak chat application.
-- Applied with ``executescript`` on every start, so every statement must be
-- idempotent.

CREATE TABLE IF NOT EXISTS users (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    username   TEXT    NOT NULL UNIQUE,
    password   TEXT    NOT NULL,
    is_admin   INTEGER NOT NULL DEFAULT 0 CHECK (is_admin IN (0, 1)),
    email      TEXT,
    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_users_is_admin ON users (is_admin);

-- 注意：邮箱的唯一索引**不在这里建**。
-- 旧数据库的 users 表没有 email 列，而 CREATE TABLE IF NOT EXISTS 不会补列，
-- 在这里建索引会直接报 "no such column: email" 导致启动失败。
-- 索引统一放在 speak/db.py 的 _migrate() 里，等 ALTER TABLE 补完列之后再建。

-- Runtime editable settings (site name, Cloudflare keys, ...).  Values saved
-- here take precedence over the environment so the operator can change them
-- from the admin UI without redeploying.
CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
