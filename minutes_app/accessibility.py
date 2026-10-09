import os
import re
import zipfile
from xml.sax.saxutils import escape

from defusedxml import ElementTree

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
DC = "{http://purl.org/dc/elements/1.1/}"
VAGUE_LINKS = {"click here", "here", "link", "this", "more", "read more", "this link"}
CORE_TYPE = "application/vnd.openxmlformats-package.core-properties+xml"
CORE_REL = "http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties"


def _read(z, name):
    try:
        return z.read(name)
    except KeyError:
        return b""


def _xml(data):
    return ElementTree.fromstring(data) if data else None


def _text(p):
    return "".join(t.text or "" for t in p.iter(W + "t"))


def _luminance(hex6):
    def chan(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (int(hex6[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(b)


def contrast_on_white(hex6):
    return 1.05 / (_luminance(hex6) + 0.05)


def contrast(a, b):
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def _fill(el, parents):
    while el is not None:
        if el.tag in (W + "p", W + "tc"):
            shd = el.find("./%s%sPr/%sshd" % (W, "p" if el.tag == W + "p" else "tc", W))
            fill = (shd.get(W + "fill") or "") if shd is not None else ""
            if re.fullmatch(r"[0-9A-Fa-f]{6}", fill):
                return fill
        el = parents.get(el)
    return "FFFFFF"


def heading_styles(styles):
    out = set()
    if styles is None:
        return out
    for st in styles.iter(W + "style"):
        sid = st.get(W + "styleId", "")
        name = st.find(W + "name")
        label = (name.get(W + "val", "") if name is not None else "").lower()
        if st.find(".//" + W + "outlineLvl") is not None or label.startswith("heading") or label == "title":
            out.add(sid)
    return out


def default_language(styles):
    if styles is None:
        return ""
    lang = styles.find("./%sdocDefaults/%srPrDefault/%srPr/%slang" % (W, W, W, W))
    return lang.get(W + "val", "") if lang is not None else ""


def check(path):
    with zipfile.ZipFile(path) as z:
        doc = _xml(_read(z, "word/document.xml"))
        styles = _xml(_read(z, "word/styles.xml"))
        core = _xml(_read(z, "docProps/core.xml"))
    results = []

    def add(cid, label, status, detail, count=0):
        results.append({"id": cid, "label": label, "status": status, "detail": detail, "count": count})

    title = (core.findtext(DC + "title") or "").strip() if core is not None else ""
    add("title", "Document title", "pass" if title else "fail",
        "Title is \"%s\"." % title if title else "Screen readers announce the title. Live Minutes sets it when it builds the file.")
    lang = default_language(styles) or ((core.findtext(DC + "language") or "").strip() if core is not None else "")
    add("language", "Document language", "pass" if lang else "fail",
        "Language is %s." % lang if lang else "Without a language, screen readers may read the text with the wrong voice.")

    heads = heading_styles(styles)
    paras = list(doc.iter(W + "p")) if doc is not None else []
    n_heads = 0
    for p in paras:
        ps = p.find("./%spPr/%spStyle" % (W, W))
        if ps is not None and ps.get(W + "val", "") in heads:
            n_heads += 1
        elif p.find("./%spPr/%soutlineLvl" % (W, W)) is not None:
            n_heads += 1
    add("headings", "Headings", "pass" if n_heads else "warn",
        "%d heading%s let people jump between sections." % (n_heads, "" if n_heads == 1 else "s") if n_heads else
        "Use Word's Heading styles for section titles in the template so screen readers can move between them.",
        n_heads)

    missing_alt = 0
    for pr in (doc.iter(WP + "docPr") if doc is not None else []):
        if not (pr.get("descr") or "").strip() and not (pr.get("title") or "").strip():
            missing_alt += 1
    add("alt_text", "Image descriptions", "fail" if missing_alt else "pass",
        "%d image%s %s no description. Right-click each image in the template, choose View Alt Text, and describe it."
        % (missing_alt, "" if missing_alt == 1 else "s", "has" if missing_alt == 1 else "have") if missing_alt else
        "Every image has a description, or there are no images.", missing_alt)

    tables = list(doc.iter(W + "tbl")) if doc is not None else []
    no_header = 0
    for t in tables:
        first = t.find(W + "tr")
        if first is not None and first.find("./%strPr/%stblHeader" % (W, W)) is None:
            no_header += 1
    add("table_headers", "Table header rows", "warn" if no_header else "pass",
        "%d of %d table%s %s no header row. In the template, select the first row and turn on Repeat Header Rows."
        % (no_header, len(tables), "" if len(tables) == 1 else "s", "has" if no_header == 1 else "have") if no_header else
        "Every table marks its header row, or there are no tables.", no_header)

    blanks, run, longest = 0, 0, 0
    body = doc.find(W + "body") if doc is not None else None
    for p in (el for el in (body if body is not None else []) if el.tag == W + "p"):
        empty = not _text(p).strip() and p.find(".//" + W + "drawing") is None and p.find(".//" + W + "br") is None
        run = run + 1 if empty else 0
        if run == 3:
            blanks += 1
        longest = max(longest, run)
    add("blank_lines", "Spacing", "warn" if blanks else "pass",
        "%d place%s use%s three or more empty lines for spacing. Screen readers read each one as \"blank\"; use paragraph spacing instead."
        % (blanks, "" if blanks == 1 else "s", "s" if blanks == 1 else "") if blanks else "No stacks of empty lines.", blanks)

    small = low = 0
    parents = {child: parent for parent in doc.iter() for child in parent} if doc is not None else {}
    for r in (doc.iter(W + "r") if doc is not None else []):
        if not "".join(t.text or "" for t in r.iter(W + "t")).strip():
            continue
        sz = r.find("./%srPr/%ssz" % (W, W))
        if sz is not None and (sz.get(W + "val") or "").isdigit() and int(sz.get(W + "val")) < 18:
            small += 1
        color = r.find("./%srPr/%scolor" % (W, W))
        val = (color.get(W + "val") or "") if color is not None else ""
        if re.fullmatch(r"[0-9A-Fa-f]{6}", val) and contrast(val, _fill(r, parents)) < 4.5:
            low += 1
    add("text_size", "Text size", "warn" if small else "pass",
        "%d piece%s of text %s smaller than 9 point." % (small, "" if small == 1 else "s", "is" if small == 1 else "are")
        if small else "All text is at least 9 point.", small)
    add("contrast", "Color contrast", "warn" if low else "pass",
        "%d piece%s of text %s too light to read easily on its background." % (low, "" if low == 1 else "s", "is" if low == 1 else "are")
        if low else "Text colors have enough contrast.", low)

    vague = 0
    for h in (doc.iter(W + "hyperlink") if doc is not None else []):
        if _text(h).strip().lower().rstrip(".") in VAGUE_LINKS:
            vague += 1
    add("links", "Link text", "warn" if vague else "pass",
        "%d link%s say%s only \"click here\" or similar. Describe where the link goes." % (
            vague, "" if vague == 1 else "s", "s" if vague == 1 else "") if vague else "Links describe where they go.",
        vague)
    passed = sum(1 for r in results if r["status"] == "pass")
    return {"passed": passed, "total": len(results), "checks": results}


def _core_xml(title, language):
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            '<dc:title>%s</dc:title><dc:language>%s</dc:language><dc:creator>Live Minutes</dc:creator>'
            '</cp:coreProperties>' % (escape(title), escape(language)))


def _set_tag(xml, tag, value):
    pat = re.compile(r"<%s(?:\s[^>]*)?(?:/>|>.*?</%s>)" % (tag, tag), re.S)
    new = "<%s>%s</%s>" % (tag, escape(value), tag)
    if pat.search(xml):
        return pat.sub(lambda m: new, xml, count=1)
    return xml.replace("</cp:coreProperties>", new + "</cp:coreProperties>", 1)


def _set_style_lang(xml, language):
    lang = '<w:lang w:val="%s"/>' % escape(language, {'"': "&quot;"})
    m = re.search(r"<w:rPrDefault>(.*?)</w:rPrDefault>", xml, re.S)
    if m:
        inner = m.group(1)
        if re.search(r"<w:lang\b[^>]*/>", inner):
            inner = re.sub(r"<w:lang\b[^>]*/>", lambda _: lang, inner, count=1)
        elif "<w:rPr>" in inner:
            inner = inner.replace("<w:rPr>", "<w:rPr>" + lang, 1)
        elif "<w:rPr/>" in inner:
            inner = inner.replace("<w:rPr/>", "<w:rPr>" + lang + "</w:rPr>", 1)
        else:
            inner = "<w:rPr>" + lang + "</w:rPr>" + inner
        return xml[:m.start(1)] + inner + xml[m.end(1):]
    block = "<w:rPrDefault><w:rPr>" + lang + "</w:rPr></w:rPrDefault>"
    if "<w:docDefaults>" in xml:
        return xml.replace("<w:docDefaults>", "<w:docDefaults>" + block, 1)
    if "<w:docDefaults/>" in xml:
        return xml.replace("<w:docDefaults/>", "<w:docDefaults>" + block + "</w:docDefaults>", 1)
    m = re.search(r"<w:styles\b[^>]*>", xml)
    if not m:
        return xml
    return xml[:m.end()] + "<w:docDefaults>" + block + "</w:docDefaults>" + xml[m.end():]


def set_properties(path, title, language):
    with zipfile.ZipFile(path) as z:
        items = [(info, z.read(info.filename)) for info in z.infolist()]
    names = {info.filename for info, _ in items}
    out = []
    for info, data in items:
        if info.filename == "docProps/core.xml":
            text = data.decode("utf-8")
            data = _set_tag(_set_tag(text, "dc:title", title), "dc:language", language).encode("utf-8")
        elif info.filename == "word/styles.xml":
            data = _set_style_lang(data.decode("utf-8"), language).encode("utf-8")
        elif info.filename == "[Content_Types].xml" and "docProps/core.xml" not in names:
            text = data.decode("utf-8")
            if "/docProps/core.xml" not in text:
                text = text.replace("</Types>", '<Override PartName="/docProps/core.xml" ContentType="%s"/></Types>' % CORE_TYPE, 1)
            data = text.encode("utf-8")
        elif info.filename == "_rels/.rels" and "docProps/core.xml" not in names:
            text = data.decode("utf-8")
            if "core-properties" not in text:
                text = text.replace("</Relationships>", '<Relationship Id="rIdLmCore" Type="%s" Target="docProps/core.xml"/>'
                                    "</Relationships>" % CORE_REL, 1)
            data = text.encode("utf-8")
        out.append((info, data))
    if "docProps/core.xml" not in names:
        out.append((zipfile.ZipInfo("docProps/core.xml"), _core_xml(title, language).encode("utf-8")))
    tmp = path + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for info, data in out:
            z.writestr(info.filename, data)
    os.replace(tmp, path)
