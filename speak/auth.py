"""Authentication views: registration, login and logout."""

import logging
import sqlite3

from flask import (
    Blueprint, current_app, flash, redirect, render_template, request, session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from .db import PASSWORD_HASH_METHOD, get_db
from .security import client_key, login_limiter
from .turnstile import RESPONSE_FIELD, verify as verify_turnstile
from .validators import ValidationError, safe_redirect_target, validate_password, validate_username

log = logging.getLogger(__name__)

bp = Blueprint('auth', __name__)

_dummy_hash = None


def _timing_equaliser_hash():
    """A throwaway hash used to keep the login response time roughly constant.

    Without it, a missing user name answers measurably faster than a wrong
    password, which leaks which accounts exist.
    """
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = generate_password_hash('speak-timing-equaliser',
                                             method=PASSWORD_HASH_METHOD)
    return _dummy_hash


def _human_verification_passed():
    """Run the Cloudflare Turnstile challenge for the current request.

    Always returns ``True`` when Turnstile is not configured, so the forms keep
    working out of the box.
    """
    return verify_turnstile(
        request.form.get(RESPONSE_FIELD, ''),
        request.remote_addr,
        current_app.config,
    )


@bp.route('/register', methods=['GET', 'POST'])
def register():
    if session.get('username'):
        return redirect(url_for('chat.chat'))

    if request.method != 'POST':
        return render_template('register.html')

    form_username = request.form.get('username', '')

    allowed, retry_after = login_limiter().check('register|' + client_key(form_username))
    if not allowed:
        flash('注册尝试过于频繁，请在 %.0f 秒后重试。' % (retry_after + 0.5), 'danger')
        return render_template('register.html', username=form_username), 429

    if not _human_verification_passed():
        flash('人机验证未通过，请重试。', 'danger')
        return render_template('register.html', username=form_username), 400

    try:
        username = validate_username(form_username, current_app.config)
        password = validate_password(
            request.form.get('password'),
            request.form.get('password2'),
            current_app.config,
        )
    except ValidationError as exc:
        flash(str(exc), 'danger')
        return render_template('register.html', username=form_username), 400

    hashed = generate_password_hash(password, method=PASSWORD_HASH_METHOD)
    try:
        db = get_db()
        db.execute(
            'INSERT INTO users (username, password, is_admin) VALUES (?, ?, 0)',
            (username, hashed),
        )
    except sqlite3.IntegrityError:
        # The UNIQUE constraint is the authoritative check: a pre-flight SELECT
        # would still race with a concurrent registration.
        flash('用户名已存在，请选择其他用户名。', 'danger')
        return render_template('register.html', username=username), 409

    log.info('新用户注册: %s', username)
    flash('注册成功！现在可以登录。', 'success')
    return redirect(url_for('auth.login'))


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('username'):
        return redirect(url_for('chat.chat'))

    if request.method != 'POST':
        return render_template('login.html')

    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    limiter = login_limiter()
    key = client_key(username)

    allowed, retry_after = limiter.check(key)
    if not allowed:
        flash('登录尝试过于频繁，请在 %.0f 秒后重试。' % (retry_after + 0.5), 'danger')
        return render_template('login.html', username=username), 429

    if not _human_verification_passed():
        flash('人机验证未通过，请重试。', 'danger')
        return render_template('login.html', username=username), 400

    row = get_db().execute(
        'SELECT id, username, password, is_admin FROM users WHERE username = ?',
        (username,),
    ).fetchone()

    if row is None:
        check_password_hash(_timing_equaliser_hash(), password)
        authenticated = False
    else:
        authenticated = check_password_hash(row['password'], password)

    if not authenticated:
        log.info('登录失败: %s (%s)', username or '<空>', request.remote_addr)
        flash('用户名或密码无效，请重试。', 'danger')
        return render_template('login.html', username=username), 401

    limiter.reset(key)
    # Re-issue the session so that a token captured before login is useless
    # afterwards (session fixation).
    session.clear()
    session['username'] = row['username']
    session['is_admin'] = bool(row['is_admin'])
    session.permanent = True
    log.info('登录成功: %s', row['username'])

    flash('登录成功！', 'success')
    return redirect(
        safe_redirect_target(request.args.get('next')) or url_for('chat.chat')
    )


@bp.route('/logout', methods=['POST'])
def logout():
    username = session.get('username')
    session.clear()
    if username:
        log.info('用户退出登录: %s', username)
    flash('您已退出登录。', 'success')
    return redirect(url_for('chat.index'))
