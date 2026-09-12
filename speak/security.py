"""Cross-cutting security helpers: CSRF protection, access decorators, rate
limiting and response hardening."""

import hmac
import logging
import secrets
import threading
import time
from functools import wraps

from flask import abort, current_app, flash, redirect, request, session, url_for

log = logging.getLogger(__name__)

CSRF_SESSION_KEY = '_csrf_token'
CSRF_FIELD_NAME = 'csrf_token'
CSRF_HEADER_NAME = 'X-CSRF-Token'
_UNSAFE_METHODS = frozenset({'POST', 'PUT', 'PATCH', 'DELETE'})


# --------------------------------------------------------------------------- #
# CSRF
# --------------------------------------------------------------------------- #
def generate_csrf_token():
    """Return the per-session CSRF token, creating it on first use."""
    token = session.get(CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        session[CSRF_SESSION_KEY] = token
    return token


def _submitted_csrf_token():
    return (
        request.form.get(CSRF_FIELD_NAME)
        or request.headers.get(CSRF_HEADER_NAME)
        or ''
    )


def protect_from_csrf():
    """``before_request`` hook rejecting unsafe requests without a valid token.

    The Socket.IO endpoint is skipped: Engine.IO uses ``POST`` for its polling
    transport and authenticates through the Flask session cookie instead.
    """
    if request.method not in _UNSAFE_METHODS:
        return None

    socketio_path = current_app.config['SOCKETIO_PATH'].strip('/')
    if socketio_path and request.path.lstrip('/').startswith(socketio_path):
        return None

    expected = session.get(CSRF_SESSION_KEY) or ''
    provided = _submitted_csrf_token()
    if not expected or not provided or not hmac.compare_digest(expected, provided):
        log.warning('拒绝 CSRF 校验失败的请求: %s %s', request.method, request.path)
        abort(400, description='安全校验失败，请刷新页面后重试。')
    return None


# --------------------------------------------------------------------------- #
# Access control
# --------------------------------------------------------------------------- #
def login_required(view):
    """Redirect anonymous visitors to the login page."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get('username'):
            flash('请先登录。', 'danger')
            return redirect(url_for('auth.login'))
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    """Allow administrators only."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get('username'):
            flash('请先登录。', 'danger')
            return redirect(url_for('auth.login'))
        if not session.get('is_admin'):
            flash('您需要管理员权限。', 'danger')
            return redirect(url_for('chat.chat'))
        return view(*args, **kwargs)

    return wrapped


# --------------------------------------------------------------------------- #
# Rate limiting
# --------------------------------------------------------------------------- #
class SlidingWindowLimiter:
    """Thread-safe, in-process sliding window limiter.

    Deliberately dependency free.  State lives in the worker process, so a
    multi-worker deployment should move this to Redis (or front the app with a
    reverse proxy limiter).
    """

    def __init__(self, limit, window_seconds, max_keys=4096):
        self.limit = max(1, int(limit))
        # A small positive floor so that a window can never mean "never expires".
        self.window = max(0.001, float(window_seconds))
        self.max_keys = max_keys
        self._lock = threading.Lock()
        self._hits = {}

    def check(self, key):
        """Record a hit.  Returns ``(allowed, retry_after_seconds)``."""
        now = time.monotonic()
        with self._lock:
            hits = [stamp for stamp in self._hits.get(key, ()) if now - stamp < self.window]
            if len(hits) >= self.limit:
                self._hits[key] = hits
                return False, self.window - (now - hits[0])
            hits.append(now)
            self._hits[key] = hits
            if len(self._hits) > self.max_keys:
                self._prune(now)
            return True, 0.0

    def reset(self, key):
        """Forget the history of ``key`` (used after a successful login)."""
        with self._lock:
            self._hits.pop(key, None)

    def _prune(self, now):
        """Drop keys whose window has fully expired.  Caller holds the lock."""
        for key in [k for k, hits in self._hits.items() if not hits or now - hits[-1] >= self.window]:
            self._hits.pop(key, None)


_LOGIN_LIMITER_KEY = 'speak_login_limiter'


def login_limiter():
    """Return the application-wide limiter for login/registration attempts."""
    limiter = current_app.extensions.get(_LOGIN_LIMITER_KEY)
    if limiter is None:
        config = current_app.config
        limiter = SlidingWindowLimiter(
            config['LOGIN_MAX_ATTEMPTS'], config['LOGIN_WINDOW_SECONDS']
        )
        current_app.extensions[_LOGIN_LIMITER_KEY] = limiter
    return limiter


def client_key(username=''):
    """Rate limit key: remote address plus the attempted user name."""
    return '%s|%s' % (request.remote_addr or '-', (username or '').lower())


# --------------------------------------------------------------------------- #
# Response hardening
# --------------------------------------------------------------------------- #
def apply_security_headers(response):
    """Attach the standard hardening headers to every response."""
    if not current_app.config['SECURITY_HEADERS']:
        return response
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'DENY')
    response.headers.setdefault('Referrer-Policy', 'same-origin')
    response.headers.setdefault('Cross-Origin-Opener-Policy', 'same-origin')
    policy = current_app.config['CONTENT_SECURITY_POLICY']
    if policy:
        response.headers.setdefault('Content-Security-Policy', policy)
    return response


def init_app(app):
    """Register every hook defined in this module with ``app``."""
    app.before_request(protect_from_csrf)
    app.after_request(apply_security_headers)
    app.jinja_env.globals['csrf_token'] = generate_csrf_token
