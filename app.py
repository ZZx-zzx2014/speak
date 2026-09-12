#!/usr/bin/env python3
"""Development entry point.

Starts the same way as before::

    python app.py

For a production deployment use a real WSGI server instead — see ``README.md``.
"""

import logging
import os
import sys


def apply_async_mode_patch():
    """Monkey patch ``gevent``/``eventlet`` before anything else is imported.

    This has to happen before ``speak`` (and therefore Flask, engineio and the
    standard library socket/thread modules) is imported, otherwise the async
    backend cannot work correctly.  Falls back to ``threading`` when the
    requested backend is not installed.
    """
    mode = os.environ.get('SPEAK_SOCKETIO_ASYNC_MODE', 'threading').strip().lower()
    if mode not in ('gevent', 'eventlet'):
        return mode

    try:
        if mode == 'gevent':
            from gevent import monkey
        else:
            from eventlet import monkey
        monkey.patch_all()
    except ImportError:
        print('提示：未安装 %s，回退到 threading 模式（仅支持长轮询）。' % mode,
              file=sys.stderr)
        os.environ['SPEAK_SOCKETIO_ASYNC_MODE'] = 'threading'
        return 'threading'
    return mode


def run_server(socketio, app):
    """Start the built-in development server.

    Flask-SocketIO >= 5.3 refuses to run the Werkzeug development server unless
    ``allow_unsafe_werkzeug=True`` is passed, while older releases raise
    ``TypeError`` for that keyword.  Instead of guessing from a version string,
    the plain call is attempted first and the opt-in is only supplied when the
    library explicitly asks for it — this works on every release in between.
    """
    host = app.config['HOST']
    port = app.config['PORT']
    options = {'debug': app.config['DEBUG'], 'use_reloader': app.config['DEBUG']}

    try:
        socketio.run(app, host=host, port=port, **options)
    except RuntimeError as exc:
        if 'allow_unsafe_werkzeug' not in str(exc):
            raise
        app.logger.warning(
            '当前 Flask-SocketIO 要求显式确认才允许使用内置开发服务器。'
            '生产环境请改用 gunicorn 等 WSGI 服务器（见 README）。'
        )
        socketio.run(app, host=host, port=port,
                     allow_unsafe_werkzeug=True, **options)


def main():
    apply_async_mode_patch()

    from speak import __version__, create_app, socketio

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)-7s %(name)s: %(message)s',
    )

    app = create_app()
    host = app.config['HOST']
    port = app.config['PORT']

    app.logger.info('Speak %s 已启动: http://%s:%s (async_mode=%s)',
                    __version__, host, port, app.config['SOCKETIO_ASYNC_MODE'])
    if host not in ('127.0.0.1', 'localhost'):
        app.logger.warning('服务绑定在 %s，同一网络中的其他主机可访问；'
                           '请仅在受信任的环境中使用内置开发服务器。', host)

    run_server(socketio, app)


if __name__ == '__main__':
    main()
