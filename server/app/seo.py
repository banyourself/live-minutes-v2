import html
import json
import os

from sqlalchemy import select

from . import models
from .settings import settings

BRAND = "Live Minutes"
HOME_TITLE = "Live Minutes · AI meeting minutes from Zoom captions and transcripts"
HOME_DESCRIPTION = ("AI drafts meeting minutes from Zoom captions, transcripts, and chat in your own format, for student "
                    "governments, clubs, and your own meetings.")
PAGES = {
    "/": (HOME_TITLE, HOME_DESCRIPTION),
    "/privacy": ("Privacy policy", "What Live Minutes collects, how it is used, who it is shared with, and the choices you have."),
    "/terms": ("Terms of use", "The terms for using Live Minutes, for school organizations and personal workspaces."),
    "/accessibility": ("Accessibility", "How Live Minutes works with keyboards, screen readers, and captions, and how to report a barrier."),
    "/support": ("Support", "Help with Live Minutes accounts, meetings, Zoom imports, and AI drafting, and how to reach me."),
    "/help/zoom": ("Live Minutes for Zoom", "Connect Zoom to import cloud recording captions, transcripts, and chat into Live Minutes. "
                   "How to add, use, and remove the app."),
    "/download": ("Downloads", "The Live Minutes desktop app and the Caption Reader browser extension, which sends Zoom web "
                  "captions to your meeting."),
}
NOINDEX = "noindex, nofollow"
APP_ROOTS = {"login", "dashboard", "verify", "reset", "invite", "connect", "account", "admin", "funding", "manage",
             "meetings", "new-org", "notifications", "recordings", "search", "settings", "templates", "votes", "week",
             "zoom"}
SECURITY_EXPIRES = "2027-09-01T00:00:00.000Z"
_shell = {"path": "", "mtime": 0.0, "text": ""}


def origin():
    return settings.public_url.rstrip("/")


def full_title(title):
    return title if title.startswith(BRAND) else title + " · " + BRAND


def app_ld():
    return {"@context": "https://schema.org", "@graph": [
        {"@type": "WebSite", "name": BRAND, "url": origin() + "/", "inLanguage": "en"},
        {"@type": "SoftwareApplication", "name": BRAND, "url": origin() + "/", "applicationCategory": "BusinessApplication",
         "operatingSystem": "Web, Windows", "description": HOME_DESCRIPTION, "image": origin() + "/og-image.png",
         "author": {"@type": "Person", "name": "Kevin Le", "url": "https://kevinle.tech/"}}]}


def archive_org(db, org_id):
    org = db.get(models.Organization, (org_id or "")[:32])
    if org is None or not (org.settings or {}).get("public_archive"):
        return None
    return org


def meta_for(path, db):
    path = path if path == "/" else "/" + path.strip("/")
    if path in PAGES:
        title, description = PAGES[path]
        return {"title": full_title(title), "description": description, "url": origin() + path, "index": True,
                "status": 200, "ld": app_ld() if path == "/" else None}
    if path.startswith("/archive/") and path.count("/") == 2:
        org = archive_org(db, path.split("/")[2])
        if org is None:
            return missing()
        place = ", " + org.school if org.school else ""
        return {"title": full_title(org.name + " meeting minutes"),
                "description": ("Approved meeting minutes from " + org.name + place + ", with plain-language summaries.")[:160],
                "url": origin() + path, "index": True, "status": 200, "ld": None}
    if path.split("/")[1] in APP_ROOTS:
        return {"title": BRAND, "index": False, "status": 200}
    return missing()


def missing():
    return {"title": full_title("Page not found"), "index": False, "status": 404}


def e(value):
    return html.escape(value, quote=True)


def head(meta):
    out = ["<title>" + e(meta["title"]) + "</title>"]
    if not meta["index"]:
        out.append('<meta name="robots" content="' + NOINDEX + '" />')
        if meta["status"] == 404:
            out.append('<meta name="lm-page" content="missing" />')
        return "\n    ".join(out)
    image = origin() + "/og-image.png"
    alt = "The Live Minutes welcome tour: live captions from a sample meeting turning into draft minutes, with no real names"
    out += ['<meta name="description" content="' + e(meta["description"]) + '" />',
            '<meta name="robots" content="index, follow, max-image-preview:large" />',
            '<link rel="canonical" href="' + e(meta["url"]) + '" />',
            '<meta property="og:type" content="website" />',
            '<meta property="og:site_name" content="' + BRAND + '" />',
            '<meta property="og:locale" content="en_US" />',
            '<meta property="og:title" content="' + e(meta["title"]) + '" />',
            '<meta property="og:description" content="' + e(meta["description"]) + '" />',
            '<meta property="og:url" content="' + e(meta["url"]) + '" />',
            '<meta property="og:image" content="' + image + '" />',
            '<meta property="og:image:width" content="1200" />',
            '<meta property="og:image:height" content="630" />',
            '<meta property="og:image:alt" content="' + alt + '" />',
            '<meta name="twitter:card" content="summary_large_image" />',
            '<meta name="twitter:title" content="' + e(meta["title"]) + '" />',
            '<meta name="twitter:description" content="' + e(meta["description"]) + '" />',
            '<meta name="twitter:image" content="' + image + '" />',
            '<meta name="twitter:image:alt" content="' + alt + '" />']
    if meta.get("ld"):
        data = json.dumps(meta["ld"], separators=(",", ":")).replace("<", "\\u003c")
        out.append('<script type="application/ld+json">' + data + "</script>")
    return "\n    ".join(out)


def shell(index_path):
    mtime = os.path.getmtime(index_path)
    if _shell["path"] != index_path or _shell["mtime"] != mtime:
        with open(index_path, encoding="utf-8") as fh:
            _shell.update(path=index_path, mtime=mtime, text=fh.read())
    return _shell["text"]


def render(index_path, path, db):
    meta = meta_for(path, db)
    text = shell(index_path)
    start, end = text.find("<title>"), text.find("</title>")
    if start < 0 or end < start:
        return text, meta
    return text[:start] + head(meta) + text[end + len("</title>"):], meta


def robots_txt():
    return "User-agent: *\nAllow: /\nDisallow: /api/\n\nSitemap: " + origin() + "/sitemap.xml\n"


def security_txt():
    return ("Contact: mailto:kevin@kevinle.tech\nExpires: " + SECURITY_EXPIRES + "\nPreferred-Languages: en\n"
            "Canonical: " + origin() + "/.well-known/security.txt\nPolicy: " + origin() + "/support\n")


def sitemap_xml(db):
    urls = [origin() + p for p in PAGES]
    rows = db.scalars(select(models.Organization)).all()
    urls += [origin() + "/archive/" + o.id for o in rows if (o.settings or {}).get("public_archive")]
    body = "".join("  <url><loc>" + html.escape(u) + "</loc></url>\n" for u in urls)
    return '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + body + "</urlset>\n"
