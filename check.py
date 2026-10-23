#!/usr/bin/env python3
"""Status checks for the Hepherus status/alert page (runs in GitHub Actions on a schedule).

Probes the public surfaces and the decrypt-service health, then writes checks.json. Stdlib only.

"up" semantics per check:
  - reachability checks: True = the host answered with an HTTP status below 500 (or a status matching the
    check's predicate); a connection failure/DNS/timeout, or a 5xx, = False (down). A 401 counts as up
    (the host answered, just unauthenticated) for the connector and Supabase reachability checks.
  - decrypt_path: a real end-to-end decrypt self-test (see decrypt_probe). True only on a verified round-trip;
    False on any non-200 / roundtrip_ok false / timeout; None (Unknown) when INTERNAL_API_SECRET is not set
    in the environment, so a missing secret shows "Unknown" rather than firing a false alert.
"""
import json, os, datetime, urllib.request, urllib.error

# Reachability targets: (display name, URL, is-up(status) predicate). GET, 15s timeout.
TARGETS = [
    ("App (app.hepherus.com)",        "https://app.hepherus.com/",                               lambda s: 200 <= s < 400),
    ("Backend (api.hepherus.com)",    "https://api.hepherus.com/version",                        lambda s: s == 200),
    ("Admin (admin.hepherus.com)",    "https://admin.hepherus.com/",                             lambda s: 200 <= s < 400),
    ("Supabase (database & auth)",    "https://wkiwgqcpdwcazckhxnak.supabase.co/auth/v1/health", lambda s: s < 500),
    ("Connector",                     "https://api.hepherus.com/connector",                      lambda s: s < 500),
    ("Sign-in page",                  "https://app.hepherus.com/sign-in",                        lambda s: s == 200),
]

# Decrypt-service end-to-end self-test (T810 §1b runbook / Resilience_Brief §2).
DECRYPT_NAME = "Decrypt service (KMS unwrap)"
DECRYPT_URL = "https://api.hepherus.com/internal/kms-selftest"


def probe(url, ok):
    """Return True/False for 'up' given a URL and an is-up(status) predicate (reachability).

    Input: url (str), ok (callable status:int -> bool).
    Returns: True if the host answered and ok(status) holds; False on 5xx, DNS, connection error or timeout.
    """
    req = urllib.request.Request(url, headers={"User-Agent": "hepherus-status/1.0"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return bool(ok(r.status))
    except urllib.error.HTTPError as e:
        return bool(ok(e.code))          # an HTTP status (e.g. 401) still means the host answered
    except Exception:
        return False                      # DNS/connection/timeout = down


def decrypt_probe():
    """End-to-end decrypt-service health via the backend self-test endpoint.

    Does NOT probe the Cloud Run service directly (it is auth-required + egress-IP-allowlisted; an
    unauthenticated runner gets 403 and must never hold the invoker credential). Instead it POSTs to the
    backend self-test with the shared INTERNAL_API_SECRET (a GitHub Actions secret), which performs a real
    encrypt->decrypt round-trip through the production path.

    Input: none (reads INTERNAL_API_SECRET from the environment).
    Returns: True on HTTP 200 AND roundtrip_ok==True AND a non-empty sha; False on any non-200 / roundtrip_ok
    false / malformed body / timeout / connection error; None when INTERNAL_API_SECRET is unset (Unknown).
    """
    secret = os.environ.get("INTERNAL_API_SECRET")
    if not secret:
        return None                       # Unknown until the Actions secret is configured; no false alert
    req = urllib.request.Request(
        DECRYPT_URL, data=b"", method="POST",
        headers={"User-Agent": "hepherus-status/1.0", "x-internal-secret": secret,
                 "Content-Type": "application/json", "Content-Length": "0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            if r.status != 200:
                return False
            body = json.loads(r.read().decode("utf-8"))
    except Exception:
        return False                      # non-200 (HTTPError), timeout, connection error, bad JSON = fail
    return bool(body.get("roundtrip_ok") is True and body.get("sha"))


def main():
    """Run every check and write checks.json (and print it). Returns None."""
    services = [{"name": name, "up": probe(url, ok)} for name, url, ok in TARGETS]
    services.append({"name": DECRYPT_NAME, "up": decrypt_probe()})
    out = {"checked_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "services": services}
    with open("checks.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
        f.write("\n")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
