import re

STOP = {"of", "the", "and", "at", "for", "in"}


def words(name):
    return re.findall(r"[a-z0-9]+", (name or "").lower())


def compact(name):
    return "".join(words(name))


def acronym(name):
    return "".join(w[0] for w in words(name) if w not in STOP)


def looks_same(a, b):
    ca, cb = compact(a), compact(b)
    if not ca or not cb:
        return False
    if ca == cb:
        return True
    aa, ab = acronym(a), acronym(b)
    if len(aa) >= 2 and aa == cb or len(ab) >= 2 and ab == ca:
        return True
    short, long_ = sorted((ca, cb), key=len)
    if len(short) >= 5 and long_.startswith(short):
        return True
    wa, wb = set(words(a)) - STOP, set(words(b)) - STOP
    return bool(wa and wb) and len(wa & wb) / len(wa | wb) >= 0.75


def similar(rows, name, skip_id=None):
    return [{"id": r.id, "name": r.name} for r in rows if r.id != skip_id and looks_same(r.name, name)]
