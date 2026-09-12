"""WSGI entry point for production servers.

Examples::

    # Long-polling, several workers (each worker keeps its own chat history).
    gunicorn -w 4 "wsgi:app"

    # WebSocket support: gunicorn's gevent worker monkey patches itself.
    gunicorn -k gevent -w 1 "wsgi:app"

Chat history and presence live in the worker process, so use a single worker
until the state is moved to Redis / a message queue.
"""

from speak import create_app

app = create_app()
