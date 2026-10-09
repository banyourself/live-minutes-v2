import datetime
import json
import sys

ALLOW = {
    "GHSA-ch52-4w7c-c8xp": ("2026-12-31", "http-cache-semantics, no fixed release yet. Only electron-builder uses it, through "
                                          "@electron/get and got, to download Electron while building the installer. It is "
                                          "not shipped in the desktop app and there is no shared cache to leak from."),
}
LEVELS = {"high", "critical"}


def advisories(name, vulns, seen):
    if name in seen:
        return set()
    seen.add(name)
    out = set()
    for via in vulns.get(name, {}).get("via", []):
        if isinstance(via, dict):
            out.add(via.get("url", "").rsplit("/", 1)[-1])
        else:
            out |= advisories(via, vulns, seen)
    return out


def main(path):
    vulns = json.load(open(path, encoding="utf-8")).get("vulnerabilities", {})
    today = datetime.date.today().isoformat()
    bad = []
    for name, v in vulns.items():
        if v.get("severity") not in LEVELS:
            continue
        for gid in advisories(name, vulns, set()) or {"unknown"}:
            until = ALLOW.get(gid, ("", ""))[0]
            if not until or until < today:
                bad.append("%s via %s" % (name, gid))
    for gid, (until, why) in ALLOW.items():
        print("allowed until %s: %s (%s)" % (until, gid, why))
    if bad:
        print("high or critical advisories not allowed:\n  " + "\n  ".join(sorted(set(bad))))
        sys.exit(1)
    print("no high or critical advisories outside the allow list")


if __name__ == "__main__":
    main(sys.argv[1])
