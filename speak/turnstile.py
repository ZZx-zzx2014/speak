"""Cloudflare Turnstile verification (bot protection).

Turnstile is optional and stays completely disabled until both
``SPEAK_TURNSTILE_SITE_KEY`` and ``SPEAK_TURNSTILE_SECRET_KEY`` are configured,
so local development needs no Cloudflare account.

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


def is_enabled(config):
    """True when both Turnstile keys are configured."""
    return bool(config.get('TURNSTILE_SITE_KEY') and config.get('TURNSTILE_SECRET_KEY'))


def verify(token, remote_ip, config, opener=None):
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
    if not is_enabled(config):
        return True

    if not token:
        log.info('人机验证失败: 表单未携带令牌')
        return False

    payload = {
        'secret': config['TURNSTILE_SECRET_KEY'],
        'response': token,
    }
    if remote_ip:
        payload['remoteip'] = remote_ip

    data = urllib.parse.urlencode(payload).encode('utf-8')
    request = urllib.request.Request(SITEVERIFY_URL, data=data, method='POST')
    request.add_header('Content-Type', 'application/x-www-form-urlencoded')

    open_url = opener or urllib.request.urlopen
    try:
        with open_url(request, timeout=config['TURNSTILE_TIMEOUT_SECONDS']) as response:
            body = response.read().decode('utf-8', 'replace')
    except (urllib.error.URLError, OSError, ValueError) as exc:
        log.warning('人机验证无法连接 Cloudflare (%s)，已按不通过处理', exc)
        return False

    try:
        result = json.loads(body)
    except ValueError:
        log.warning('人机验证返回了无法解析的内容: %r', body[:200])
        return False

    if result.get('success'):
        return True

    log.info('人机验证未通过: %s', result.get('error-codes') or result)
    return False
