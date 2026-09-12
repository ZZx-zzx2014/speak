"""Socket.IO event handlers and per-application chat state.

Handlers are registered by :func:`register`, which **must** run before the first
``socketio.init_app`` call: Flask-SocketIO builds a brand new server on every
``init_app`` and only replays the handlers it collected up to that point.  The
original project avoided the issue by using a module level ``SocketIO(app)``;
the application factory has to be explicit about the ordering.
"""

import logging
import threading
import time
from collections import deque

from flask import current_app, request, session
from flask_socketio import emit, join_room

from .security import SlidingWindowLimiter
from .validators import ValidationError, sanitise_message

log = logging.getLogger(__name__)

_REGISTRY_KEY = 'speak_chat_state'
_registered = False


class ChatState:
    """In-process chat state: bounded history, presence and rate limiting.

    This lives in the worker process.  Run a single worker, or move the state to
    Redis / a message queue, before scaling out horizontally.
    """

    def __init__(self, config):
        self.room = config['CHAT_ROOM']
        self.history_size = max(0, int(config['CHAT_HISTORY_SIZE']))
        self.lock = threading.RLock()
        # maxlen is always > 0 so that deque accepts the size.
        self.history = deque(maxlen=self.history_size or 1)
        self.presence = {}
        self.limiter = SlidingWindowLimiter(
            config['CHAT_MESSAGES_PER_WINDOW'],
            config['CHAT_RATE_WINDOW_SECONDS'],
        )

    def remember(self, message):
        with self.lock:
            self.history.append(message)
        return message

    def snapshot(self):
        with self.lock:
            return list(self.history)

    def add_presence(self, sid, username):
        with self.lock:
            self.presence[sid] = username
            return len(self.presence)

    def drop_presence(self, sid):
        with self.lock:
            return self.presence.pop(sid, None)

    def online_count(self):
        with self.lock:
            return len(self.presence)


def chat_state():
    """Return the :class:`ChatState` bound to the current application."""
    state = current_app.extensions.get(_REGISTRY_KEY)
    if state is None:  # pragma: no cover - normally created by ``init_app``
        state = ChatState(current_app.config)
        current_app.extensions[_REGISTRY_KEY] = state
    return state


def init_app(app):
    """Create the per-application chat state."""
    app.extensions[_REGISTRY_KEY] = ChatState(app.config)


def _timestamp():
    """Unix time in seconds; the browser formats it with ``toLocaleTimeString``."""
    return time.time()


def _announce(state, text):
    emit('system_message', {'msg': text, 'ts': _timestamp()}, room=state.room)


def _emit_presence(state, count=None):
    emit(
        'presence',
        {'count': state.online_count() if count is None else count},
        room=state.room,
    )


def register(server):
    """Attach every handler to ``server``; safe to call repeatedly."""
    global _registered
    if _registered:
        return
    _registered = True

    @server.on('connect')
    def handle_connect():
        """Reject anonymous connections: the chat is for logged-in users only."""
        username = session.get('username')
        if not username:
            # Log the session keys (not values) so a rejected connection is
            # diagnosable: an empty list usually means the cookie was missing,
            # expired, or signed with a different SECRET_KEY.
            log.warning('拒绝未登录的 Socket.IO 连接 (sid=%s, addr=%s, 会话字段=%s)',
                        request.sid, request.remote_addr, sorted(session.keys()))
            return False
        return True

    @server.on('join')
    def handle_join(_data=None):
        username = session.get('username')
        if not username:  # defence in depth; ``connect`` already refuses
            return False

        state = chat_state()
        join_room(state.room)
        count = state.add_presence(request.sid, username)

        # Replay the recent backlog to the newcomer only.
        emit('history', {'messages': state.snapshot()}, to=request.sid)
        _announce(state, '%s 加入了聊天室' % username)
        _emit_presence(state, count)
        return None

    @server.on('chat_message')
    def handle_chat_message(data):
        username = session.get('username')
        if not username:
            return None

        state = chat_state()
        payload = data if isinstance(data, dict) else {}

        try:
            text = sanitise_message(payload.get('msg'), current_app.config)
        except ValidationError as exc:
            emit('system_message', {'msg': str(exc), 'ts': _timestamp()}, to=request.sid)
            return None

        allowed, retry_after = state.limiter.check(username)
        if not allowed:
            emit(
                'system_message',
                {'msg': '发送过于频繁，请在 %.0f 秒后重试。' % (retry_after + 0.5),
                 'ts': _timestamp()},
                to=request.sid,
            )
            return None

        message = {'username': username, 'msg': text, 'ts': _timestamp()}
        state.remember(message)
        emit('chat_message', message, room=state.room)
        return None

    @server.on('disconnect')
    def handle_disconnect():
        """Presence cleanup.

        This replaces the original ``beforeunload`` client hook, which browsers
        do not deliver reliably (and which never fires on a dropped connection).
        """
        state = chat_state()
        username = state.drop_presence(request.sid)
        if username:
            _announce(state, '%s 离开了聊天室' % username)
            _emit_presence(state)
        return None


__all__ = ['ChatState', 'chat_state', 'init_app', 'register']
