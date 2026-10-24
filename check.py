#!/usr/bin/env python3
"""Status checks for the Hepherus status page (runs in GitHub Actions on a schedule).

Writes checks.json with the PUBLIC, customer-facing components ONLY — "Hepherus app", "Sign-in",
"Agents", "Connections" — each a boolean derived from probing public surfaces in plain terms. No
hostnames, vendor names, internal endpoint names or secrets appear in this file or in checks.json.

Internal-only surfaces (an operator console; the database/auth health) are probed too, but their URLs
come from GitHub Actions SECRETS (never the repo), and their results are written to an EPHEMERAL
internal.json (git-ignored, same job run) that alert.py uses to email Maestro. They never reach the page.

Stdlib only.
"""
import json
import os
import datetime
import urllib.request
import urllib.error

TIMEOUT = 15


def probe(url, ok):
    """Return True/False for 'up' given a URL and an is-up(status) predicate (reachability).

    Input: url (str); ok (callable: status:int -> bool).
    Returns: True if the host answered and ok(status) holds; False on 5xx / DNS / connection / timeout.
    """
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "hepherus-status/1.0"}, method="GET")
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return bool(ok(r.status))
    except urllib.error.HTTPError as e:
        return bool(ok(e.code))          # an HTTP status (e.g. 401) still means the host answered
    except Exception:
        return False                      # DNS / connection / timeout = down


def probe_json(url, key):
    """GET a JSON health endpoint; return True iff HTTP 200 and body[key] is True; any error -> False.

    Input: url (str); key (str, the boolean field to read). Returns: bool.
    """
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "hepherus-status/1.0"}, method="GET")
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            if r.status != 200:
                return False
            body = json.loads(r.read().decode("utf-8"))
            return body.get(key) is True
    except Exception:
        return False


def env_probe(url_env):
    """Probe an INTERNAL surface whose URL lives in a GitHub Actions secret (never in this repo).

    Input: url_env (str, the environment variable holding the URL).
    Returns: True/False when the secret is set (answered-below-500 = up, so a 401/403 counts as reachable),
    or None (no signal) when the secret is absent — so missing config shows Unknown, never a false alarm.
    """
    url = os.environ.get(url_env)
    if not url:
        return None
    return probe(url, lambda s: 200 <= s < 500)


def _all_known(*vals):
    """True iff every KNOWN (non-None) signal is up; None signals are ignored. All-None -> None (Unknown).

    So a customer component is Operational only when all of its underlying signals that we actually have
    are up, and an unconfigured internal signal never forces a false "Down".
    """
    known = [v for v in vals if v is not None]
    return all(known) if known else None


def main():
    """Probe the public surfaces, derive the four customer components, and write checks.json. Returns None."""
    # PUBLIC customer surfaces (public hosts/endpoints only).
    app = probe("https://app.hepherus.com/", lambda s: 200 <= s < 400)
    signin = probe("https://app.hepherus.com/sign-in", lambda s: s == 200)
    backend = probe("https://api.hepherus.com/version", lambda s: s == 200)
    connector = probe("https://api.hepherus.com/connector", lambda s: s < 500)
    decrypt = probe_json("https://api.hepherus.com/health/decrypt", "decrypt_ok")

    # INTERNAL surfaces — URLs from Actions secrets; None when not configured. Email-only; never on the page.
    db = env_probe("DB_HEALTH_URL")          # database/auth health: feeds the two customer components + email
    admin = env_probe("ADMIN_HEALTH_URL")    # operator console: email-only (not a customer component)

    # The four customer-facing components. Mapping: database -> Hepherus app + Sign-in; backend -> Agents;
    # connector + decrypt -> Connections.
    services = [
        {"name": "Hepherus app", "up": _all_known(app, db)},
        {"name": "Sign-in", "up": _all_known(signin, db)},
        {"name": "Agents", "up": _all_known(backend)},
        {"name": "Connections", "up": _all_known(connector, decrypt)},
    ]
    checked_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = {"checked_at": checked_at, "services": services}
    with open("checks.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
        f.write("\n")

    # Ephemeral internal results for alert.py (git-ignored; consumed in the same job run). Opaque ids keep
    # the committed alert_state.json free of internal names; the human label is used only in the private email.
    internal = {
        "checked_at": checked_at,
        "services": [
            {"id": "i1", "label": os.environ.get("DB_HEALTH_LABEL", "Database"), "up": db},
            {"id": "i2", "label": os.environ.get("ADMIN_HEALTH_LABEL", "Operator console"), "up": admin},
        ],
    }
    with open("internal.json", "w", encoding="utf-8") as f:
        json.dump(internal, f, indent=2)
        f.write("\n")

    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
