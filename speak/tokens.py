"""密码重置令牌。

用 ``itsdangerous``（Flask 自带依赖）生成带签名与有效期的令牌，
**不需要额外的数据库表**。

载荷里除了用户 id，还带一个「当前密码哈希的指纹」：

* 密码一旦被修改，指纹变化，**旧链接立刻失效**（天然的一次性效果）；
* 令牌本身有过期时间，过期后 ``itsdangerous`` 会直接拒绝。

令牌是签名的，无法伪造成别的用户。

用法上分成两步，因为校验指纹必须先查到用户：

    payload = tokens.load(token)           # 校验签名 + 有效期
    row = 用 payload 里的 uid 查用户
    if not tokens.matches(payload, row['password']):  # 再校验指纹
        ...
"""

import hashlib
import logging

from flask import current_app
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

log = logging.getLogger(__name__)

#: 与其它签名用途隔离，避免令牌被拿到别处复用。
_SALT = 'speak-password-reset'

DEFAULT_TTL_MINUTES = 30


def _serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'], salt=_SALT)


def _fingerprint(password_hash):
    """取密码哈希的短指纹。改密后指纹必然变化。"""
    return hashlib.sha256((password_hash or '').encode('utf-8')).hexdigest()[:16]


def ttl_seconds():
    """令牌有效期（秒），来自可在线修改的设置。"""
    from .settings import get
    try:
        minutes = int(get('reset_token_minutes') or DEFAULT_TTL_MINUTES)
    except (TypeError, ValueError):
        minutes = DEFAULT_TTL_MINUTES
    return max(1, minutes) * 60


def ttl_minutes():
    return ttl_seconds() // 60


def generate(user_id, password_hash):
    """Build a reset token for one user."""
    return _serializer().dumps({
        'uid': int(user_id),
        'fp': _fingerprint(password_hash),
    })


def load(token, max_age=None):
    """校验签名与有效期，返回载荷字典；任何问题都返回 ``None``。"""
    if not token:
        return None
    if max_age is None:
        max_age = ttl_seconds()

    try:
        payload = _serializer().loads(token, max_age=max_age)
    except SignatureExpired:
        log.info('密码重置令牌已过期')
        return None
    except BadSignature:
        log.info('密码重置令牌签名无效')
        return None

    if not isinstance(payload, dict) or 'uid' not in payload:
        return None
    return payload


def user_id(payload):
    """取出载荷里的用户 id，非法时返回 ``None``。"""
    try:
        return int(payload['uid'])
    except (KeyError, TypeError, ValueError):
        return None


def matches(payload, password_hash):
    """指纹是否与当前密码一致（改密后即失效）。"""
    return payload.get('fp') == _fingerprint(password_hash)


def verify(token, password_hash, max_age=None):
    """一步完成校验，返回用户 id 或 ``None``（方便测试与复用）。"""
    payload = load(token, max_age=max_age)
    if payload is None or not matches(payload, password_hash):
        return None
    return user_id(payload)
