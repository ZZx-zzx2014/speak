"""SQLite access layer.

A single connection is opened per request and stored on ``flask.g`` so that it
is committed/closed exactly once by the application teardown handler.  All
queries in the project use bound parameters.
"""

import logging
import secrets
import sqlite3
from pathlib import Path

from flask import current_app, g
from werkzeug.security import generate_password_hash

log = logging.getLogger(__name__)

SCHEMA_PATH = Path(__file__).with_name('schema.sql')

#: Same parameters the original project used, kept explicit for clarity.
PASSWORD_HASH_METHOD = 'pbkdf2:sha256'


def get_db():
    """Return the request-scoped connection, opening it on first use."""
    if 'db' not in g:
        config = current_app.config
        timeout = config['SQLITE_TIMEOUT_SECONDS']
        db = sqlite3.connect(
            config['DATABASE'],
            timeout=timeout,
            # Transactions are managed explicitly with ``commit``/``rollback``.
            isolation_level=None,
        )
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys = ON')
        db.execute('PRAGMA busy_timeout = %d' % (int(timeout * 1000),))
        # WAL keeps readers from blocking the writer, which matters because the
        # Socket.IO handlers and the HTTP views share the same file.
        try:
            db.execute('PRAGMA journal_mode = WAL')
        except sqlite3.DatabaseError:  # pragma: no cover - e.g. network volumes
            log.warning('无法启用 WAL 日志模式，回退到默认模式', exc_info=True)
        g.db = db
    return g.db


def close_db(exc=None):
    """Teardown handler: roll back on error, otherwise close the connection."""
    db = g.pop('db', None)
    if db is None:
        return
    try:
        if exc is not None:
            db.rollback()
    finally:
        db.close()


def init_app(app):
    """Register the connection lifecycle with ``app``."""
    app.teardown_appcontext(close_db)


def init_db():
    """Create the schema and apply additive migrations.

    Safe to call on every start, including against a ``database.db`` created by
    the original version of the project.
    """
    db = get_db()
    with SCHEMA_PATH.open(encoding='utf-8') as handle:
        db.executescript(handle.read())
    _migrate(db)


def _migrate(db):
    """Add columns that older databases are missing.

    ``CREATE TABLE IF NOT EXISTS`` leaves an existing table untouched, so new
    columns have to be added explicitly.  All migrations here are additive.
    """
    columns = {row['name'] for row in db.execute('PRAGMA table_info(users)')}

    if 'created_at' not in columns:
        # SQLite only accepts a constant default in ALTER TABLE, so the column
        # is added empty and then backfilled.
        db.execute("ALTER TABLE users ADD COLUMN created_at TEXT NOT NULL DEFAULT ''")
        db.execute("UPDATE users SET created_at = datetime('now') WHERE created_at = ''")
        log.info('已为 users 表补充 created_at 列。')


def seed_admin():
    """Create the initial administrator account if it does not exist yet.

    The password comes from ``SPEAK_ADMIN_PASSWORD``.  Without it, debug mode
    falls back to the historical ``root``/``root`` credentials (with a warning)
    while a production start generates a random password that is logged once.
    """
    config = current_app.config
    username = config['ADMIN_USERNAME']
    db = get_db()

    if db.execute('SELECT 1 FROM users WHERE username = ?', (username,)).fetchone():
        return

    password = config['ADMIN_PASSWORD']
    generated = False
    if not password:
        if config['DEBUG'] or config['TESTING']:
            password = 'root'
        else:
            password = secrets.token_urlsafe(12)
            generated = True

    db.execute(
        'INSERT INTO users (username, password, is_admin) VALUES (?, ?, 1)',
        (username, generate_password_hash(password, method=PASSWORD_HASH_METHOD)),
    )

    if generated:
        log.warning(
            '已创建管理员账户 %r，随机初始密码为: %s  ——请立即登录并修改，'
            '或通过 SPEAK_ADMIN_PASSWORD 环境变量指定。',
            username, password,
        )
    elif not config['ADMIN_PASSWORD']:
        log.warning(
            '已创建管理员账户 %r，使用默认弱密码 "root"。'
            '生产环境请设置 SPEAK_ADMIN_PASSWORD。',
            username,
        )
    else:
        log.info('已创建管理员账户 %r。', username)
