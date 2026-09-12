"""Cloudflare Turnstile verification (bot protection).

Turnstile is optional and stays completely disabled until a site key **and** a
secret key are configured, so local development needs no Cloudflare account.

Values are read from :mod:`speak.settings`, which means the administrator can
enter them in the web UI at ``/admin/settings`` instead of editing environment
variables.  Passing an explicit ``config`` mapping (as the tests do) bypasses the
database entirely.

Only the standard library is used, which keeps the dependency list unchanged.
"""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request

log = logging.getLogger(__name__)

#: Name of the hidden field Cloudflare's widget injects into the form.
RESPONSE_FIELD = 'cf-turnstile-response'

SITEVERIFY_URL = 'https://challenges.cloudflare.com/turnstile/v0/siteverify'

#: Cloudflare's published dummy keys, handy for trying the integration without
#: creating a site (documented under "Testing" in the Turnstile docs).
TEST_KEYS = {
    'site_key_always_passes': '1x00000000000000000000AA',
    'site_key_always_blocks': '2x00000000000000000000AB',
    'secret_key_always_passes': '1x0000000000000000000000000000000AA',
    'secret_key_always_fails': '2x0000000000000000000000000000000AA',
}

#: A syntactically valid but meaningless token, used to probe a secret key.
_DUMMY_TOKEN = 'XXXX.DUMMY.TOKEN.XXXX'


def _values(config=None):
    """Return ``(site_key, secret_key)``.

    ``config`` given -> read from that mapping (used by the tests).
    ``config`` None  -> read the runtime editable settings.
    """
    if config is not None:
        return (
            config.get('TURNSTILE_SITE_KEY') or '',
            config.get('TURNSTILE_SECRET_KEY') or '',
        )

    from .settings import get as setting_value
    return setting_value('turnstile_site_key'), setting_value('turnstile_secret_key')


def is_enabled(config=None):
    """True when both Turnstile keys are configured."""
    site_key, secret_key = _values(config)
    return bool(site_key and secret_key)


def _post(payload, timeout, opener):
    """POST ``payload`` to siteverify.

    :return: ``(decoded_json, unreachable)``.  ``decoded_json`` is ``None`` when
        the call failed; ``unreachable`` distinguishes a network problem from a
        reply that could not be parsed, which matters for the fail-open option.
    """
    data = urllib.parse.urlencode(payload).encode('utf-8')
    request = urllib.request.Request(SITEVERIFY_URL, data=data, method='POST')
    request.add_header('Content-Type', 'application/x-www-form-urlencoded')

    open_url = opener or urllib.request.urlopen
    try:
        with open_url(request, timeout=timeout) as response:
            body = response.read().decode('utf-8', 'replace')
    except (urllib.error.URLError, OSError, ValueError) as exc:
        log.warning('无法连接 Cloudflare 校验接口: %s', exc)
        return None, True

    try:
        return json.loads(body), False
    except ValueError:
        log.warning('Cloudflare 返回了无法解析的内容: %r', body[:200])
        return None, False


def verify(token, remote_ip, config=None, opener=None):
    """Validate a Turnstile token against Cloudflare's siteverify endpoint.

    Returns ``True`` when the request may proceed.  When Turnstile is not
    configured this returns ``True`` so that the rest of the app is unaffected.

    Failures are **closed**: a missing token, an unreachable Cloudflare endpoint
    or a malformed reply all deny the request.  That is deliberate — failing
    open would let anyone bypass the challenge by blocking the verification
    call — but it does mean an outage at Cloudflare blocks logins.  The reason
    is always logged so the cause is visible.

    :param opener: injection point for tests; defaults to ``urlopen``.
    """
    site_key, secret_key = _values(config)
    if not (site_key and secret_key):
        return True

    if not token:
        log.info('人机验证失败: 表单未携带令牌')
        return False

    if config is None:
        from flask import current_app
        timeout = current_app.config['TURNSTILE_TIMEOUT_SECONDS']
        fail_open = current_app.config.get('TURNSTILE_FAIL_OPEN', False)
    else:
        timeout = config.get('TURNSTILE_TIMEOUT_SECONDS', 5)
        fail_open = config.get('TURNSTILE_FAIL_OPEN', False)

    payload = {'secret': secret_key, 'response': token}
    if remote_ip:
        payload['remoteip'] = remote_ip

    result, unreachable = _post(payload, timeout, opener)
    if result is None:
        if unreachable and fail_open:
            log.warning('Cloudflare 不可达，按 SPEAK_TURNSTILE_FAIL_OPEN=true 放行本次验证。')
            return True
        log.warning('人机验证无法完成，已按不通过处理')
        return False

    if result.get('success'):
        return True

    log.info('人机验证未通过: %s', result.get('error-codes') or result)
    return False


def verify_secret_key(secret_key, timeout=5, opener=None):
    """Check a secret key against Cloudflare without needing a real widget token.

    A dummy token is submitted on purpose: a *valid* key answers
    ``invalid-input-response`` (the token was junk), whereas a wrong key answers
    ``invalid-input-secret``.  That distinction is what makes the setup wizard
    able to tell the operator their key is wrong before anyone tries to log in.

    :return: ``(ok, message)`` where ``message`` is user facing Chinese text.
    """
    secret_key = (secret_key or '').strip()
    if not secret_key:
        return False, '请先填写密钥（Secret Key）。'

    result, unreachable = _post({'secret': secret_key, 'response': _DUMMY_TOKEN},
                                timeout, opener)
    if result is None:
        if unreachable:
            return False, '无法连接 Cloudflare，请检查服务器网络后重试。'
        return False, 'Cloudflare 返回了无法识别的内容，请稍后重试。'

    codes = result.get('error-codes') or []

    if result.get('success'):
        # A dummy token should never pass; treat it as "unexpected but usable".
        return True, '密钥有效。'

    if 'invalid-input-secret' in codes:
        return False, '密钥无效：Cloudflare 不认这个 Secret Key，请确认是否复制完整。'

    if 'invalid-input-response' in codes:
        return True, '密钥有效（令牌是测试用的假令牌，所以才被拒绝，这是正常的）。'

    return False, '校验未通过：%s' % ('、'.join(codes) or '未知原因')
