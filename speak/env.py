"""Minimal ``.env`` loader built on the standard library.

Flask's built-in dotenv support requires the optional ``python-dotenv``
dependency; a ~40 line loader keeps the dependency list unchanged while making
the precedence rule explicit: **real environment variables always win over the
file**, so exporting a variable in the shell still overrides ``.env``.

Supported syntax (deliberately small)::

    # comment lines and blank lines are ignored
    KEY=value
    KEY="quoted value"
    export KEY=value
"""

import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)


def load_dotenv(path, override=False):
    """Load ``KEY=VALUE`` pairs from ``path`` into ``os.environ``.

    :param path: file to read; a missing file is not an error.
    :param override: when ``False`` (the default) existing environment
        variables are left untouched.
    :return: mapping of the values that were actually applied.
    """
    file_path = Path(path)
    if not file_path.is_file():
        return {}

    try:
        content = file_path.read_text(encoding='utf-8')
    except OSError as exc:  # pragma: no cover - unreadable file
        log.warning('无法读取 %s: %s', file_path, exc)
        return {}

    applied = {}
    for number, raw_line in enumerate(content.splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('export '):
            line = line[len('export '):].lstrip()

        key, separator, value = line.partition('=')
        key = key.strip()
        if not separator or not key:
            log.warning('%s 第 %d 行不是有效的 KEY=VALUE，已忽略', file_path, number)
            continue

        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]

        if not override and key in os.environ:
            continue

        os.environ[key] = value
        applied[key] = value

    return applied
