"""Authentication views: registration, login, logout and password reset.

邮箱是**可选但推荐**的账号属性（由 ``EMAIL_REQUIRED`` 决定注册时是否必填）：

* 注册时可以填邮箱；
* 登录时可以用**用户名或邮箱**；
* 忘记密码时用邮箱收重置链接。
"""

import logging
import sqlite3

from flask import (
    Blueprint, current_app, flash, redirect, render_template, request, session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from . import mail, tokens
from .db import PASSWORD_HASH_METHOD, get_db
from .security import client_key, login_limiter
from .turnstile import RESPONSE_FIELD, verify as verify_turnstile
from .validators import (
    ValidationError, safe_redirect_target, validate_email, validate_password,
    validate_username,
)

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

    Reads the runtime editable settings, so the keys entered in the admin UI
    take effect immediately.  Always returns ``True`` when Turnstile is not
    configured, so the forms keep working out of the box.
    """
    return verify_turnstile(request.form.get(RESPONSE_FIELD, ''), request.remote_addr)


@bp.route('/register', methods=['GET', 'POST'])
def register():
    if session.get('username'):
        return redirect(url_for('chat.chat'))

    if request.method != 'POST':
        return render_template('register.html')

    form_username = request.form.get('username', '')
    form_email = request.form.get('email', '')

    allowed, retry_after = login_limiter().check('register|' + client_key(form_username))
    if not allowed:
        flash('注册尝试过于频繁，请在 %.0f 秒后重试。' % (retry_after + 0.5), 'danger')
        return render_template('register.html', username=form_username,
                               email=form_email), 429

    if not _human_verification_passed():
        flash('人机验证未通过，请重试。', 'danger')
        return render_template('register.html', username=form_username,
                               email=form_email), 400

    try:
        username = validate_username(form_username, current_app.config)
        email = validate_email(form_email, current_app.config)
        password = validate_password(
            request.form.get('password'),
            request.form.get('password2'),
            current_app.config,
        )
    except ValidationError as exc:
        flash(str(exc), 'danger')
        return render_template('register.html', username=form_username,
                               email=form_email), 400

    hashed = generate_password_hash(password, method=PASSWORD_HASH_METHOD)
    try:
        # The UNIQUE constraints are the authoritative check: a pre-flight SELECT
        # would still race with a concurrent registration.
        get_db().execute(
            'INSERT INTO users (username, password, is_admin, email) '
            'VALUES (?, ?, 0, ?)',
            (username, hashed, email),
        )
    except sqlite3.IntegrityError as exc:
        # 注册场景必须明确告诉用户是哪一项冲突，否则无法修正。
        if 'email' in str(exc).lower():
            flash('该邮箱已被注册，可以直接登录，或用「忘记密码」重置。', 'danger')
        else:
            flash('用户名已存在，请选择其他用户名。', 'danger')
        return render_template('register.html', username=username,
                               email=form_email), 409

    log.info('新用户注册: %s (email=%s)', username, email or '未填')
    flash('注册成功！现在可以登录。', 'success')
    return redirect(url_for('auth.login'))


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('username'):
        return redirect(url_for('chat.chat'))

    if request.method != 'POST':
        return render_template('login.html')

    # 这一栏既接受用户名，也接受邮箱
    identifier = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    limiter = login_limiter()
    key = client_key(identifier)

    allowed, retry_after = limiter.check(key)
    if not allowed:
        flash('登录尝试过于频繁，请在 %.0f 秒后重试。' % (retry_after + 0.5), 'danger')
        return render_template('login.html', username=identifier), 429

    if not _human_verification_passed():
        flash('人机验证未通过，请重试。', 'danger')
        return render_template('login.html', username=identifier), 400

    row = get_db().execute(
        'SELECT id, username, password, is_admin FROM users '
        'WHERE username = ? OR email = ?',
        (identifier, identifier.lower()),
    ).fetchone()

    if row is None:
        check_password_hash(_timing_equaliser_hash(), password)
        authenticated = False
    else:
        authenticated = check_password_hash(row['password'], password)

    if not authenticated:
        log.info('登录失败: %s (%s)', identifier or '<空>', request.remote_addr)
        flash('用户名、邮箱或密码无效，请重试。', 'danger')
        return render_template('login.html', username=identifier), 401

    limiter.reset(key)
    # Re-issue the session so that a token captured before login is useless
    # afterwards (session fixation).
    session.clear()
    session['username'] = row['username']
    session['is_admin'] = bool(row['is_admin'])
    session.permanent = True
    if session['is_admin']:
        # Nudge the administrator into the settings screen once, right after login.
        session['show_admin_setup'] = True
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


# --------------------------------------------------------------------------- #
# 密码重置
# --------------------------------------------------------------------------- #
@bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """发送重置邮件。

    注意：**无论邮箱是否存在，都给出完全相同的提示**，
    否则这个接口会变成"某个邮箱是否注册过"的查询接口。
    """
    if request.method != 'POST':
        return render_template('forgot_password.html')

    email = (request.form.get('email') or '').strip().lower()

    allowed, retry_after = login_limiter().check('forgot|' + client_key(email))
    if not allowed:
        flash('请求过于频繁，请在 %.0f 秒后重试。' % (retry_after + 0.5), 'danger')
        return render_template('forgot_password.html', email=email), 429

    if not _human_verification_passed():
        flash('人机验证未通过，请重试。', 'danger')
        return render_template('forgot_password.html', email=email), 400

    row = None
    if email:
        row = get_db().execute(
            'SELECT id, username, password FROM users WHERE email = ?', (email,)
        ).fetchone()

    if row is not None:
        token = tokens.generate(row['id'], row['password'])
        reset_url = url_for('auth.reset_password', token=token, _external=True)
        ok, message = mail.send_password_reset(
            email, row['username'], reset_url, tokens.ttl_minutes()
        )
        if ok:
            log.info('已为 %s 发送密码重置邮件', row['username'])
        else:
            # 只记日志，不告诉请求方（否则又变成账户枚举）
            log.warning('密码重置邮件发送失败: %s', message)

    flash('如果该邮箱对应的账号存在，我们已发送重置邮件。'
          '请查收收件箱与垃圾箱。', 'success')
    return redirect(url_for('auth.login'))


def _load_reset_user(token):
    """校验令牌并取出对应用户；任何一步失败都返回 ``None``。"""
    payload = tokens.load(token)
    if payload is None:
        return None

    uid = tokens.user_id(payload)
    if uid is None:
        return None

    row = get_db().execute(
        'SELECT id, username, password FROM users WHERE id = ?', (uid,)
    ).fetchone()

    if row is None or not tokens.matches(payload, row['password']):
        # 用户不存在，或密码已经改过（链接作废）
        return None
    return row


@bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    row = _load_reset_user(token)
    if row is None:
        flash('重置链接无效或已过期，请重新申请。', 'danger')
        return redirect(url_for('auth.forgot_password'))

    if request.method != 'POST':
        return render_template('reset_password.html', token=token,
                               username=row['username'])

    try:
        password = validate_password(
            request.form.get('password'),
            request.form.get('password2'),
            current_app.config,
        )
    except ValidationError as exc:
        flash(str(exc), 'danger')
        return render_template('reset_password.html', token=token,
                               username=row['username']), 400

    get_db().execute(
        'UPDATE users SET password = ? WHERE id = ?',
        (generate_password_hash(password, method=PASSWORD_HASH_METHOD), row['id']),
    )
    # 改密后指纹变化，这个链接自然失效（无法重复使用）
    log.info('用户 %s 通过邮件链接重置了密码', row['username'])
    flash('密码已重置，请用新密码登录。', 'success')
    return redirect(url_for('auth.login'))
