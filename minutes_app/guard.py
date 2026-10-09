import re
import unicodedata

RANGES = ((0x00AD, 0x00AD), (0x061C, 0x061C), (0x115F, 0x1160), (0x17B4, 0x17B5), (0x180E, 0x180E), (0x200B, 0x200F),
          (0x202A, 0x202E), (0x2060, 0x206F), (0x3164, 0x3164), (0xFE00, 0xFE0F), (0xFEFF, 0xFEFF), (0xFFA0, 0xFFA0),
          (0xE0000, 0xE007F), (0xE0100, 0xE01EF))
INVISIBLE = re.compile("[" + "".join(re.escape(chr(a)) + ("-" + re.escape(chr(b)) if b != a else "") for a, b in RANGES) + "]")
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
BLANK_RUN = re.compile(r"\n{4,}")
SPACE_RUN = re.compile(r"[ \t]{40,}")
REPEAT_WORDS = re.compile(r"(\b[^\s]+(?:\s+[^\s]+){0,5}?)(?:[\s,.!-]+\1\b){7,}", re.I)
TAGS = ("transcript", "excerpt", "minutes", "example", "conversation", "facts", "data", "current_draft", "notes", "reference")
TAG = re.compile(r"</?\s*(" + "|".join(TAGS) + r")\b", re.I)


def clean(text, limit=None):
    text = unicodedata.normalize("NFC", str(text or ""))
    text = INVISIBLE.sub("", text)
    text = CONTROL.sub("", text)
    text = BLANK_RUN.sub("\n\n\n", text)
    text = SPACE_RUN.sub(" ", text)
    return text[:limit] if limit else text


def data(name, text, limit=None, attrs=""):
    own = re.compile(r"</?\s*" + re.escape(name) + r"\b", re.I)
    body = clean(text, limit)
    for pattern in (TAG, own):
        body = pattern.sub(lambda m: m.group(0).replace("<", "(").replace(">", ")"), body)
    return "<%s%s>\n%s\n</%s>" % (name, (" " + attrs) if attrs else "", body, name)


def squash_repeats(text):
    out = REPEAT_WORDS.sub(lambda m: m.group(1) + " [repeated text removed]", text)
    lines, kept, last, count = out.split("\n"), [], None, 0
    for line in lines:
        count = count + 1 if line.strip() and line == last else 0
        last = line
        if count < 3:
            kept.append(line)
    return "\n".join(kept)


def output(text, limit=60000):
    return squash_repeats(clean(text, limit))
