import re

MOVE = re.compile(r"\b(i\s+(?:would\s+like\s+to\s+)?move\b(?!\s+(?:on|forward|to\s+(?:our|the\s+next|number|item)))"
                  r"|i\s+make\s+a\s+motion|motion\s+to\b|so\s+moved)", re.I)
ASK = re.compile(r"\b(?:can|could|may)\s+i\s+(?:get|have|hear)\s+a\s+motion|\bdo\s+i\s+(?:hear|have)\s+a\s+motion"
                 r"|\bis\s+there\s+a\s+motion|\bwould\s+(?:someone|anyone)\s+(?:like\s+to\s+)?(?:make\s+a\s+)?motion", re.I)
SECOND = re.compile(r"^\W*(i\s+)?second(ed)?\b|\bi\s+second\b", re.I)
CHAIR = re.compile(r"motion(?:ed)?\s+by\s+([A-Z][\w'-]+).{0,40}?seconded\s+by\s+([A-Z][\w'-]+)", re.I)
ROLL = re.compile(r"\broll\s*call\b", re.I)
RESULT = re.compile(r"\bmotion\s+(passes|passed|carries|carried|fails|failed)\b|\bthe\s+motion\s+(passes|fails)\b", re.I)
VOTE = re.compile(r"^\W*(yes|yea|aye|no|nay|abstain|i\s+abstain|present)\W*$", re.I)


def track(lines):
    motions, cur = [], None
    for ln in lines:
        text = ln.text
        if MOVE.search(text) and not ASK.search(text):
            cur = {"t": ln.t, "mover": ln.speaker, "text": text[:240], "seconder": "",
                   "votes": {}, "roll_call": False, "result": "", "confirmed": False}
            motions.append(cur)
            continue
        m = CHAIR.search(text)
        if m and (cur is None or cur["confirmed"] or cur["result"]):
            cur = {"t": ln.t, "mover": "", "text": text[:240], "seconder": "",
                   "votes": {}, "roll_call": False, "result": "", "confirmed": False}
            motions.append(cur)
        if cur is None:
            continue
        if m:
            cur["mover"], cur["seconder"], cur["confirmed"] = m.group(1), m.group(2), True
        elif not cur["seconder"] and SECOND.search(text) and ln.speaker != cur["mover"]:
            cur["seconder"] = ln.speaker
        if ROLL.search(text):
            cur["roll_call"] = True
        v = VOTE.match(text)
        if v and cur["roll_call"] and ln.speaker:
            cur["votes"][ln.speaker] = v.group(1).lower().replace("i ", "")
        r = RESULT.search(text)
        if r:
            cur["result"] = (r.group(1) or r.group(2)).lower()
    for mo in motions:
        vals = list(mo["votes"].values())
        mo["tally"] = {k: vals.count(k) for k in sorted(set(vals))}
        mo["status"] = mo["result"] or ("seconded, vote pending" if mo["seconder"] else "needs a second")
    return motions
