#!/usr/bin/env python3
"""Status checks for the Hepherus status/alert page (runs in GitHub Actions on a schedule).

Probes the five surfaces and writes checks.json. "up" = an HTTP response below 500 (reachable); a connection
failure or 5xx = down. The connector counts a 401 as up (it answers, just unauthenticated). Stdlib only."""
import json, datetime, urllib.request, urllib.error

TARGETS = [
    ("App (app.hepherus.com)",       "https://app.hepherus.com/",            lambda s: 200 <= s < 400),
    ("Backend (api.hepherus.com)",   "https://api.hepherus.com/version",     lambda s: s == 200),
    ("Admin (admin.hepherus.com)",   "https://admin.hepherus.com/",          lambda s: 200 <= s < 400),
    ("Connector",                    "https://api.hepherus.com/connector",   lambda s: s < 500),
    ("Sign-in page",                 "https://app.hepherus.com/sign-in",     lambda s: s == 200),
]

def probe(url, ok):
    """Return True/False for up, given a URL and an is-up(status) predicate. Reachability-based."""
    req = urllib.request.Request(url, headers={"User-Agent": "hepherus-status/1.0"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return bool(ok(r.status))
    except urllib.error.HTTPError as e:
        return bool(ok(e.code))          # an HTTP status (e.g. 401) still means the host answered
    except Exception:
        return False                      # DNS/connection/timeout = down

def main():
    services = [{"name": name, "up": probe(url, ok)} for name, url, ok in TARGETS]
    out = {"checked_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "services": services}
    with open("checks.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
        f.write("\n")
    print(json.dumps(out, indent=2))

if __name__ == "__main__":
    main()
