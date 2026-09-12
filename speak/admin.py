"""Administrator views: user management and the runtime settings screen."""

import logging

from flask import (
    Blueprint, current_app, flash, redirect, render_template, request, session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from .db import PASSWORD_HASH_METHOD, get_db
from .security import admin_required
from .settings import all_sources, all_values, save as save_settings
from .turnstile import TEST_KEYS, verify_secret_key
from .validators import ValidationError, validate_password

log = logging.getLogger(__name__)

bp = Blueprint('admin', __name__)


@bp.route('/manage')
@admin_required
def manage():
    users = get_db().execute(
        'SELECT id, username, created_at FROM users '
        'WHERE is_admin = 0 ORDER BY id'
    ).fetchall()
    return render_template('manage.html', users=users)


@bp.route('/manage/users/<int:user_id>/delete', methods=['POST'])
@admin_required
def delete_user(user_id):
    """Delete a regular user.

    The original implementation ran ``DELETE FROM users WHERE id = ?`` straight
    from the request, so a crafted POST could remove an administrator account
    (and, without CSRF protection, a third-party page could trigger it).  The
    target is now looked up and validated first.
    """
    db = get_db()
    row = db.execute(
        'SELECT id, username, is_admin FROM users WHERE id = ?', (user_id,)
    ).fetchone()

    if row is None:
        flash('该用户不存在或已被删除。', 'danger')
    elif row['is_admin']:
        flash('不能通过此页面删除管理员账户。', 'danger')
    elif row['username'] == session.get('username'):
        flash('不能删除当前登录的账户。', 'danger')
    else:
        db.execute('DELETE FROM users WHERE id = ?', (user_id,))
        log.info('管理员 %s 删除了用户 %s', session.get('username'), row['username'])
        flash('用户 %s 已删除。' % row['username'], 'success')

    return redirect(url_for('admin.manage'))


# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #
@bp.route('/admin/settings')
@admin_required
def settings_page():
    """The administrator settings screen."""
    return render_template(
        'admin_settings.html',
        values=all_values(),
        sources=all_sources(),
        test_keys=TEST_KEYS,
    )


@bp.route('/admin/settings/site', methods=['POST'])
@admin_required
def save_site_settings():
    """Save the site name and announcement."""
    site_name = (request.form.get('site_name') or '').strip()
    if not site_name:
        flash('站点名称不能为空。', 'danger')
        return redirect(url_for('admin.settings_page'))
    if len(site_name) > 60:
        flash('站点名称过长，请控制在 60 个字符以内。', 'danger')
        return redirect(url_for('admin.settings_page'))

    announcement = (request.form.get('site_announcement') or '').strip()
    if len(announcement) > 500:
        flash('公告过长，请控制在 500 个字符以内。', 'danger')
        return redirect(url_for('admin.settings_page'))

    save_settings({'site_name': site_name, 'site_announcement': announcement})
    log.info('管理员 %s 更新了站点信息', session.get('username'))
    flash('基础信息已保存。', 'success')
    return redirect(url_for('admin.settings_page'))


@bp.route('/admin/settings/turnstile', methods=['POST'])
@admin_required
def save_turnstile_settings():
    """Save, pre-fill or validate the Cloudflare Turnstile keys."""
    action = request.form.get('action', 'save')

    if action == 'use_test_keys':
        save_settings({
            'turnstile_site_key': TEST_KEYS['site_key_always_passes'],
            'turnstile_secret_key': TEST_KEYS['secret_key_always_passes'],
        })
        flash('已填入 Cloudflare 官方测试密钥：验证码会永远通过，'
              '仅用于确认流程是否打通。上线前请换成正式密钥。', 'success')
        return redirect(url_for('admin.settings_page'))

    site_key = (request.form.get('turnstile_site_key') or '').strip()
    secret_key = (request.form.get('turnstile_secret_key') or '').strip()

    if action == 'verify':
        # Keep whatever was typed so the operator does not lose it.
        save_settings({'turnstile_site_key': site_key, 'turnstile_secret_key': secret_key})
        ok, message = verify_secret_key(
            secret_key, timeout=current_app.config['TURNSTILE_TIMEOUT_SECONDS']
        )
        flash(message, 'success' if ok else 'danger')
        return redirect(url_for('admin.settings_page'))

    if bool(site_key) != bool(secret_key):
        flash('Site Key 与 Secret Key 必须成对填写，否则人机验证不会生效。', 'danger')
        return redirect(url_for('admin.settings_page'))

    save_settings({'turnstile_site_key': site_key, 'turnstile_secret_key': secret_key})
    log.info('管理员 %s 更新了 Cloudflare Turnstile 配置', session.get('username'))

    if site_key and secret_key:
        flash('Cloudflare 配置已保存，人机验证已开启。', 'success')
    else:
        flash('Cloudflare 配置已清空，人机验证已关闭。', 'success')
    return redirect(url_for('admin.settings_page'))


@bp.route('/admin/settings/password', methods=['POST'])
@admin_required
def change_password():
    """Change the signed-in administrator's own password."""
    current_password = request.form.get('current_password') or ''
    username = session.get('username')

    db = get_db()
    row = db.execute(
        'SELECT id, password FROM users WHERE username = ?', (username,)
    ).fetchone()

    if row is None or not check_password_hash(row['password'], current_password):
        log.info('管理员 %s 修改密码时当前密码校验失败', username)
        flash('当前密码不正确。', 'danger')
        return redirect(url_for('admin.settings_page'))

    try:
        new_password = validate_password(
            request.form.get('new_password'),
            request.form.get('new_password2'),
            current_app.config,
        )
    except ValidationError as exc:
        flash(str(exc), 'danger')
        return redirect(url_for('admin.settings_page'))

    if check_password_hash(row['password'], new_password):
        flash('新密码不能与当前密码相同。', 'danger')
        return redirect(url_for('admin.settings_page'))

    db.execute(
        'UPDATE users SET password = ? WHERE id = ?',
        (generate_password_hash(new_password, method=PASSWORD_HASH_METHOD), row['id']),
    )
    log.info('管理员 %s 修改了自己的密码', username)
    flash('管理密码已更新，请牢记新密码。', 'success')
    return redirect(url_for('admin.settings_page'))
