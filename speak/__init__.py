"""Speak — a small Flask + Socket.IO chat application.

The application is built by :func:`create_app` rather than at import time, so
that tests and multiple deployments can hold independent instances with
independent configuration.
"""

import logging
import os
import secrets
from pathlib import Path

from flask import Flask, render_template
from flask_socketio import SocketIO

from .config import Config
from .socketio_client import cdn_urls

__all__ = ['__version__', 'create_app', 'socketio']

#: Single source of truth for the release number (kept in sync with
#: ``pyproject.toml``; see ``CHANGELOG.md``).
__version__ = '1.0.0'

log = logging.getLogger(__name__)

#: The single Socket.IO extension object; bound to an app by :func:`create_app`.
socketio = SocketIO()


def _normalised_socketio_path(raw_path):
    """Flask-SocketIO wants the endpoint without a leading slash."""
    return (raw_path or 'socket.io').strip('/') or 'socket.io'


def _load_or_create_secret_key(path):
    """Return the persisted signing key, generating it on first use."""
    key_file = Path(path)
    try:
        if key_file.exists():
            stored = key_file.read_text(encoding='utf-8').strip()
            if stored:
                return stored

        key = secrets.token_hex(32)
        key_file.parent.mkdir(parents=True, exist_ok=True)
        key_file.write_text(key, encoding='utf-8')
        try:
            os.chmod(str(key_file), 0o600)
        except OSError:  # pragma: no cover - not meaningful on Windows
            pass
        log.warning(
            '未设置 SPEAK_SECRET_KEY，已生成随机密钥并保存到 %s。'
            '多实例部署请改用环境变量共享同一密钥。', key_file,
        )
        return key
    except OSError as exc:
        raise RuntimeError(
            '未设置 SPEAK_SECRET_KEY，且无法读写 %s (%s)。'
            '请通过环境变量提供密钥，例如：'
            'python -c "import secrets; print(secrets.token_hex(32))"' % (key_file, exc)
        ) from exc


def _resolve_secret_key(app):
    """Guarantee a signing key without ever shipping a hard-coded one."""
    if app.config.get('SECRET_KEY'):
        return
    if app.config['DEBUG'] or app.config['TESTING']:
        # Ephemeral: fine for development, invalidates sessions on restart.
        app.config['SECRET_KEY'] = secrets.token_hex(32)
        log.warning('调试模式下未设置 SPEAK_SECRET_KEY，已生成临时密钥。')
        return
    app.config['SECRET_KEY'] = _load_or_create_secret_key(app.config['SECRET_KEY_FILE'])


def _register_error_handlers(app):
    @app.errorhandler(400)
    def _bad_request(error):
        return render_template(
            'error.html',
            status=400,
            message=getattr(error, 'description', '请求无效。'),
        ), 400

    @app.errorhandler(404)
    def _not_found(_error):
        return render_template('error.html', status=404, message='页面不存在。'), 404

    @app.errorhandler(500)
    def _server_error(error):  # pragma: no cover - defensive branch
        app.logger.exception('未处理的服务端异常', exc_info=error)
        try:
            return render_template(
                'error.html', status=500, message='服务器内部错误。'
            ), 500
        except Exception:
            return 'Internal Server Error', 500


def create_app(config_object=Config, **overrides):
    """Build, configure and return a Flask application instance.

    :param config_object: configuration class or object to load first.
    :param overrides: individual settings applied on top (used by the tests).
    """
    app = Flask(__name__)
    app.config.from_object(config_object)
    app.config.update(overrides)

    _resolve_secret_key(app)
    app.logger.setLevel(logging.DEBUG if app.config['DEBUG'] else logging.INFO)

    # Import the event handlers and register them *before* ``init_app``:
    # Flask-SocketIO creates a fresh server on every ``init_app`` and only
    # replays the handlers gathered up to that moment.
    from . import events

    events.register(socketio)
    socketio.init_app(
        app,
        async_mode=app.config['SOCKETIO_ASYNC_MODE'],
        path=_normalised_socketio_path(app.config['SOCKETIO_PATH']),
        cors_allowed_origins=app.config['SOCKETIO_CORS_ALLOWED_ORIGINS'],
        logger=app.config['SOCKETIO_LOGGER'],
        engineio_logger=app.config['SOCKETIO_ENGINEIO_LOGGER'],
    )

    from . import admin, auth, chat, db, security, turnstile

    db.init_app(app)
    security.init_app(app)
    events.init_app(app)

    app.register_blueprint(chat.bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(admin.bp)

    app.jinja_env.globals['socketio_client_urls'] = lambda: cdn_urls(app.config)
    # Empty string when Turnstile is not configured, so templates can simply
    # test ``{% if turnstile_site_key %}``.
    app.jinja_env.globals['turnstile_site_key'] = (
        app.config['TURNSTILE_SITE_KEY'] if turnstile.is_enabled(app.config) else ''
    )

    _register_error_handlers(app)

    with app.app_context():
        db.init_db()
        db.seed_admin()

    log.debug('Speak 应用初始化完成 (debug=%s, database=%s)',
              app.config['DEBUG'], app.config['DATABASE'])
    return app
