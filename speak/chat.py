"""Public and chat views."""

from flask import Blueprint, current_app, render_template, session

from .security import login_required

bp = Blueprint('chat', __name__)


@bp.route('/')
def index():
    return render_template('index.html')


@bp.route('/chat')
@login_required
def chat():
    config = current_app.config
    # The browser client needs a *leading* slash: socket.io-client does not
    # normalise the ``path`` option, and a value like "socket.io" makes it build
    # the malformed URL "http://host:portsocket.io/...", which fails instantly
    # with "xhr poll error" and never even reaches the server.
    socketio_path = '/' + (config['SOCKETIO_PATH'].strip('/') or 'socket.io')
    return render_template(
        'chat.html',
        username=session['username'],
        room=config['CHAT_ROOM'],
        max_message_length=config['CHAT_MAX_MESSAGE_LENGTH'],
        socketio_path=socketio_path,
    )
