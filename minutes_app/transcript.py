import re
import time

from .config import zm

TS_LINE = re.compile(r"^\(?\d{1,2}:\d{2}(:\d{2})?\s*([AaPp]\.?[Mm]\.?)?\)?$")
CHAT_LINE = re.compile(r"^(\d{1,2}:\d{2}:\d{2})\s+From\s+(.+?)(?:\s+to\s+[^:]+?)?\s*:\s*(.*)$")


class Line:
    __slots__ = ("t", "speaker", "text", "source", "id")

    def __init__(self, t, speaker, text, source, id=None):
        self.t, self.speaker, self.text, self.source, self.id = t, speaker, text, source, id

    def as_dict(self):
        return {"t": self.t, "speaker": self.speaker, "text": self.text, "source": self.source}

    def render(self):
        stamp = zm.hhmmss(self.t) if self.t is not None else "--:--:--"
        tag = " (chat)" if self.source == "chat" else ""
        who = (self.speaker + tag + ": ") if self.speaker else ""
        return "[%s] %s%s" % (stamp, who, self.text)


def name_like(line):
    s = line.strip()
    if not s or len(s) > 48 or TS_LINE.match(s) or s[-1] in ".?!,;:":
        return False
    words = s.split()
    if not 1 <= len(words) <= 6:
        return False
    return all(w[0].isupper() or w[0].isdigit() or "@" in w or w.startswith("(") for w in words)


def looks_like_speaker(line, nxt):
    return bool(nxt) and name_like(line) and (bool(TS_LINE.match(nxt.strip())) or not name_like(nxt))


def parse_panel_text(raw_lines):
    out, i, lines = [], 0, [l.strip() for l in raw_lines if l.strip()]
    speaker, stamp = "", None
    while i < len(lines):
        cur = lines[i]
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        if looks_like_speaker(cur, nxt):
            speaker = cur
            i += 1
            if i < len(lines) and TS_LINE.match(lines[i]):
                stamp = lines[i]
                i += 1
            continue
        if TS_LINE.match(cur):
            stamp = cur
            i += 1
            continue
        m = re.match(r"^([^:]{2,48}):\s+(.+)$", cur)
        if m and not speaker_line_is_sentence(m.group(1)):
            out.append((m.group(1).strip(), m.group(2).strip(), stamp))
        else:
            out.append((speaker, cur, stamp))
        i += 1
    return out


def speaker_line_is_sentence(prefix):
    return len(prefix.split()) > 7


def to_seconds(stamp):
    if not stamp:
        return None
    m = re.match(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?", stamp)
    if not m:
        return None
    a, b, c = int(m.group(1)), int(m.group(2)), m.group(3)
    return a * 3600 + b * 60 + int(c) if c is not None else a * 60 + b


class Transcript:
    def __init__(self):
        self.lines = []
        self.started = time.time()
        self._snapshot_tail = []


    def add(self, speaker, text, source, t=None):
        text = (text or "").strip()
        if not text:
            return
        if t is None and source == "captions":
            t = time.time() - self.started
        if self.lines:
            last = self.lines[-1]
            if last.source == source and last.speaker == speaker:
                if text == last.text or last.text.startswith(text):
                    return
                if text.startswith(last.text):
                    last.text = text
                    return
        for recent in self.lines[-40:]:
            if recent.speaker == speaker and recent.text == text:
                return
        self.lines.append(Line(t, speaker, text, source))

    def ingest_snapshot(self, raw_text):
        raw = [l.strip() for l in raw_text.splitlines() if l.strip()][-400:]
        if not raw:
            return 0
        tail = self._snapshot_tail
        start = 0
        if tail:
            anchor = tail[-1]
            found = None
            for j in range(len(raw) - 1, -1, -1):
                if raw[j] == anchor or (len(anchor) > 10 and raw[j].startswith(anchor)):
                    found = j
                    break
            if found is not None:
                start = found
                for k in range(found - 1, max(-1, found - 5), -1):
                    if looks_like_speaker(raw[k], raw[k + 1]):
                        start = k
                        break
        before = len(self.lines)
        for speaker, text, stamp in parse_panel_text(raw[start:]):
            self.add(speaker, text, "captions")
        self._snapshot_tail = raw[-50:]
        return len(self.lines) - before

    def import_vtt(self, text):
        n = 0
        for start, _, speaker, said in zm.parse_vtt(text):
            self.add(speaker, said, "vtt", t=start)
            n += 1
        return n

    def import_page_text(self, text):
        n = 0
        for speaker, said, stamp in parse_panel_text(text.splitlines()):
            self.add(speaker, said, "recording", t=to_seconds(stamp))
            n += 1
        return n

    def import_chat(self, text):
        n = 0
        for raw in text.splitlines():
            m = CHAT_LINE.match(raw.strip())
            if m:
                self.add(m.group(2).strip(), m.group(3).strip(), "chat", t=to_seconds(m.group(1)))
                n += 1
        return n

    def import_any(self, text, name=""):
        name = name.lower()
        if name.endswith(".vtt") or "-->" in text[:2000]:
            return "vtt", self.import_vtt(text)
        if "chat" in name or CHAT_LINE.match(text.strip().splitlines()[0] if text.strip() else ""):
            return "chat", self.import_chat(text)
        return "text", self.import_page_text(text)


    def sort(self):
        self.lines.sort(key=lambda l: (l.t is None, l.t or 0))

    def text(self, start=0):
        return "\n".join(l.render() for l in self.lines[start:])

    def to_list(self, start=0):
        return [l.as_dict() for l in self.lines[start:]]

    @classmethod
    def from_list(cls, rows):
        tr = cls()
        tr.lines = [Line(r.get("t"), r.get("speaker", ""), r.get("text", ""), r.get("source", ""), r.get("id"))
                    for r in rows]
        return tr
