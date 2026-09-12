"""Pick the Socket.IO browser build that matches the installed server.

The Socket.IO and Engine.IO protocols changed between major versions and the two
sides must agree:

===========================  ======================  =====================
``python-engineio``          Engine.IO protocol      Browser client
===========================  ======================  =====================
``3.x``                      v3 (binary polling)     ``socket.io-client`` 2.x
``4.x``                      v4                      ``socket.io-client`` 4.x
===========================  ======================  =====================

The original project hard-coded ``socket.io/4.0.0`` from a CDN regardless of the
installed Python packages, which silently breaks the chat whenever an older
engineio is installed.  Resolving the version at runtime removes that trap.

The *file name* differs between generations as well.  ``socket.io-client`` 4.x
publishes ``dist/socket.io.min.js``, while 2.x only publishes ``dist/socket.io.js``
on npm (the ``.min.js`` name exists solely on cdnjs for that release line), so the
mirror list is chosen per protocol generation.
"""

import logging

import engineio

try:  # Python >= 3.8
    from importlib.metadata import version as _distribution_version
except ImportError:  # pragma: no cover - only on very old interpreters
    _distribution_version = None

log = logging.getLogger(__name__)

#: Newest browser release speaking each Engine.IO protocol generation.
_CLIENT_VERSION_BY_ENGINEIO_MAJOR = {
    3: '2.5.0',
    4: '4.8.3',
}
_FALLBACK_CLIENT_VERSION = '4.8.3'

#: Version of the copy bundled in ``speak/static/vendor``.  Bump it together
#: with the file whenever the client is updated.
VENDORED_CLIENT_VERSION = '4.8.3'
VENDORED_CLIENT_PATH = 'vendor/socket.io.min.js'

#: CDN mirrors per Engine.IO generation, tried in order by the browser.
#: ``{version}`` is replaced with the resolved client version.
_CDN_TEMPLATES_BY_ENGINEIO_MAJOR = {
    # socket.io-client 2.x: npm ships dist/socket.io.js (no .min.js variant).
    3: (
        'https://cdn.jsdelivr.net/npm/socket.io-client@{version}/dist/socket.io.js',
        'https://cdnjs.cloudflare.com/ajax/libs/socket.io/{version}/socket.io.min.js',
        'https://unpkg.com/socket.io-client@{version}/dist/socket.io.js',
    ),
    4: (
        'https://cdn.jsdelivr.net/npm/socket.io-client@{version}/dist/socket.io.min.js',
        'https://cdnjs.cloudflare.com/ajax/libs/socket.io/{version}/socket.io.min.js',
        'https://unpkg.com/socket.io-client@{version}/dist/socket.io.min.js',
    ),
}


def engineio_version():
    """Return the installed ``python-engineio`` version string.

    ``python-engineio`` 4.14 removed the module level ``engineio.__version__``
    attribute, so the distribution metadata is the primary source here and the
    module attribute is only a fallback for older releases.
    """
    if _distribution_version is not None:
        try:
            return _distribution_version('python-engineio')
        except Exception:
            pass
    return getattr(engineio, '__version__', '')


def engineio_major():
    """Major version of the installed ``python-engineio``."""
    try:
        return int(str(engineio_version()).split('.')[0])
    except (TypeError, ValueError):
        return 4


def detect_client_version():
    """Browser client version matching the installed server stack."""
    return _CLIENT_VERSION_BY_ENGINEIO_MAJOR.get(
        engineio_major(), _FALLBACK_CLIENT_VERSION
    )


def detect_cdn_templates():
    """CDN mirrors matching the installed server stack."""
    return _CDN_TEMPLATES_BY_ENGINEIO_MAJOR.get(
        engineio_major(), _CDN_TEMPLATES_BY_ENGINEIO_MAJOR[4]
    )


def resolve_client_version(configured=None):
    """Return the configured version, or auto-detect one."""
    if configured:
        return configured
    version = detect_client_version()
    log.debug('检测到 python-engineio %s，使用 Socket.IO 客户端 %s',
              engineio_version(), version)
    return version


def _static_url(filename):
    """Build a static URL, tolerating a missing application context."""
    try:
        from flask import url_for
        return url_for('static', filename=filename)
    except Exception:  # pragma: no cover - only in the unit tests
        return '/static/' + filename


def vendored_client_url():
    """URL of the locally bundled client, or ``None`` when it does not match.

    The client is committed under ``speak/static/vendor`` so the chat keeps
    working when a CDN mirror is blocked or unreachable.  The file is version
    specific, so it is only offered when it matches the detected generation.
    """
    needed = detect_client_version()
    if needed != VENDORED_CLIENT_VERSION:
        log.warning(
            '本地内置的 Socket.IO 客户端为 %s，与当前 engineio 需要的 %s 不匹配，'
            '将回退到 CDN。', VENDORED_CLIENT_VERSION, needed,
        )
        return None
    return _static_url(VENDORED_CLIENT_PATH)


def cdn_urls(config):
    """Ordered list of URLs the browser should try for the client.

    The bundled local copy comes first (most reliable), then the CDN mirrors.
    ``SPEAK_SOCKETIO_CDN_BASES`` replaces the built-in mirror list; leave it
    empty to use the set matching the installed Engine.IO generation.
    """
    version = resolve_client_version(config.get('SOCKETIO_CLIENT_VERSION'))
    templates = config.get('SOCKETIO_CDN_BASES') or detect_cdn_templates()
    urls = [template.format(version=version) for template in templates if template]

    local = vendored_client_url()
    if local and local not in urls:
        urls.insert(0, local)
    return urls
