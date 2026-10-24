# status

Hepherus status &amp; alert page. A **static** status site hosted on GitHub Pages — deliberately outside the
main host, so it stays up when the app is down.

This repo is **public**. Nothing here names a host, a vendor, an internal endpoint, or a secret. The page
shows only the customer-facing components; any internal check is configured through GitHub Actions secrets and
reported to the operator by email only.

## What it does

- **`check.py`** — a stdlib-only runner (no dependencies) that probes the public surfaces and writes
  **`checks.json`** with the four customer-facing components:
  - **Hepherus app**
  - **Sign-in**
  - **Agents**
  - **Connections**

  Each is a plain up / down / unknown boolean derived from the public surfaces. It also probes the
  decrypt-service health (a public up/down-only endpoint) and folds it into **Connections**.

- Internal-only surfaces (an operator console; the database/auth health) are probed too, but their **URLs come
  from GitHub Actions secrets**, never this repo. Their results go to an **ephemeral `internal.json`**
  (git-ignored) that `alert.py` uses to email the operator. They **never appear on the page or in any
  committed file** (`alert_state.json` tracks them under opaque ids).

- **`alert.py`** — reads `checks.json` + `internal.json`, keeps a consecutive-failure counter in
  **`alert_state.json`**, and emails the operator via Resend on **2 consecutive failures** (debounces a
  transient) and again on recovery. A send is a no-op (state still tracked) when the mail secrets are absent.

- **`index.html`** — the static page; it fetches `checks.json` + `incidents.json` client-side. If the checks
  data is **older than 30 minutes** it shows **"Status unknown"** for every component rather than a stale
  "Operational".

- **`incidents.json`** — the human incident banner, editable from the GitHub phone app (set `status` to
  anything other than `operational` to raise a banner).

- **`.github/workflows/checks.yml`** — runs the checks on a schedule (`*/5`, GitHub's minimum) and commits any
  change. GitHub's scheduled runs are **best-effort** and can be **delayed or skipped** under load, so the page
  does not trust stale data (see the 30-minute guard above).

## GitHub Actions secrets (Settings → Secrets and variables → Actions)

Nothing secret is committed. Set these repository secrets:

| Secret | Purpose | Without it |
|---|---|---|
| `RESEND_API_KEY` | a **send-only** Resend key (restricted to the hepherus.com domain) for email alerts | alerts are tracked but **not emailed** |
| `ALERT_EMAIL_TO` | the operator's email (alert recipient) | alerts not emailed |
| `ALERT_EMAIL_FROM` | a verified Resend sender on hepherus.com (default `alerts@hepherus.com`) | uses the default |
| `DB_HEALTH_URL` | the database/auth health URL (internal; feeds Hepherus app + Sign-in and the email) | that signal shows unknown; the two components fall back to surface reachability |
| `ADMIN_HEALTH_URL` | the operator-console health URL (internal; email-only) | that email check is skipped |

The decrypt check uses a **public, unauthenticated** up/down endpoint — **no secret is needed** for it.

## Run locally

```
python3 check.py      # writes checks.json (+ an ephemeral internal.json; internal checks need the two URL vars)
python3 alert.py      # writes alert_state.json; emails only if RESEND_API_KEY + ALERT_EMAIL_TO are exported
```
