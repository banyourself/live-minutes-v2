import os
import re
from functools import lru_cache

PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "docs", "AI-REFERENCE.md")
HOW = re.compile(r"\b(how|where|what is|what's|can i|help|find|explain|guide|page|button|tab|steps?)\b", re.I)


@lru_cache(maxsize=1)
def text():
    try:
        with open(PATH, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def section(title):
    parts = re.split(r"(?m)^## ", text())
    return next((p.split("\n", 1)[1].strip() for p in parts if p.startswith(title)), "")


def for_question(question):
    if not HOW.search(question or ""):
        return ""
    body = section("Where things are")
    return ("How the website is laid out (for answering how-to questions; point to the page and keep it short):\n" + body) if body else ""
