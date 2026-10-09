#!/usr/bin/env python3

import argparse
import base64
import io
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import date, datetime, timedelta
from xml.etree import ElementTree as ET

try:
    from defusedxml.ElementTree import fromstring as parse_xml
except ImportError:
    parse_xml = ET.XML

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
TOKEN_CACHE = os.path.join(HERE, ".zoom_token.json")
API = "https://api.zoom.us/v2"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"


def load_dotenv():
    path = os.path.join(HERE, ".env")
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


class MinutesError(ValueError):
    pass


def die(msg, code=1):
    print("error: " + msg, file=sys.stderr)
    sys.exit(code)


def need(key):
    val = os.environ.get(key)
    if not val:
        die(key + " is not set. Put it in the environment or in "
            + os.path.join(HERE, ".env")
            + "\nSee README.md for how to create the Zoom Server-to-Server OAuth app.")
    return val


class ZoomError(Exception):
    def __init__(self, status, detail):
        self.status = status
        self.detail = detail
        super().__init__("HTTP {0}: {1}".format(status, detail))


def _request(url, headers=None, data=None, method="GET", raw=False, timeout=120):
    req = urllib.request.Request(url, data=data, method=method)
    for key, val in (headers or {}).items():
        req.add_header(key, val)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            return body if raw else json.loads(body.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:600]
        raise ZoomError(exc.code, detail) from None


def get_token(force=False):
    if not force and os.path.exists(TOKEN_CACHE):
        try:
            with open(TOKEN_CACHE, "r", encoding="utf-8") as fh:
                cached = json.load(fh)
            if cached.get("expires_at", 0) > time.time() + 120:
                return cached["access_token"]
        except (json.JSONDecodeError, KeyError, OSError):
            pass

    account_id = need("ZOOM_ACCOUNT_ID")
    client_id = need("ZOOM_CLIENT_ID")
    client_secret = need("ZOOM_CLIENT_SECRET")

    basic = base64.b64encode((client_id + ":" + client_secret).encode()).decode()
    url = "https://zoom.us/oauth/token?" + urllib.parse.urlencode(
        {"grant_type": "account_credentials", "account_id": account_id})
    payload = _request(
        url,
        headers={"Authorization": "Basic " + basic,
                 "Content-Type": "application/x-www-form-urlencoded"},
        data=b"",
        method="POST")

    token = payload["access_token"]
    with open(TOKEN_CACHE, "w", encoding="utf-8") as fh:
        json.dump({"access_token": token,
                   "expires_at": time.time() + int(payload.get("expires_in", 3600))}, fh)
    try:
        os.chmod(TOKEN_CACHE, 0o600)
    except OSError:
        pass
    return token


def api_get(path, params=None):
    url = API + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    try:
        return _request(url, headers={"Authorization": "Bearer " + get_token()})
    except ZoomError as exc:
        if exc.status == 401:
            return _request(url, headers={"Authorization": "Bearer " + get_token(force=True)})
        raise


def list_recordings(user_id, start, end):
    meetings = []
    window_start = start
    while window_start <= end:
        window_end = min(window_start + timedelta(days=29), end)
        page_token = ""
        while True:
            params = {"from": window_start.isoformat(),
                      "to": window_end.isoformat(),
                      "page_size": 300}
            if page_token:
                params["next_page_token"] = page_token
            payload = api_get("/users/" + user_id + "/recordings", params)
            meetings.extend(payload.get("meetings", []))
            page_token = payload.get("next_page_token") or ""
            if not page_token:
                break
        window_start = window_end + timedelta(days=1)
    meetings.sort(key=lambda m: m.get("start_time", ""))
    return meetings


def transcript_file(meeting):
    for rec in meeting.get("recording_files", []):
        if rec.get("file_type") == "TRANSCRIPT" or rec.get("recording_type") == "audio_transcript":
            return rec
    return None


def download(rec):
    url = rec["download_url"]
    try:
        return _request(url, headers={"Authorization": "Bearer " + get_token()}, raw=True)
    except ZoomError:
        dl = rec.get("download_access_token")
        if not dl:
            raise
        sep = "&" if "?" in url else "?"
        return _request(url + sep + "access_token=" + dl, raw=True)


