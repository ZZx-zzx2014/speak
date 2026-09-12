"""Administrator views: user listing and deletion."""

import logging

from flask import Blueprint, flash, redirect, render_template, session, url_for

from .db import get_db
from .security import admin_required

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
