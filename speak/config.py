"""Configuration for the Speak chat application.

Every value can be overridden with an environment variable (see ``.env.example``)
so that secrets and deployment-specific settings never have to be committed to
the repository.  :class:`Config` holds development-friendly defaults while still
being safe-by-default for a small production deployment.
"""

import os
from datetime import timedelta
from pathlib import Path

#: Project root, i.e. the directory that contains ``app.py``.
BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default=False):
    """Read a boolean environment variable."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {'1', 'true', 'yes', 'on'}


def env_int(name, default):
    """Read an integer environment variable, falling back on bad input."""
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw.strip())
    except (TypeError, ValueError):
        return default


def env_list(name, default):
    """Read a comma separated environment variable as a list."""
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return list(default)
    return [item.strip() for item in raw.split(',') if item.strip()]


class Config:
    """Default application configuration."""

    # --- Core -----------------------------------------------------------
    #: Required in production.  When unset, ``create_app`` generates a random
    #: key: ephemeral in debug mode, persisted to :data:`SECRET_KEY_FILE`
    #: otherwise, so that ``python app.py`` works without extra setup.
    SECRET_KEY = os.environ.get('SPEAK_SECRET_KEY')
    SECRET_KEY_FILE = os.environ.get('SPEAK_SECRET_KEY_FILE') or str(BASE_DIR / '.secret_key')
    DEBUG = env_bool('SPEAK_DEBUG', False)
    TESTING = False

    #: SQLite database file.  Defaults to the ``database.db`` file that the
    #: original project shipped at the repository root.
    DATABASE = os.environ.get('SPEAK_DATABASE') or str(BASE_DIR / 'database.db')
    SQLITE_TIMEOUT_SECONDS = env_int('SPEAK_SQLITE_TIMEOUT', 5)

    #: Bind address of the built-in development server.  Loopback by default:
    #: exposing the Werkzeug dev server to the network is opt-in.
    HOST = os.environ.get('SPEAK_HOST', '127.0.0.1')
    PORT = env_int('SPEAK_PORT', 5002)

    # --- Sessions and cookies -------------------------------------------
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    #: Turn on when serving over HTTPS.
    SESSION_COOKIE_SECURE = env_bool('SPEAK_COOKIE_SECURE', False)
    PERMANENT_SESSION_LIFETIME = timedelta(hours=env_int('SPEAK_SESSION_HOURS', 12))
    MAX_CONTENT_LENGTH = env_int('SPEAK_MAX_CONTENT_LENGTH', 64 * 1024)

    # --- Socket.IO --------------------------------------------------------
    #: ``threading`` requires no monkey patching and works everywhere, but only
    #: offers HTTP long-polling.  Use ``gevent``/``eventlet`` (with the extra
    #: installed) to get WebSocket support.
    SOCKETIO_ASYNC_MODE = os.environ.get('SPEAK_SOCKETIO_ASYNC_MODE', 'threading')
    SOCKETIO_PATH = os.environ.get('SPEAK_SOCKETIO_PATH', 'socket.io')
    #: An empty list disables CORS response headers, which makes the browser
    #: enforce the same-origin policy for the Socket.IO handshake.
    SOCKETIO_CORS_ALLOWED_ORIGINS = env_list('SPEAK_SOCKETIO_CORS_ALLOWED_ORIGINS', [])
    SOCKETIO_LOGGER = env_bool('SPEAK_SOCKETIO_LOGGER', False)
    SOCKETIO_ENGINEIO_LOGGER = env_bool('SPEAK_SOCKETIO_ENGINEIO_LOGGER', False)
    #: ``None`` auto-detects the browser build that matches the installed
    #: Engine.IO protocol version (see :mod:`speak.socketio_client`).
    SOCKETIO_CLIENT_VERSION = os.environ.get('SPEAK_SOCKETIO_CLIENT_VERSION') or None
    #: CDN mirrors tried in order by the browser when loading the client.
    #: ``{version}`` is substituted with the resolved client version.
    #: Leave empty to use the mirror set that matches the installed Engine.IO
    #: generation (the file name differs between client 2.x and 4.x, so the
    #: default is resolved at runtime — see :mod:`speak.socketio_client`).
    SOCKETIO_CDN_BASES = env_list('SPEAK_SOCKETIO_CDN_BASES', [])

    # --- Bootstrap administrator ------------------------------------------
    ADMIN_USERNAME = os.environ.get('SPEAK_ADMIN_USERNAME', 'root')
    #: When unset: ``root`` while debugging (with a loud warning), otherwise a
    #: random password that is logged once at startup.
    ADMIN_PASSWORD = os.environ.get('SPEAK_ADMIN_PASSWORD') or None

    # --- Chat behaviour ----------------------------------------------------
    CHAT_ROOM = os.environ.get('SPEAK_CHAT_ROOM', 'main_room')
    CHAT_MAX_MESSAGE_LENGTH = env_int('SPEAK_CHAT_MAX_MESSAGE_LENGTH', 500)
    CHAT_HISTORY_SIZE = env_int('SPEAK_CHAT_HISTORY_SIZE', 50)
    CHAT_MESSAGES_PER_WINDOW = env_int('SPEAK_CHAT_MESSAGES_PER_WINDOW', 20)
    CHAT_RATE_WINDOW_SECONDS = env_int('SPEAK_CHAT_RATE_WINDOW_SECONDS', 10)

    # --- Authentication hardening -------------------------------------------
    USERNAME_MIN_LENGTH = 3
    USERNAME_MAX_LENGTH = 20
    PASSWORD_MIN_LENGTH = 8
    PASSWORD_MAX_LENGTH = 128
    LOGIN_MAX_ATTEMPTS = env_int('SPEAK_LOGIN_MAX_ATTEMPTS', 5)
    LOGIN_WINDOW_SECONDS = env_int('SPEAK_LOGIN_WINDOW_SECONDS', 300)

    # --- Response hardening --------------------------------------------------
    SECURITY_HEADERS = env_bool('SPEAK_SECURITY_HEADERS', True)
    #: Blocks inline scripts (the main XSS vector) while still allowing the
    #: Socket.IO client to be loaded from any HTTPS mirror.
    CONTENT_SECURITY_POLICY = os.environ.get(
        'SPEAK_CONTENT_SECURITY_POLICY',
        "default-src 'self'; script-src 'self' https:; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; connect-src 'self' ws: wss:; font-src 'self'; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
    )
