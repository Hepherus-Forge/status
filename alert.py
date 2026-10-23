#!/usr/bin/env python3
"""Email alerting for the Hepherus status page (runs in GitHub Actions right after check.py). Stdlib only.

Reads the freshly-written checks.json, maintains alert_state.json (a per-service consecutive-failure counter
and whether an alert is currently open), and emails Maestro via the Resend HTTP API:

  - DOWN alert: sent once a service reaches 2 CONSECUTIVE failures (debounces a single cold-start/transient
    timeout, per the T810 §1b spec and Resilience_Brief §5.4). Not re-sent while the alert stays open.
  - RECOVERY: sent once a previously-alerting service is back up.

A check reporting up==null (Unknown, e.g. decrypt_path before INTERNAL_API_SECRET is configured) is treated
as "no signal": it neither increments the failure counter nor clears an open alert.

Secrets/vars it reads from the environment (GitHub Actions secrets/vars; nothing is hardcoded):
  RESEND_API_KEY   - Resend API key (required to actually send; absent => state still tracked, no send)
  ALERT_EMAIL_TO   - Maestro's email (required to send)
  ALERT_EMAIL_FROM - verified Resend sender (default: alerts@hepherus.com)

Exit code is always 0 on a handled path: a missing secret or a Resend error must not fail the checks job
(the page still updates). Send failures are printed.
"""
import json, os, urllib.request, urllib.error

STATE_FILE = "alert_state.json"
CHECKS_FILE = "checks.json"
FAIL_THRESHOLD = 2
RESEND_URL = "https://api.resend.com/emails"


def load_json(path, default):
    """Read JSON from path, returning default on any error. Input: path (str), default. Returns: parsed obj or default."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def send_email(subject, text):
    """Send one email via the Resend API. Input: subject (str), text (str). Returns: True if sent, else False.

    No-ops (returns False, prints why) when RESEND_API_KEY or ALERT_EMAIL_TO is unset.
    """
    api_key = os.environ.get("RESEND_API_KEY")
    to_addr = os.environ.get("ALERT_EMAIL_TO")
    from_addr = os.environ.get("ALERT_EMAIL_FROM", "alerts@hepherus.com")
    if not api_key or not to_addr:
        print(f"[alert] would send: {subject!r} (RESEND_API_KEY/ALERT_EMAIL_TO not set — not sending)")
        return False
    payload = json.dumps({"from": from_addr, "to": [to_addr], "subject": subject, "text": text}).encode("utf-8")
    req = urllib.request.Request(
        RESEND_URL, data=payload, method="POST",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            ok = 200 <= r.status < 300
            print(f"[alert] resend status {r.status} for {subject!r}")
            return ok
    except Exception as e:                # never let a mail failure fail the job
        print(f"[alert] resend send failed for {subject!r}: {type(e).__name__}: {e}")
        return False


def main():
    """Compare the latest checks against prior state, email on 2 consecutive fails / on recovery, persist state."""
    checks = load_json(CHECKS_FILE, {"services": [], "checked_at": ""})
    state = load_json(STATE_FILE, {})
    checked_at = checks.get("checked_at", "")

    for svc in checks.get("services", []):
        name, up = svc.get("name"), svc.get("up")
        if not name:
            continue
        st = state.setdefault(name, {"fails": 0, "alerted": False})

        if up is None:                    # Unknown: no signal — hold counters/flags as-is
            continue
        if up is False:
            st["fails"] += 1
            if st["fails"] >= FAIL_THRESHOLD and not st["alerted"]:
                sent = send_email(
                    f"[Hepherus] DOWN: {name}",
                    f"{name} has failed {st['fails']} consecutive status checks.\n"
                    f"Last check: {checked_at}\n\n"
                    f"Status page: https://status.hepherus.com/\n"
                    f"This is an automated alert from the Hepherus status checker.")
                st["alerted"] = True      # mark open even if the send no-op'd, so we don't spam each run
                st["alert_sent"] = bool(sent)
        else:                             # up is True
            if st["alerted"]:
                send_email(
                    f"[Hepherus] RECOVERED: {name}",
                    f"{name} is back up as of {checked_at}.\n\n"
                    f"Status page: https://status.hepherus.com/")
            st["fails"] = 0
            st["alerted"] = False
            st.pop("alert_sent", None)

    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
        f.write("\n")
    print(json.dumps(state, indent=2))


if __name__ == "__main__":
    main()
