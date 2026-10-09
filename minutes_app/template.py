import os
import re
import zipfile
from xml.sax.saxutils import escape

from .accessibility import contrast
from .config import zm


def read_upload_topics(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".docx":
        doc = zm.Minutes(path)
        lines = [zm.para_text(p) for p in doc.paras()]
    elif ext == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            raise ValueError("PDF uploads need the pypdf package (pip install pypdf), "
                             "or save the agenda as .docx or .txt instead.")
        lines = []
        for page in PdfReader(path).pages:
            lines += (page.extract_text() or "").splitlines()
    elif ext in (".txt", ".md"):
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    else:
        raise ValueError("unsupported file type " + ext + " (use .docx, .pdf, .txt or .md)")
    topics = []
    for line in lines:
        s = re.sub(r"^\s*(?:[-*•●]|\d+[.)]|[a-zA-Z][.)])\s*", "", line).strip()
        if len(s) >= 3 and not re.fullmatch(r"(page \d+|\d+)", s, re.I):
            topics.append(s)
    return topics


def prepare(upload_path, out_dir, title="Meeting Minutes", date_text=""):
    if upload_path.lower().endswith(".docx"):
        doc = zm.Minutes(upload_path)
        items = [p for p in doc.paras() if doc.is_agenda_item(p) and zm.para_text(p).strip()]
        if len(items) >= 2:
            return upload_path, "template"
    topics = read_upload_topics(upload_path)
    if not topics:
        raise ValueError("no topics or agenda items found in the upload")
    out = os.path.join(out_dir, "generated-template.docx")
    generate(topics, out, title=title, date_text=date_text)
    return out, "generated"


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
ACCENT = "1F3A5F"
TEXT_WIDTH = 9720
INK = "1F2328"
MUTED = "595959"


FONTS = ("Calibri", "Aptos", "Arial", "Georgia", "Times New Roman", "Garamond", "Cambria", "Verdana")
ALIGN = ("left", "center", "right")
NUMBERING = {"decimal": ("decimal", "%1."), "roman": ("upperRoman", "%1."), "letter": ("upperLetter", "%1."),
             "lower": ("lowerLetter", "%1)")}
HEADINGS = ("rule", "band", "plain", "caps", "tint")
TITLE_BLOCKS = ("classic", "banner", "masthead")
STYLE = {"font": "Calibri", "accent": "1F3A5F", "title_align": "left", "subtitle_align": "left", "date_align": "left",
         "heading_align": "left", "heading_style": "rule", "numbering": "decimal", "title_size": 20, "body_size": 11,
         "bold_items": True, "title_rule": False, "title_block": "classic", "section_numbers": False,
         "accent_numbers": False}
LABELS = {"date_label": "Date:", "first_item": "Call to Order", "opening_line": "Meeting called to order at .",
          "last_item": "Adjournment", "attendance_heading": "Attendance", "present_label": "Present:",
          "absent_label": "Absent:", "agenda_heading": "Agenda", "action_heading": "Action Items",
          "summary_heading": "Summary", "summary_lead": "Key Items Discussed/Actions Taken",
          "details_date": "Date", "details_start": "Called to order", "details_end": "Adjourned",
          "details_place": "Location", "approval_heading": "Approval", "sign_first": "Recording secretary",
          "sign_second": "Presiding officer"}
SECTIONS = {"attendance": True, "action_items": True, "summary": True, "details": False, "signatures": False,
            "footer": False}
FIELDS = ("lm_date", "lm_start", "lm_end", "lm_place")


def _hex(value, fallback):
    v = str(value or "").strip().lstrip("#").upper()
    return v if re.fullmatch(r"[0-9A-F]{6}", v) else fallback


def _text(value, fallback, limit=160):
    v = " ".join(str(value if value is not None else "").split())[:limit]
    return v if v else fallback


def _lines(value, limit=600):
    lines = (" ".join(line.split()) for line in str(value or "").splitlines())
    return "\n".join(line for line in lines if line)[:limit]


def tint(hex6, amount=0.12):
    r, g, b = (int(hex6[i:i + 2], 16) for i in (0, 2, 4))
    return "%02X%02X%02X" % tuple(round(255 - (255 - c) * amount) for c in (r, g, b))


def ink_on(fill):
    return "FFFFFF" if contrast("FFFFFF", fill) >= 4.5 else INK


def readable(color, fill):
    return color if contrast(color, fill) >= 4.5 else INK


def normalize(design):
    d = dict(design or {})
    st = dict(STYLE)
    st.update({k: v for k, v in (d.get("style") or {}).items() if k in STYLE})
    st["font"] = st["font"] if st["font"] in FONTS else STYLE["font"]
    for k in ("title_align", "subtitle_align", "date_align"):
        st[k] = st[k] if st[k] in ALIGN else "left"
    st["heading_align"] = st["heading_align"] if st["heading_align"] in ALIGN else "left"
    st["heading_style"] = st["heading_style"] if st["heading_style"] in HEADINGS else "rule"
    st["title_block"] = st["title_block"] if st["title_block"] in TITLE_BLOCKS else "classic"
    st["numbering"] = st["numbering"] if st["numbering"] in NUMBERING else "decimal"
    st["accent"] = _hex(st["accent"], STYLE["accent"])
    try:
        st["title_size"] = max(14, min(40, int(st["title_size"])))
        st["body_size"] = max(9, min(16, int(st["body_size"])))
    except (TypeError, ValueError):
        st["title_size"], st["body_size"] = STYLE["title_size"], STYLE["body_size"]
    for k in ("bold_items", "title_rule", "section_numbers", "accent_numbers"):
        st[k] = bool(st[k])
    out = {"title": _text(d.get("title"), "Meeting Minutes", 200), "subtitle": _text(d.get("subtitle"), "", 200),
           "topics": clean_topics(d.get("topics") or []), "style": st}
    for k, v in SECTIONS.items():
        out[k] = bool(d.get(k, v))
    for k, v in LABELS.items():
        out[k] = _text(d.get(k), v)
    out["intro"], out["closing"] = _lines(d.get("intro")), _lines(d.get("closing"))
    if "called to order at" not in out["opening_line"].lower():
        out["opening_line"] = LABELS["opening_line"]
    return out


def _run(text, bold=False, unbold=False, caps=False, color=None, spacing=None, size=None):
    if not text:
        return ""
    rpr = ("<w:b/>" if bold else '<w:b w:val="0"/>' if unbold else "") + ("<w:caps/>" if caps else "")
    if color:
        rpr += '<w:color w:val="%s"/>' % color
    if spacing:
        rpr += '<w:spacing w:val="%d"/>' % spacing
    if size:
        rpr += '<w:sz w:val="%d"/><w:szCs w:val="%d"/>' % (size, size)
    return '<w:r>%s<w:t xml:space="preserve">%s</w:t></w:r>' % ("<w:rPr>%s</w:rPr>" % rpr if rpr else "", escape(text))


def _p(text, style=None, num=None, ilvl=0, indent=None, bold=False, color=None, size=None, align=None, border="",
       shade=None, spacing="", runs=None, after="", right=None, keep=False):
    ppr = ""
    if style:
        ppr += '<w:pStyle w:val="%s"/>' % style
    if keep:
        ppr += "<w:keepNext/>"
    if num:
        ppr += '<w:numPr><w:ilvl w:val="%d"/><w:numId w:val="%s"/></w:numPr>' % (ilvl, num)
    ppr += border
    if shade:
        ppr += '<w:shd w:val="clear" w:color="auto" w:fill="%s"/>' % shade
    ppr += spacing
    if indent is not None or right is not None:
        ppr += "<w:ind%s%s/>" % (' w:left="%d"' % indent if indent is not None else "",
                                 ' w:right="%d"' % right if right is not None else "")
    if align and align != "left":
        ppr += '<w:jc w:val="%s"/>' % align
    body = "".join(runs) if runs is not None else _run(text, bold=bold, color=color, size=size)
    return "<w:p>%s%s%s</w:p>" % ("<w:pPr>%s</w:pPr>" % ppr if ppr else "", body, after)


def _box(color, space):
    side = '<w:%s w:val="single" w:sz="4" w:space="%d" w:color="%s"/>'
    return "<w:pBdr>%s</w:pBdr>" % "".join(side % (s, space, color) for s in ("top", "left", "bottom", "right"))


def _cell(width, content, fill=None):
    shd = '<w:shd w:val="clear" w:color="auto" w:fill="%s"/>' % fill if fill else ""
    return '<w:tc><w:tcPr><w:tcW w:w="%d" w:type="dxa"/>%s</w:tcPr>%s</w:tc>' % (width, shd, content)


FIXED = {"call to order", "adjournment", "adjourn", "meeting adjourned"}


def clean_topics(topics, limit=60, fixed=()):
    skip = FIXED | {f.lower().rstrip(".:") for f in fixed}
    out, seen = [], set()
    for topic in topics:
        text = " ".join(str(topic).split())[:120]
        key = text.lower().rstrip(".:")
        if len(text) < 2 or key in skip or key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out[:limit]


def _title_block(d, st, date_text, mark):
    accent, block = st["accent"], st["title_block"]
    out = []
    if block == "banner":
        ink, frame = ink_on(accent), _box(accent, 10)
        out.append(_p("", style="Title", border=frame, shade=accent, indent=220, right=220, align=st["title_align"],
                      spacing='<w:spacing w:after="0"/>', runs=[_run(d["title"], color=ink)]))
        if d["subtitle"]:
            out.append(_p("", style="Subtitle", border=frame, shade=accent, indent=220, right=220,
                          align=st["subtitle_align"], spacing='<w:spacing w:after="0"/>',
                          runs=[_run(d["subtitle"], color=ink)]))
        out.append(_p("", spacing='<w:spacing w:after="60"/>'))
    else:
        border = ""
        if block == "masthead":
            rule = ('<w:bottom w:val="single" w:sz="8" w:space="6" w:color="%s"/>' % accent) if st["title_rule"] else ""
            border = '<w:pBdr><w:top w:val="single" w:sz="36" w:space="12" w:color="%s"/>%s</w:pBdr>' % (accent, rule)
        out.append(_p(d["title"], style="Title", align=st["title_align"], border=border))
        if d["subtitle"]:
            out.append(_p("", style="Subtitle", align=st["subtitle_align"],
                          runs=[_run(d["subtitle"], caps=block == "masthead", spacing=20 if block == "masthead" else None)]))
    out += [_p(line, color="444444", align=st["subtitle_align"]) for line in d["intro"].splitlines()]
    if not d["details"]:
        if date_text:
            out.append(_p(date_text, color="555555", align=st["date_align"]))
        else:
            out.append(_p("", align=st["date_align"], runs=[_run(d["date_label"] + " ", color="555555")],
                          after=mark("lm_date")))
    return out


def _details(d, st, mark):
    accent = st["accent"]
    width = TEXT_WIDTH // 4
    cols = [(d["details_date"], "lm_date"), (d["details_start"], "lm_start"), (d["details_end"], "lm_end"),
            (d["details_place"], "lm_place")]
    line = '<w:%s w:val="single" w:sz="%d" w:space="0" w:color="%s"/>'
    borders = "<w:tblBorders>%s%s%s</w:tblBorders>" % (line % ("top", 8, accent), line % ("bottom", 8, accent),
                                                       line % ("insideH", 4, tint(accent, 0.3)))
    fill = tint(accent, 0.1)
    label = readable(MUTED, fill)
    gap = '<w:spacing w:before="60" w:after="60"/>'
    heads = "".join(_cell(width, _p("", spacing=gap, runs=[_run(text, bold=True, caps=True, color=label, spacing=10,
                                                                    size=18)]), fill) for text, _ in cols)
    values = "".join(_cell(width, _p("", spacing=gap, after=mark(name))) for _, name in cols)
    return ('<w:tbl><w:tblPr><w:tblW w:w="%d" w:type="dxa"/>%s<w:tblLayout w:type="fixed"/>'
            '<w:tblCellMar><w:left w:w="100" w:type="dxa"/><w:right w:w="100" w:type="dxa"/></w:tblCellMar>'
            '<w:tblCaption w:val="Meeting details"/></w:tblPr><w:tblGrid>%s</w:tblGrid>'
            '<w:tr><w:trPr><w:tblHeader/></w:trPr>%s</w:tr><w:tr>%s</w:tr></w:tbl>') % (
        TEXT_WIDTH, borders, '<w:gridCol w:w="%d"/>' % width * 4, heads, values)


def generate(topics, out_path, title="Meeting Minutes", date_text="", attendance=True, action_items=True, summary=True,
             design=None):
    d = normalize(dict(design or {}, topics=topics, title=title, attendance=attendance, action_items=action_items,
                       summary=summary) if design is None else design)
    st = d["style"]
    accent = st["accent"]
    topics = clean_topics(d["topics"], fixed=(d["first_item"], d["last_item"]))
    bold = st["bold_items"]
    ids = iter(range(1, 100))

    def mark(name):
        n = next(ids)
        return '<w:bookmarkStart w:id="%d" w:name="%s"/><w:bookmarkEnd w:id="%d"/>' % (n, name, n)

    count = [0]
    number_color = (None if st["heading_style"] == "band" else
                    readable(accent, tint(accent, 0.12)) if st["heading_style"] == "tint" else accent)

    def heading(text):
        if not st["section_numbers"]:
            return _p(text, style="Heading1")
        count[0] += 1
        return _p("", style="Heading1", runs=[_run("%02d" % count[0], unbold=True, color=number_color), _run("   " + text)])

    body = _title_block(d, st, date_text, mark)
    if d["details"]:
        body.append(_details(d, st, mark))
    if d["attendance"]:
        body += [heading(d["attendance_heading"]), _p(d["present_label"] + " ", num="2", indent=720),
                 _p(d["absent_label"] + " ", num="2", indent=720)]
    body += [heading(d["agenda_heading"]),
             _p(d["first_item"], num="1", indent=360, bold=bold),
             _p(d["opening_line"], num="2", indent=720)]
    for topic in topics:
        body.append(_p(topic, num="1", indent=360, bold=bold))
        body.append(_p("", num="2", indent=720))
    body.append(_p(d["last_item"], num="1", indent=360, bold=bold))
    if d["action_items"]:
        body += [heading(d["action_heading"]), _p("", num="2", indent=720)]
    if d["summary"]:
        body += [heading(d["summary_heading"]), _p(d["summary_lead"], style="LMSummary", bold=True)]
    if d["signatures"]:
        body.append(heading(d["approval_heading"]))
        for who in (d["sign_first"], d["sign_second"]):
            body.append(_p("", keep=True, border='<w:pBdr><w:bottom w:val="single" w:sz="6" w:space="1" w:color="7F7F7F"/></w:pBdr>',
                           spacing='<w:spacing w:before="520" w:after="40"/>', right=4860))
            body.append(_p("", runs=[_run(who, bold=True, size=20), _run("   Signature and date", color=MUTED, size=19)]))
    body += [_p(line, color="444444", spacing='<w:spacing w:before="160"/>' if n == 0 else "")
             for n, line in enumerate(d["closing"].splitlines())]
    footer_ref = '<w:footerReference w:type="default" r:id="rId3"/>' if d["footer"] else ""
    document = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
                '<w:document xmlns:w="%s" xmlns:r="%s"><w:body>%s'
                '<w:sectPr>%s<w:pgSz w:w="12240" w:h="15840"/>'
                '<w:pgMar w:top="1260" w:right="1260" w:bottom="1260" w:left="1260" w:header="720" w:footer="560" w:gutter="0"/>'
                '</w:sectPr></w:body></w:document>') % (W_NS, R_NS, "".join(body), footer_ref)

    font = escape(st["font"])
    jc = '<w:jc w:val="%s"/>' % st["heading_align"] if st["heading_align"] != "left" else ""
    head_border = head_shd = head_ind = ""
    if st["heading_style"] == "band":
        head_shd = '<w:shd w:val="clear" w:color="auto" w:fill="%s"/>' % accent
        head_ind = '<w:ind w:left="0"/>'
        head_rpr = '<w:b/><w:color w:val="%s"/><w:sz w:val="24"/>' % ink_on(accent)
    elif st["heading_style"] == "tint":
        fill = tint(accent, 0.12)
        head_border = '<w:pBdr><w:left w:val="single" w:sz="24" w:space="6" w:color="%s"/></w:pBdr>' % accent
        head_shd = '<w:shd w:val="clear" w:color="auto" w:fill="%s"/>' % fill
        head_ind = '<w:ind w:left="160"/>'
        head_rpr = '<w:b/><w:color w:val="%s"/><w:sz w:val="24"/>' % readable(accent, fill)
    elif st["heading_style"] == "plain":
        head_rpr = '<w:b/><w:color w:val="%s"/><w:sz w:val="26"/>' % accent
    elif st["heading_style"] == "caps":
        head_rpr = '<w:b/><w:caps/><w:color w:val="%s"/><w:spacing w:val="20"/><w:sz w:val="22"/>' % accent
    else:
        head_border = '<w:pBdr><w:bottom w:val="single" w:sz="6" w:space="2" w:color="%s"/></w:pBdr>' % accent
        head_rpr = '<w:b/><w:color w:val="%s"/><w:sz w:val="26"/>' % accent
    title_border = ('<w:pBdr><w:bottom w:val="single" w:sz="12" w:space="4" w:color="%s"/></w:pBdr>' % accent
                    if st["title_rule"] and st["title_block"] == "classic" else "")
    styles = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
              '<w:styles xmlns:w="%(ns)s">'
              '<w:docDefaults><w:rPrDefault><w:rPr>'
              '<w:rFonts w:ascii="%(font)s" w:hAnsi="%(font)s" w:cs="%(font)s"/>'
              '<w:sz w:val="%(body)d"/><w:szCs w:val="%(body)d"/></w:rPr></w:rPrDefault>'
              '<w:pPrDefault><w:pPr><w:spacing w:after="80" w:line="276" w:lineRule="auto"/></w:pPr></w:pPrDefault>'
              '</w:docDefaults>'
              '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
              '<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/>'
              '<w:pPr>%(title_border)s<w:spacing w:after="40"/></w:pPr>'
              '<w:rPr><w:b/><w:color w:val="%(accent)s"/><w:sz w:val="%(title)d"/></w:rPr></w:style>'
              '<w:style w:type="paragraph" w:styleId="Subtitle"><w:name w:val="Subtitle"/><w:basedOn w:val="Normal"/>'
              '<w:pPr><w:spacing w:after="40"/></w:pPr><w:rPr><w:color w:val="444444"/><w:sz w:val="%(sub)d"/></w:rPr></w:style>'
              '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/>'
              '<w:pPr><w:keepNext/>%(head_border)s%(head_shd)s<w:spacing w:before="280" w:after="80"/>%(head_ind)s%(jc)s'
              '<w:outlineLvl w:val="0"/></w:pPr><w:rPr>%(head_rpr)s</w:rPr></w:style>'
              '<w:style w:type="paragraph" w:customStyle="1" w:styleId="LMSummary"><w:name w:val="Summary lead"/>'
              '<w:basedOn w:val="Normal"/><w:rPr><w:b/></w:rPr></w:style>'
              '</w:styles>') % {"ns": W_NS, "font": font, "body": st["body_size"] * 2, "accent": accent,
                                "title": st["title_size"] * 2, "sub": st["body_size"] * 2 + 2, "head_border": head_border,
                                "head_shd": head_shd, "head_ind": head_ind, "head_rpr": head_rpr, "jc": jc,
                                "title_border": title_border}

    fmt, text = NUMBERING[st["numbering"]]
    number_rpr = '<w:rPr><w:b/><w:color w:val="%s"/></w:rPr>' % accent if st["accent_numbers"] else ""
    numbering = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
                 '<w:numbering xmlns:w="%s">'
                 '<w:abstractNum w:abstractNumId="0"><w:multiLevelType w:val="multilevel"/>'
                 '<w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="%s"/><w:lvlText w:val="%s"/>'
                 '<w:lvlJc w:val="left"/><w:pPr><w:ind w:left="360" w:hanging="360"/></w:pPr>%s</w:lvl>'
                 '<w:lvl w:ilvl="1"><w:start w:val="1"/><w:numFmt w:val="decimal"/><w:lvlText w:val="%%1.%%2."/>'
                 '<w:lvlJc w:val="left"/><w:pPr><w:ind w:left="1080" w:hanging="540"/></w:pPr></w:lvl>'
                 '</w:abstractNum>'
                 '<w:abstractNum w:abstractNumId="1"><w:multiLevelType w:val="hybridMultilevel"/>'
                 '<w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="bullet"/><w:lvlText w:val="•"/>'
                 '<w:lvlJc w:val="left"/><w:pPr><w:ind w:left="720" w:hanging="360"/></w:pPr></w:lvl>'
                 '<w:lvl w:ilvl="1"><w:start w:val="1"/><w:numFmt w:val="bullet"/><w:lvlText w:val="◦"/>'
                 '<w:lvlJc w:val="left"/><w:pPr><w:ind w:left="1440" w:hanging="360"/></w:pPr></w:lvl>'
                 '</w:abstractNum>'
                 '<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>'
                 '<w:num w:numId="2"><w:abstractNumId w:val="1"/></w:num>'
                 '</w:numbering>') % (W_NS, fmt, text, number_rpr)

    footer_type = ('<Override PartName="/word/footer1.xml" '
                   'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>'
                   if d["footer"] else "")
    ctypes = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
              '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
              '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
              '<Default Extension="xml" ContentType="application/xml"/>'
              '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
              '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
              '<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>'
              '%s</Types>') % footer_type
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            '</Relationships>')
    footer_rel = ('<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" '
                  'Target="footer1.xml"/>' if d["footer"] else "")
    doc_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>'
                '%s</Relationships>') % footer_rel
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ctypes)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/_rels/document.xml.rels", doc_rels)
        z.writestr("word/document.xml", document)
        z.writestr("word/styles.xml", styles)
        z.writestr("word/numbering.xml", numbering)
        if d["footer"]:
            z.writestr("word/footer1.xml", _footer(d["title"], accent))
    return out_path


