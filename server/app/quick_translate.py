import time

import httpx

from .settings import settings

CODES = {"zh-Hans": "zh", "zh-Hant": "zt"}
LABEL = "Quick translation (LibreTranslate on the Live Minutes server)"
_seen = {"at": 0.0, "url": "", "targets": frozenset()}


def targets():
    url = settings.libretranslate_url
    if not url:
        return frozenset()
    if _seen["url"] == url and time.time() - _seen["at"] < 300:
        return _seen["targets"]
    try:
        r = httpx.get(url + "/languages", timeout=5)
        r.raise_for_status()
        rows = r.json()
        found = frozenset(next((row.get("targets") or [] for row in rows if row.get("code") == "en"), []))
    except (httpx.HTTPError, ValueError, AttributeError, TypeError):
        found = frozenset()
    _seen.update(at=time.time(), url=url, targets=found)
    return found


def code(language):
    return language if language in targets() else CODES.get(language, language)


def supports(language):
    return code(language) in targets()


def translate(items, language):
    keys = list(items)
    r = httpx.post(settings.libretranslate_url + "/translate", timeout=180,
                   json={"q": [items[k] for k in keys], "source": "en", "target": code(language), "format": "text"})
    r.raise_for_status()
    out = r.json().get("translatedText")
    if not isinstance(out, list) or len(out) != len(keys) or not all(isinstance(v, str) for v in out):
        raise ValueError("unexpected answer")
    return dict(zip(keys, out))
