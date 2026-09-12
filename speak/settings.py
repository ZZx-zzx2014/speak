"""Runtime-editable settings, stored in the database.

Environment variables keep working (they are convenient for automation and for
pinning a value), but a value saved from the admin UI wins, so the operator can
change things without a redeploy.

Precedence, highest first:

1. the ``settings`` table (edited from ``/admin/settings``)
2. ``current_app.config`` (the environment / :class:`speak.config.Config`)
3. the built-in default below
"""

import logging
import sqlite3

from flask import current_app, g

from .db import get_db

log = logging.getLogger(__name__)

#: Every setting the application understands, with its default value.
DEFAULTS = {
    'site_name': 'Speak 聊天室',
    'site_announcement': '',
    'turnstile_site_key': '',
    'turnstile_secret_key': '',
}

#: Setting name -> config attribute, so environment variables keep working.
CONFIG_KEYS = {
    'site_name': 'SITE_NAME',
    'site_announcement': 'SITE_ANNOUNCEMENT',
    'turnstile_site_key': 'TURNSTILE_SITE_KEY',
    'turnstile_secret_key': 'TURNSTILE_SECRET_KEY',
}

_CACHE_ATTR = '_speak_settings_cache'


def _load():
    """Build the effective settings once per request.

    :return: ``(values, sources)`` where ``sources`` maps each key to
        ``'database'``, ``'environment'`` or ``'default'`` so the UI can explain
        where a value comes from.
    """
    values = dict(DEFAULTS)
    sources = {key: 'default' for key in DEFAULTS}

    for setting_key, config_key in CONFIG_KEYS.items():
        config_value = current_app.config.get(config_key)
        # A config value equal to the built-in default means "nobody set this",
        # so it must not be reported as coming from the environment.
        if config_value and config_value != DEFAULTS[setting_key]:
            values[setting_key] = config_value
            sources[setting_key] = 'environment'

    try:
        rows = get_db().execute('SELECT key, value FROM settings').fetchall()
    except sqlite3.Error:  # pragma: no cover - table not created yet
        log.warning('无法读取 settings 表', exc_info=True)
        return values, sources

    for row in rows:
        if row['key'] in DEFAULTS and row['value']:
            values[row['key']] = row['value']
            sources[row['key']] = 'database'

    return values, sources


def _cache():
    cached = getattr(g, _CACHE_ATTR, None)
    if cached is None:
        cached = _load()
        setattr(g, _CACHE_ATTR, cached)
    return cached


def invalidate():
    """Drop the per-request cache (call after saving)."""
    if _CACHE_ATTR in g:
        delattr(g, _CACHE_ATTR)


def all_values():
    """Effective value of every known setting."""
    return dict(_cache()[0])


def all_sources():
    """Where each effective value comes from."""
    return dict(_cache()[1])


def get(key, default=None):
    """Effective value of one setting."""
    values = _cache()[0]
    if key in values:
        return values[key]
    return DEFAULTS.get(key, default)


def source(key):
    """``'database'`` | ``'environment'`` | ``'default'`` for one setting."""
    return _cache()[1].get(key, 'default')


def save(mapping):
    """Persist the supplied settings; unknown keys are ignored.

    Empty strings are stored explicitly so that clearing a value in the UI
    actually clears it (rather than falling back to the environment).
    """
    db = get_db()
    applied = []
    for key, value in mapping.items():
        if key not in DEFAULTS:
            continue
        db.execute(
            'INSERT OR REPLACE INTO settings (key, value, updated_at) '
            "VALUES (?, ?, datetime('now'))",
            (key, '' if value is None else str(value)),
        )
        applied.append(key)
    invalidate()
    return applied