def _footer(title, accent):
    small = '<w:rPr><w:color w:val="%s"/><w:sz w:val="18"/><w:szCs w:val="18"/></w:rPr>' % MUTED

    def field(code):
        return '<w:fldSimple w:instr=" %s "><w:r>%s<w:t>1</w:t></w:r></w:fldSimple>' % (code, small)
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
            '<w:ftr xmlns:w="%s"><w:p><w:pPr><w:pBdr><w:top w:val="single" w:sz="4" w:space="6" w:color="%s"/></w:pBdr>'
            '<w:tabs><w:tab w:val="right" w:pos="%d"/></w:tabs><w:spacing w:after="0"/></w:pPr>'
            '<w:r>%s<w:t xml:space="preserve">%s</w:t></w:r><w:r>%s<w:tab/><w:t xml:space="preserve">Page </w:t></w:r>%s'
            '<w:r>%s<w:t xml:space="preserve"> of </w:t></w:r>%s</w:p></w:ftr>') % (
        W_NS, tint(accent, 0.45), TEXT_WIDTH, small, escape(title), small, field("PAGE"), small, field("NUMPAGES"))


def read_text(path, limit=12000):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".docx":
        doc = zm.Minutes(path)
        lines = [zm.para_text(p) for p in doc.paras()]
    elif ext == ".pdf":
        from pypdf import PdfReader
        lines = []
        for page in PdfReader(path).pages:
            lines += (page.extract_text() or "").splitlines()
    elif ext in (".txt", ".md"):
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    else:
        raise ValueError("unsupported file type " + ext)
    text = "\n".join(line.rstrip() for line in lines if line.strip())
    return text[:limit]


