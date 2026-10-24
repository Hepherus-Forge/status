#!/usr/bin/env python3
"""Send ONE clearly-marked TEST alert email, to prove the Resend path works end-to-end. Stdlib only.

Run from the workflow ONLY when the manual `send_test_alert` input is set, so a routine scheduled run never
emails. Uses the same secrets/sender as alert.py. Exit 0 always (a mail error must not fail the job).
"""
import json
import os
import urllib.request

RESEND_URL = "https://api.resend.com/emails"


def main():
    """Send a single TEST email via Resend using the Actions secrets. Returns None."""
    api_key = os.environ.get("RESEND_API_KEY")
    to_addr = os.environ.get("ALERT_EMAIL_TO")
    from_addr = os.environ.get("ALERT_EMAIL_FROM", "alerts@hepherus.com")
    if not api_key or not to_addr:
        print("[test-alert] RESEND_API_KEY/ALERT_EMAIL_TO not set — nothing sent")
        return
    subject = "[Hepherus TEST] Status alert test — please ignore"
    text = ("This is a TEST of the Hepherus status alert email path. No action is needed.\n\n"
            "If you received this, the status checker can email you when a real outage is detected.\n"
            "Status page: https://status.hepherus.com/\n")
    payload = json.dumps({"from": from_addr, "to": [to_addr], "subject": subject, "text": text}).encode("utf-8")
    req = urllib.request.Request(
        RESEND_URL, data=payload, method="POST",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            print(f"[test-alert] resend status {r.status} (TEST email sent to the configured recipient)")
    except Exception as e:  # never fail the job on a mail error
        print(f"[test-alert] resend send failed: {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
