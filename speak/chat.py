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
    return render_template(
        'chat.html',
        username=session['username'],
        room=config['CHAT_ROOM'],
        max_message_length=config['CHAT_MAX_MESSAGE_LENGTH'],
        socketio_path=config['SOCKETIO_PATH'].strip('/') or 'socket.io',
    )
