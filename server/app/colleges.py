import json
import os

from . import names

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "us_colleges.json")
_rows = []


def rows():
    if not _rows:
        with open(PATH, encoding="utf-8") as fh:
            _rows.extend(json.load(fh))
    return _rows


def search(query, limit=8):
    wanted = [w for w in names.words(query) if w not in names.STOP]
    if len("".join(wanted)) < 3:
        return []
    start = names.compact(query)
    hits = []
    for row in rows():
        have = names.words(row["name"])
        if all(any(h.startswith(w) for h in have) for w in wanted) or names.looks_same(row["name"], query):
            hits.append((0 if names.compact(row["name"]).startswith(start) else 1, len(row["name"]), row))
    hits.sort(key=lambda hit: (hit[0], hit[1]))
    return [{"name": row["name"], "domains": row["domains"]} for _, _, row in hits[:limit]]


def best(name):
    if len(names.compact(name)) < 6:
        return None
    for row in rows():
        if names.looks_same(row["name"], name):
            return {"name": row["name"], "domains": row["domains"]}
    hits = search(name, 2)
    return hits[0] if len(hits) == 1 else None


def domain_known(domain, known):
    domain = (domain or "").lower()
    return any(domain == d or domain.endswith("." + d) for d in known)