def meeting_summary(uuid):
    once = urllib.parse.quote(uuid, safe="")
    encoded = urllib.parse.quote(once, safe="") if (uuid.startswith("/") or "//" in uuid) else once
    try:
        return api_get("/meetings/" + encoded + "/meeting_summary")
    except ZoomError as exc:
        print("note: no AI Companion summary available (HTTP {0}). "
              "Continuing with the transcript alone.".format(exc.status), file=sys.stderr)
        return None


TS = re.compile(r"(\d{1,2}:)?(\d{2}):(\d{2})[.,](\d{3})")


def parse_ts(text):
    match = TS.search(text)
    if not match:
        return 0.0
    hours = int((match.group(1) or "0:").rstrip(":"))
    return (hours * 3600 + int(match.group(2)) * 60
            + int(match.group(3)) + int(match.group(4)) / 1000.0)


def hhmmss(seconds):
    seconds = int(seconds)
    return "{0}:{1:02d}:{2:02d}".format(seconds // 3600, (seconds % 3600) // 60, seconds % 60)


def parse_vtt(text):
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    cues = []
    for block in text.split("\n\n"):
        lines = [ln for ln in block.strip().split("\n") if ln.strip()]
        if not lines or lines[0].startswith("WEBVTT"):
            continue
        timing_at = next((i for i, ln in enumerate(lines) if "-->" in ln), None)
        if timing_at is None:
            continue
        left, _, right = lines[timing_at].partition("-->")
        body = " ".join(lines[timing_at + 1:]).strip()
        if not body:
            continue
        speaker, said = "", body
        match = re.match(r"^([^:]{1,60}?):\s*(.*)$", body)
        if match:
            speaker, said = match.group(1).strip(), match.group(2).strip()
        cues.append([parse_ts(left), parse_ts(right), speaker, said])

    merged = []
    for cue in cues:
        if merged and merged[-1][2] == cue[2] and cue[0] - merged[-1][1] < 8:
            merged[-1][1] = cue[1]
            merged[-1][3] += " " + cue[3]
        else:
            merged.append(cue)
    return merged


def roster(turns):
    stats = {}
    for start, end, speaker, _ in turns:
        if not speaker:
            continue
        row = stats.setdefault(speaker, {"seconds": 0.0, "first": start,
                                         "last": end, "turns": 0})
        row["seconds"] += max(0.0, end - start)
        row["first"] = min(row["first"], start)
        row["last"] = max(row["last"], end)
        row["turns"] += 1
    return dict(sorted(stats.items(), key=lambda kv: -kv[1]["seconds"]))


def render_transcript(meeting, turns, summary=None):
    out = io.StringIO()
    out.write("# " + str(meeting.get("topic", "Zoom meeting")) + "\n")
    out.write("# start    : " + str(meeting.get("start_time", "?")) + " (UTC)\n")
    out.write("# duration : " + str(meeting.get("duration", "?")) + " min\n")
    out.write("# meeting  : " + str(meeting.get("id", "?"))
              + "   uuid " + str(meeting.get("uuid", "?")) + "\n\n")

    out.write("# ---- speakers (talk time / first heard / last heard) ----\n")
    for name, row in roster(turns).items():
        out.write("#   {0:<32} {1:6.1f} min   {2} -> {3}   {4} turns\n".format(
            name[:32], row["seconds"] / 60.0, hhmmss(row["first"]),
            hhmmss(row["last"]), row["turns"]))
    out.write("#\n# Times below are offsets from the recording start, not wall clock.\n")
    out.write("# --------------------------------------------------------\n\n")

    if summary:
        out.write("# ==== Zoom AI Companion summary ====\n")
        for section in summary.get("summary_details") or []:
            out.write("#\n# " + str(section.get("label", "")) + "\n")
            for line in str(section.get("summary") or "").split("\n"):
                out.write("#   " + line + "\n")
        if summary.get("summary_overview"):
            out.write("#\n# Overview: " + str(summary["summary_overview"]) + "\n")
        out.write("# ===================================\n\n")

    for start, _, speaker, said in turns:
        out.write("[" + hhmmss(start) + "] " + (speaker + ": " if speaker else "") + said + "\n")
    return out.getvalue()


DTD = re.compile(r"<!\s*(doctype|entity)", re.I)
NS_LOCK = threading.Lock()


def q(tag):
    return "{" + W + "}" + tag


def read_docx_xml(path):
    with zipfile.ZipFile(path) as zf:
        return zf.read("word/document.xml").decode("utf-8")


def list_formats(path):
    with zipfile.ZipFile(path) as zf:
        if "word/numbering.xml" not in zf.namelist():
            return {}
        xml = guard_xml(zf.read("word/numbering.xml").decode("utf-8"), path + ":numbering.xml")
    root = parse_xml(xml)
    abstract = {}
    for a in root.findall(q("abstractNum")):
        lvl0 = next((l for l in a.findall(q("lvl")) if l.get(q("ilvl")) == "0"), None)
        fmt = lvl0.find(q("numFmt")) if lvl0 is not None else None
        abstract[a.get(q("abstractNumId"))] = fmt.get(q("val")) if fmt is not None else ""
    formats = {}
    for n in root.findall(q("num")):
        ref = n.find(q("abstractNumId"))
        if ref is not None:
            formats[n.get(q("numId"))] = abstract.get(ref.get(q("val")), "")
    return formats


def guard_xml(xml_text, source):
    if DTD.search(xml_text):
        raise MinutesError("refusing to parse " + source + ": it declares a DTD or XML entities, "
            "which a Word document never does. Treat that file as untrusted.")
    return xml_text


def declared_namespaces(xml_text):
    return re.findall(r'xmlns:([A-Za-z0-9_]+)="([^"]+)"', xml_text[:4000])


def serialize(root, namespaces):
    with NS_LOCK:
        saved = dict(ET._namespace_map)
        try:
            for prefix, uri in namespaces:
                try:
                    ET.register_namespace(prefix, uri)
                except ValueError:
                    pass
            return ET.tostring(root, encoding="unicode")
        finally:
            ET._namespace_map.clear()
            ET._namespace_map.update(saved)


def write_docx(src, dst, document_xml):
    with zipfile.ZipFile(src) as zin:
        infos = zin.infolist()
        blobs = {info.filename: zin.read(info.filename) for info in infos}
    blobs["word/document.xml"] = document_xml.encode("utf-8")
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in infos:
            zout.writestr(info.filename, blobs[info.filename])


def para_text(p):
    return "".join(t.text or "" for t in p.iter(q("t")))


def _ppr_val(p, child, attr="val"):
    node = p.find(q("pPr") + "/" + q(child))
    return node.get(q(attr)) if node is not None else None


def para_numid(p):
    node = p.find(q("pPr") + "/" + q("numPr") + "/" + q("numId"))
    return node.get(q("val")) if node is not None else None


def para_ilvl(p):
    node = p.find(q("pPr") + "/" + q("numPr") + "/" + q("ilvl"))
    return int(node.get(q("val"))) if node is not None else 0


def para_indent(p):
    val = _ppr_val(p, "ind", "left")
    return int(val) if val and val.lstrip("-").isdigit() else None


def para_style(p):
    return _ppr_val(p, "pStyle") or ""


def set_para_text(p, text):
    runs = p.findall(q("r"))
    if not runs:
        runs = [ET.SubElement(p, q("r"))]
    first = runs[0]
    for extra in runs[1:]:
        p.remove(extra)
    for child in list(first):
        if child.tag != q("rPr"):
            first.remove(child)
    t = ET.SubElement(first, q("t"))
    t.set(XML_SPACE, "preserve")
    t.text = text


def make_para(text, indent, bold=False, num_id="1", ilvl=0):
    p = ET.Element(q("p"))
    pPr = ET.SubElement(p, q("pPr"))
    numPr = ET.SubElement(pPr, q("numPr"))
    ET.SubElement(numPr, q("ilvl")).set(q("val"), str(ilvl))
    ET.SubElement(numPr, q("numId")).set(q("val"), str(num_id))
    ET.SubElement(pPr, q("ind")).set(q("left"), str(indent))
    if bold:
        ET.SubElement(ET.SubElement(pPr, q("rPr")), q("b"))
    r = ET.SubElement(p, q("r"))
    if bold:
        ET.SubElement(ET.SubElement(r, q("rPr")), q("b"))
    t = ET.SubElement(r, q("t"))
    t.set(XML_SPACE, "preserve")
    t.text = text
    return p


NORM = re.compile(r"[^a-z0-9]+")
ROOT_OPEN = re.compile(r"<w:document\b[^>]*>", re.S)


def norm(text):
    return NORM.sub(" ", (text or "").lower()).strip()


def sentence(text):
    text = (text or "").strip()
    return text if text.endswith((".", "!", "?")) else text + "."


class Minutes:

    def __init__(self, path):
        self.path = path
        self.xml = guard_xml(read_docx_xml(path), path)
        self.namespaces = declared_namespaces(self.xml)
        self.root = parse_xml(self.xml)
        self.body = self.root.find(q("body"))
        if self.body is None:
            raise MinutesError("no <w:body> in " + path)
        formats = list_formats(path)
        self.agenda_numids = {n for n, f in formats.items() if f and f != "bullet"}
        bullets = sorted((n for n, f in formats.items() if f == "bullet"), key=int)
        self.bullet_numid = bullets[0] if bullets else "1"


    def paras(self):
        return [el for el in list(self.body) if el.tag == q("p")]

    def find_para(self, needle, predicate=None, after=None):
        target = norm(needle)
        if not target:
            return None
        paras = self.paras()
        if after is not None:
            try:
                paras = paras[paras.index(after) + 1:]
            except ValueError:
                pass
        for p in paras:
            if target in norm(para_text(p)) and (predicate is None or predicate(p)):
                return p
        return None

    def find_heading(self, needle):
        target = norm(needle)
        for p in self.paras():
            if para_style(p).startswith("Heading") and target in norm(para_text(p)):
                return p
        return None

    def is_agenda_item(self, p):
        return para_numid(p) in self.agenda_numids

    def item_span(self, item):
        kids = list(self.body)
        start = kids.index(item)
        base = para_ilvl(item)
        base_indent = para_indent(item) or 0
        span = []
        for el in kids[start + 1:]:
            if el.tag != q("p"):
                if el.tag == q("tbl"):
                    continue
                break
            if para_style(el).startswith("Heading"):
                break
            if self.is_agenda_item(el) and para_ilvl(el) <= base:
                break
            if (para_numid(el) is None and para_text(el).strip()
                    and (para_indent(el) or 0) < base_indent):
                break
            span.append(el)
        return span

    def insertion_point(self, item):
        span = self.item_span(item)
        while span and para_numid(span[-1]) is None and not para_text(span[-1]).strip():
            span.pop()
        return span[-1] if span else item


    def insert_after(self, anchor, new_para):
        kids = list(self.body)
        self.body.insert(kids.index(anchor) + 1, new_para)

    def fill_under(self, needle, text, bold=False):
        item = self.find_para(needle, predicate=self.is_agenda_item)
        if item is None:
            item = self.find_para(needle)
        if item is None:
            return False, "no agenda item matching " + repr(needle)

        span = self.item_span(item)
        for p in span:
            if not para_text(p).strip() and para_numid(p) and not self.is_agenda_item(p):
                set_para_text(p, text)
                return True, "filled existing bullet"

        sibling = next((p for p in span if para_numid(p) and not self.is_agenda_item(p)), None)
        if sibling is not None:
            indent = para_indent(sibling) or (para_indent(item) or 360) + 360
            num_id = para_numid(sibling)
        else:
            indent = (para_indent(item) or 360) + 360
            num_id = self.bullet_numid
        new_para = make_para(text, indent, bold=bold, num_id=num_id)
        self.insert_after(self.insertion_point(item), new_para)
        return True, "inserted new bullet"

    def replace_text(self, needle, text, predicate=None):
        p = self.find_para(needle, predicate)
        if p is None:
            return False, "no paragraph matching " + repr(needle)
        set_para_text(p, text)
        return True, "replaced"

    def append_to_line(self, needle, suffix, sep=" - ", after=None):
        p = self.find_para(needle, after=after)
        if p is None:
            return False, "no line matching " + repr(needle)
        current = para_text(p).rstrip()
        while current.endswith("-") or current.endswith("_"):
            current = current[:-1].rstrip()
        set_para_text(p, current + sep + suffix)
        return True, "appended"

    def save(self, dst):
        xml = serialize(self.root, self.namespaces)

        orig_open = ROOT_OPEN.search(self.xml)
        new_open = ROOT_OPEN.search(xml)
        if orig_open and new_open:
            xml = xml[:new_open.start()] + orig_open.group(0) + xml[new_open.end():]
        elif orig_open:
            raise MinutesError("could not locate the <w:document> tag in the regenerated XML; "
                "refusing to write a file Word may reject.")

        if not xml.startswith("<?xml"):
            xml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n' + xml
        write_docx(self.path, dst, xml)


def cmd_auth_check(args):
    token = get_token(force=True)
    print("token acquired, length " + str(len(token)))
    user_id = os.environ.get("ZOOM_USER_ID", "me")
    who = api_get("/users/" + user_id)
    print("authenticated as: {0} {1} <{2}>  type={3}".format(
        who.get("first_name", ""), who.get("last_name", ""),
        who.get("email", "?"), who.get("type", "?")))
    print("account id      : " + str(who.get("account_id", "?")))
    print("\nOK. Scopes look sufficient for /users/{id}. If `list` returns 400/403,")
    print("add the cloud-recording read scopes to the app and re-activate it.")


def _pick_meetings(args):
    user_id = os.environ.get("ZOOM_USER_ID", "me")
    if args.date:
        try:
            day = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            die("--date must be YYYY-MM-DD, got " + repr(args.date))
        start, end = day - timedelta(days=1), day + timedelta(days=1)
    else:
        end = date.today()
        start = end - timedelta(days=args.days)

    meetings = list_recordings(user_id, start, end)

    wanted = args.meeting_id or os.environ.get("ASG_MEETING_ID")
    if wanted:
        digits = re.sub(r"\D", "", wanted)
        meetings = [m for m in meetings if re.sub(r"\D", "", str(m.get("id", ""))) == digits]
    if args.date:
        meetings = [m for m in meetings if str(m.get("start_time", "")).startswith(args.date)]
    return meetings


def cmd_list(args):
    meetings = _pick_meetings(args)
    if not meetings:
        print("no cloud recordings found in that window"
              + (" for meeting " + str(args.meeting_id or os.environ.get('ASG_MEETING_ID'))
                 if (args.meeting_id or os.environ.get("ASG_MEETING_ID")) else ""))
        print("\nReminder: only *cloud* recordings reach the API. Local recordings do not.")
        return
    print("{0:<22} {1:<13} {2:>5}  {3:<4} {4}".format(
        "start (UTC)", "meeting id", "min", "vtt", "topic"))
    for m in meetings:
        has_vtt = "yes" if transcript_file(m) else "NO"
        print("{0:<22} {1:<13} {2:>5}  {3:<4} {4}".format(
            str(m.get("start_time", "?"))[:22], str(m.get("id", "?")),
            str(m.get("duration", "?")), has_vtt, str(m.get("topic", ""))[:44]))


def cmd_fetch(args):
    meetings = _pick_meetings(args)
    if not meetings:
        die("no cloud recording found. Run `list` to see what is available.")
    if len(meetings) > 1 and not args.date:
        print("note: {0} recordings matched; taking the most recent. "
              "Use --date to pin one.".format(len(meetings)), file=sys.stderr)
    meeting = meetings[-1]

    rec = transcript_file(meeting)
    if not rec:
        die("that recording has no VTT transcript. Audio transcription must be enabled\n"
            "in Zoom before the meeting, and Zoom needs time after it to finish processing.")

    vtt = download(rec).decode("utf-8", "replace")
    turns = parse_vtt(vtt)
    if not turns:
        die("the transcript downloaded but parsed to zero turns -- pass --keep-vtt and inspect it.")

    summary = None if args.no_summary else meeting_summary(str(meeting.get("uuid", "")))
    text = render_transcript(meeting, turns, summary)

    out = args.out or ("transcript-" + str(meeting.get("start_time", "meeting"))[:10] + ".txt")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(text)
    if args.keep_vtt:
        with open(out + ".vtt", "w", encoding="utf-8") as fh:
            fh.write(vtt)
    print("wrote {0}  ({1} turns, {2} speakers)".format(out, len(turns), len(roster(turns))))


def cmd_local(args):
    with open(args.vtt, "r", encoding="utf-8", errors="replace") as fh:
        vtt = fh.read()
    if "-->" not in vtt:
        die(args.vtt + " does not look like a VTT/SRT transcript (no cue timings found).\n"
            "On the Zoom recording page, download the *Audio Transcript*, not the chat "
            "file or the recording itself.")

    turns = parse_vtt(vtt)
    if not turns:
        die("parsed zero turns out of " + args.vtt)

    meeting = {"topic": args.topic or os.path.basename(args.vtt),
               "start_time": args.date or "(not recorded in the VTT)",
               "duration": int(max(t[1] for t in turns) // 60),
               "id": "(local file)", "uuid": "(local file)"}

    out = args.out or (os.path.splitext(args.vtt)[0] + ".txt")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(render_transcript(meeting, turns))
    print("wrote {0}  ({1} turns, {2} speakers)".format(out, len(turns), len(roster(turns))))


def cmd_inspect(args):
    doc = Minutes(args.template)
    slots = []
    print("{0:<6} {1:<9} {2:<7} {3}".format("idx", "numId", "indent", "text"))
    for i, p in enumerate(doc.paras()):
        text = para_text(p).strip()
        num, ind = para_numid(p) or "-", para_indent(p)
        marker = ""
        if doc.is_agenda_item(p) and text:
            marker = "ITEM  "
            slots.append(text)
        elif not text and num != "-" and not doc.is_agenda_item(p):
            marker = "EMPTY "
        elif "____" in text or re.search(r"called to order at\s*\.?$", text):
            marker = "BLANK "
        if marker or args.all:
            print("{0}{1:<6} {2:<9} {3:<7} {4}".format(
                marker, i, num, ind if ind is not None else "-", text[:90]))

    if args.skeleton:
        skeleton = {
            "order_time": "9:0X a.m.",
            "adjourn_time": "11:0X a.m.",
            "roll_call": {},
            "motions": [],
            "fills": [{"under": s[:60], "text": ""} for s in slots[:40]],
            "reports": {},
            "summary": [],
        }
        with open(args.skeleton, "w", encoding="utf-8") as fh:
            json.dump(skeleton, fh, indent=2, ensure_ascii=False)
        print("\nwrote skeleton to " + args.skeleton)


def apply_minutes(template, data, out):
    doc = Minutes(template)
    applied, failed = [], []

    def record(ok, what, detail):
        (applied if ok else failed).append(what + "  [" + detail + "]")

    if data.get("order_time"):
        ok, detail = doc.replace_text(
            "called to order at",
            sentence("Meeting called to order at " + data["order_time"]))
        record(ok, "call to order", detail)

    for rep in data.get("replace") or []:
        ok, detail = doc.replace_text(rep.get("match", ""), rep.get("text", ""))
        record(ok, "replace " + repr(rep.get("match", "")[:40]), detail)

    for position, status in (data.get("roll_call") or {}).items():
        ok, detail = doc.append_to_line(position, status)
        record(ok, "roll call: " + position, detail)

    for motion in data.get("motions") or []:
        needle, text = motion.get("under", ""), motion.get("text", "")
        target = doc.find_para(needle)
        if target is not None and "____" in para_text(target):
            set_para_text(target, text)
            record(True, "motion under " + repr(needle[:40]), "replaced placeholder")
        else:
            ok, detail = doc.fill_under(needle, text)
            record(ok, "motion under " + repr(needle[:40]), detail)

    for fill in data.get("fills") or []:
        text = (fill.get("text") or "").strip()
        if not text:
            continue
        ok, detail = doc.fill_under(fill.get("under", ""), text, bold=bool(fill.get("bold")))
        record(ok, "discussion under " + repr(str(fill.get("under"))[:40]), detail)

    reports_from = doc.find_heading("REPORTS")
    for line, text in (data.get("reports") or {}).items():
        sep = " - "
        if isinstance(text, dict):
            sep, text = text.get("sep", sep), text.get("text", "")
        ok, detail = doc.append_to_line(line, text, sep=sep, after=reports_from)
        record(ok, "report: " + line, detail)

    if data.get("adjourn_time"):
        anchor = doc.find_para("Advisor Reports", predicate=doc.is_agenda_item)
        if anchor is None:
            anchor = doc.find_para("Adjournment", predicate=doc.is_agenda_item)
        if anchor is None:
            items = [p for p in doc.paras() if doc.is_agenda_item(p) and para_ilvl(p) == 0 and para_text(p).strip()]
            anchor = items[-1] if items else None
        text = sentence("Chair adjourned the meeting at " + data["adjourn_time"])
        if anchor is not None:
            doc.insert_after(doc.insertion_point(anchor), make_para(text, 720, num_id=doc.bullet_numid))
            record(True, "adjournment", "inserted after " + para_text(anchor).strip()[:30])
        else:
            record(False, "adjournment", "no Advisor Reports or Adjournment item found")

    bullets = data.get("summary") or []
    if bullets:
        anchor = doc.find_para("Key Items Discussed")
        if anchor is None:
            anchor = next((p for p in doc.paras() if para_style(p) == "LMSummary"), None)
        if anchor is None:
            record(False, "summary", "no 'Key Items Discussed/Actions Taken' line found")
        else:
            for text in reversed(bullets):
                doc.insert_after(anchor, make_para(text, 720, bold=True, num_id=doc.bullet_numid))
            record(True, "summary", str(len(bullets)) + " bullets")

    fields = {"lm_start": data.get("order_time") or "", "lm_end": data.get("adjourn_time") or ""}
    fields.update({k: v for k, v in (data.get("fields") or {}).items() if k in ("lm_date", "lm_place")})
    parents = {child: parent for parent in doc.root.iter() for child in parent}
    for mark in list(doc.root.iter(q("bookmarkStart"))):
        name = mark.get(q("name"), "")
        value = " ".join(str(fields.get(name) or "").split())[:120]
        holder = parents.get(mark)
        current = para_text(holder).strip() if holder is not None else ""
        if not value or holder is None or (current and not current.endswith(":")):
            continue
        run = ET.Element(q("r"))
        t = ET.SubElement(run, q("t"))
        t.set(XML_SPACE, "preserve")
        t.text = value
        holder.insert(list(holder).index(mark) + 1, run)
        record(True, "field " + name, "filled")

    for fix in data.get("corrections") or []:
        old, new = fix.get("find", ""), fix.get("replace", "")
        hits = 0
        for p in doc.paras():
            if fix.get("whole_paragraph"):
                if para_text(p).strip() == old:
                    set_para_text(p, new)
                    hits += 1
                continue
            for t in p.iter(q("t")):
                if t.text and old in t.text:
                    t.text = t.text.replace(old, new)
                    hits += 1
        record(hits > 0, "correction " + repr(old),
               str(hits) + " hit(s)" if hits else "not found within a single run")

    doc.save(out)
    return applied, failed


def cmd_fill(args):
    with open(args.data, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    applied, failed = apply_minutes(args.template, data, args.out)

    print("applied " + str(len(applied)) + " change(s):")
    for line in applied:
        print("  + " + line)
    if failed:
        print("\nSKIPPED " + str(len(failed)) + " -- these did not match the template:")
        for line in failed:
            print("  ! " + line)
    print("\nwrote " + args.out)
    print("This is a DRAFT. Read it against the recording before it goes to the board.")
    if failed:
        sys.exit(2)


def main():
    load_dotenv()
    ap = argparse.ArgumentParser(
        description="Pull a Zoom transcript and fill an ASG minutes template.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("auth-check", help="verify the Zoom credentials work").set_defaults(
        func=cmd_auth_check)

    for name, helptext, func in (("list", "list cloud recordings", cmd_list),
                                 ("fetch", "download + parse a transcript", cmd_fetch)):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("--days", type=int, default=14, help="look back this many days")
        p.add_argument("--date", help="a single meeting date, YYYY-MM-DD")
        p.add_argument("--meeting-id", help="numeric Zoom meeting id (overrides ASG_MEETING_ID)")
        p.set_defaults(func=func)
        if name == "fetch":
            p.add_argument("--out", help="output path (default transcript-YYYY-MM-DD.txt)")
            p.add_argument("--keep-vtt", action="store_true", help="also save the raw .vtt")
            p.add_argument("--no-summary", action="store_true",
                           help="skip the AI Companion summary lookup")

    p = sub.add_parser("local", help="render a .vtt you downloaded by hand (no credentials)")
    p.add_argument("--vtt", required=True, help="path to the Audio Transcript .vtt")
    p.add_argument("--out", help="output path (default: same name, .txt)")
    p.add_argument("--date", help="meeting date, for the header")
    p.add_argument("--topic", help="meeting topic, for the header")
    p.set_defaults(func=cmd_local)

    p = sub.add_parser("inspect", help="show the template's fillable slots")
    p.add_argument("--template", required=True)
    p.add_argument("--skeleton", help="also write a starter JSON here")
    p.add_argument("--all", action="store_true", help="show every paragraph, not just slots")
    p.set_defaults(func=cmd_inspect)

    p = sub.add_parser("fill", help="apply a minutes JSON to the template")
    p.add_argument("--template", required=True)
    p.add_argument("--data", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_fill)

    args = ap.parse_args()
    try:
        args.func(args)
    except ZoomError as exc:
        die("Zoom API returned HTTP {0}\n{1}".format(exc.status, exc.detail))
    except FileNotFoundError as exc:
        die("file not found: " + str(exc))
    except MinutesError as exc:
        die(str(exc))


if __name__ == "__main__":
    main()