BUILTIN = {
    "student-government": {
        "name": "Student government (formal)",
        "description": "Centered masthead, Roman numerals, a meeting details table, and signature lines for an official senate or ASG record.",
        "topics": ["Roll Call", "Approval of the Agenda", "Approval of the Previous Minutes", "Public Comment",
                   "Officer Reports", "Advisor Report", "Unfinished Business", "New Business", "Announcements"],
        "design": {"subtitle": "Regular Meeting", "details": True, "signatures": True, "footer": True,
                   "style": {"font": "Times New Roman", "title_align": "center", "subtitle_align": "center",
                             "date_align": "center", "heading_style": "caps", "numbering": "roman", "title_rule": True,
                             "title_block": "masthead", "accent": "1F3A5F"}}},
    "modern": {
        "name": "Modern team meeting",
        "description": "A color banner title, tinted section headings, and a details strip, in a clean sans-serif.",
        "topics": ["Check-in", "Updates", "Discussion", "Decisions"],
        "design": {"first_item": "Start of meeting", "last_item": "Wrap-up", "agenda_heading": "Meeting notes",
                   "action_heading": "Next steps and owners", "summary_heading": "At a glance",
                   "summary_lead": "Key Items Discussed/Actions Taken", "details": True, "footer": True,
                   "details_start": "Started", "details_end": "Ended",
                   "style": {"font": "Aptos", "heading_style": "tint", "accent": "2B6CB0", "title_size": 24,
                             "bold_items": True, "title_block": "banner", "accent_numbers": True}}},
    "club": {
        "name": "Club meeting (simple)",
        "description": "Friendly notes without roll call, with a bold masthead and colored agenda numbers, for clubs and interest groups.",
        "topics": ["Officer Updates", "Events and Activities", "Budget and Funding", "Member Ideas", "Announcements"],
        "design": {"first_item": "Welcome", "last_item": "Closing", "attendance": False, "details": True,
                   "details_start": "Started", "details_end": "Ended",
                   "style": {"font": "Arial", "heading_style": "plain", "accent": "2F855A", "title_block": "masthead",
                             "accent_numbers": True, "title_size": 24}}},
    "committee": {
        "name": "Committee working session",
        "description": "Numbered sections and a lettered agenda that starts from last meeting's action items and ends with assignments.",
        "topics": ["Review of Last Meeting's Action Items", "Discussion Items", "Decisions", "Assignments", "Next Meeting"],
        "design": {"action_heading": "Assignments and due dates", "details": True, "footer": True,
                   "style": {"font": "Calibri", "heading_style": "rule", "numbering": "letter", "accent": "6B46C1",
                             "section_numbers": True, "accent_numbers": True}}},
    "board": {
        "name": "Board or senate (Robert's Rules)",
        "description": "Traditional parliamentary order with quorum, reports, open forum, and approval signatures, in a classic serif.",
        "topics": ["Roll Call and Quorum", "Approval of the Agenda", "Approval of the Minutes", "Public Comment",
                   "Reports of Officers", "Reports of Committees", "Unfinished Business", "New Business", "Open Forum",
                   "Announcements"],
        "design": {"subtitle": "Minutes of the Regular Meeting", "present_label": "Members present:",
                   "absent_label": "Members absent:", "details": True, "signatures": True, "footer": True,
                   "sign_second": "Chair",
                   "style": {"font": "Garamond", "title_align": "center", "subtitle_align": "center",
                             "date_align": "center", "heading_style": "caps", "heading_align": "center",
                             "numbering": "roman", "title_rule": True, "accent": "7B2D26", "title_size": 22}}},
    "special": {
        "name": "Special meeting",
        "description": "Short record for a meeting called about one item, with public comment, the vote, and signatures.",
        "topics": ["Public Comment on Agenda Items", "Item for Consideration", "Vote"],
        "design": {"subtitle": "Special Meeting", "action_items": False, "details": True, "signatures": True,
                   "style": {"font": "Georgia", "title_align": "center", "subtitle_align": "center",
                             "heading_style": "plain", "accent": "1F3A5F", "title_rule": True}}},
    "brief": {
        "name": "One-page brief",
        "description": "Compact summary-first notes for quick check-ins, with a slim masthead and small-caps headings.",
        "topics": ["Highlights", "Decisions", "Open Questions"],
        "design": {"attendance": False, "agenda_heading": "Notes",
                   "style": {"font": "Verdana", "heading_style": "caps", "body_size": 10, "title_size": 18,
                             "accent": "C05621", "bold_items": False, "title_block": "masthead"}}},
    "executive": {
        "name": "Executive board meeting",
        "description": "Editorial layout with numbered sections, officer reports, a details table, and approval signatures.",
        "topics": ["Approval of the Previous Minutes", "President's Report", "Treasurer's Report", "Committee Updates",
                   "Old Business", "New Business", "Officer Announcements"],
        "design": {"subtitle": "Executive Board", "details": True, "signatures": True, "footer": True,
                   "sign_second": "President",
                   "style": {"font": "Cambria", "heading_style": "caps", "accent": "0F4C5C", "title_block": "masthead",
                             "section_numbers": True, "accent_numbers": True, "title_size": 26}}},
    "finance": {
        "name": "Finance committee",
        "description": "Budget reports, funding requests, and allocation votes under tinted headings, with signatures for the record.",
        "topics": ["Treasurer's Report", "Budget Overview", "Funding Requests", "Budget Transfers",
                   "Allocations and Votes", "Audit and Compliance"],
        "design": {"subtitle": "Finance Committee", "details": True, "signatures": True, "footer": True,
                   "sign_first": "Treasurer", "sign_second": "Committee chair",
                   "action_heading": "Follow-ups and deadlines",
                   "style": {"font": "Calibri", "heading_style": "tint", "accent": "2F5D3A", "accent_numbers": True,
                             "title_size": 24}}},
    "event": {
        "name": "Event planning",
        "description": "A bright banner and tinted headings for planning an event, from venue and budget to volunteers and deadlines.",
        "topics": ["Event Overview", "Venue and Logistics", "Budget and Purchases", "Marketing and Outreach",
                   "Volunteers and Roles", "Timeline and Deadlines"],
        "design": {"subtitle": "Event Planning Meeting", "first_item": "Welcome", "last_item": "Closing",
                   "action_heading": "Tasks, owners, and due dates", "details": True,
                   "details_start": "Started", "details_end": "Ended",
                   "style": {"font": "Verdana", "heading_style": "tint", "accent": "9D174D", "title_block": "banner",
                             "accent_numbers": True, "body_size": 10, "title_size": 24}}},
    "project": {
        "name": "Project status update",
        "description": "Banner title, numbered sections, and a details strip for weekly project or team check-ins.",
        "topics": ["Wins Since Last Meeting", "Progress by Workstream", "Risks and Blockers", "Decisions Needed",
                   "Next Milestones"],
        "design": {"subtitle": "Status Update", "first_item": "Start of meeting", "last_item": "Wrap-up",
                   "agenda_heading": "Discussion", "action_heading": "Next steps and owners",
                   "summary_heading": "At a glance", "details": True, "footer": True,
                   "details_start": "Started", "details_end": "Ended",
                   "style": {"font": "Aptos", "heading_style": "rule", "accent": "334155", "title_block": "banner",
                             "section_numbers": True, "accent_numbers": True, "title_size": 24}}},
    "one-on-one": {
        "name": "One-on-one check-in",
        "description": "A calm, minimal layout for one-on-ones and mentoring: wins, priorities, support, feedback, and goals.",
        "topics": ["Wins and Highlights", "Current Priorities", "Challenges and Support Needed", "Feedback",
                   "Goals and Growth"],
        "design": {"first_item": "Check-in", "last_item": "Next steps", "attendance": False, "agenda_heading": "Notes",
                   "action_heading": "Commitments", "summary_heading": "Takeaways", "details": True,
                   "details_start": "Started", "details_end": "Ended",
                   "style": {"font": "Georgia", "heading_style": "plain", "accent": "5B21B6", "title_block": "masthead",
                             "accent_numbers": True, "title_size": 24}}},
}


def preset(key, title):
    b = BUILTIN[key]
    return normalize(dict(b["design"], title=title, topics=b["topics"]))
