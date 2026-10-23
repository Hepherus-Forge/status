# status

Hepherus status &amp; alert page (D-2208). A **static** status site hosted on GitHub Pages — deliberately
outside the main host, so it stays up when the app is down.

## What it does

- **`check.py`** — a stdlib-only runner (no dependencies) that probes each surface and writes **`checks.json`**:
  - App (`app.hepherus.com`)
  - Backend (`api.hepherus.com/version`)
  - Admin (`admin.hepherus.com`)
  - **Supabase** (`/auth/v1/health` reachability — a 401 counts as up: the host answered)
  - Connector (`api.hepherus.com/connector`)
  - Sign-in page (`app.hepherus.com/sign-in`)
  - **Decrypt service** — a real end-to-end KMS unwrap self-test via `POST api.hepherus.com/internal/kms-selftest`
    (PASS = HTTP 200 AND `roundtrip_ok==true` AND non-empty `sha`). It does **not** probe the Cloud Run service
    directly (that is auth-required + egress-IP-allowlisted). Shows **Unknown** until `INTERNAL_API_SECRET` is set.
- **`alert.py`** — reads `checks.json`, keeps a per-service consecutive-failure counter in **`alert_state.json`**,
  and emails Maestro via Resend on **2 consecutive failures** (debounces a cold start/transient) and again on
  recovery. A send is a no-op (state still tracked) when the mail secrets are absent.
- **`index.html`** — the static page; it fetches `checks.json` + `incidents.json` client-side and renders them.
  New services in `checks.json` appear automatically.
- **`incidents.json`** — the human incident banner, editable from the GitHub phone app (set `status` to anything
  other than `operational` to raise a banner).
- **`.github/workflows/checks.yml`** — runs the above every 5 minutes (GitHub's minimum; schedule is best-effort)
  and commits any change back to the repo.

## GitHub Actions secrets (Settings → Secrets and variables → Actions)

Nothing secret is committed. Set these repository secrets:

| Secret | Purpose | Without it |
|---|---|---|
| `INTERNAL_API_SECRET` | the backend self-test secret for the decrypt check | Decrypt line shows **Unknown** |
| `RESEND_API_KEY` | Resend API key for email alerts | alerts are tracked but **not emailed** |
| `ALERT_EMAIL_TO` | Maestro's email (alert recipient) | alerts not emailed |
| `ALERT_EMAIL_FROM` | verified Resend sender (default `alerts@hepherus.com`) | uses the default |

`INTERNAL_API_SECRET` must also be recorded in the secrets register as living on GitHub (T810 §1b).

## Run locally

```
python3 check.py      # writes checks.json (decrypt = Unknown unless INTERNAL_API_SECRET is exported)
python3 alert.py      # writes alert_state.json; emails only if RESEND_API_KEY + ALERT_EMAIL_TO are exported
```
