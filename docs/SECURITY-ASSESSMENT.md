# Security assessment: minutes.kevinle.tech

Date: 2026-10-01. Assessment of minutes.kevinle.tech, authorized by Kevin Le, the site owner.
Scope: the live site at https://minutes.kevinle.tech, the host it runs on, and this
repository at the deployed commit.

## Summary

No critical or high findings remain. Four issues found during the assessment were fixed and
redeployed the same day. The site exposes only an HTTPS website through Cloudflare; the
host opens no inbound ports.

| # | Finding | Severity | Status |
|---|---|---|---|
| 1 | Passwords built around a common word plus a year (for example `Summer2024!!xy`) passed the rules | Medium | Fixed: such passwords are rejected |
| 2 | Content-Security-Policy allowed inline styles (`style-src 'unsafe-inline'`) | Medium (ZAP) | Fixed: `style-src 'self'`, every page checked for violations |
| 3 | Cross-Origin-Embedder-Policy header missing | Low (ZAP) | Fixed: `require-corp` when Turnstile is off |
| 4 | Per-network sign-in limit (20 attempts in 10 minutes) could lock out a whole campus behind one IP | Low (availability) | Fixed: 30 failures or 120 attempts in 10 minutes per network; per-account lockout unchanged |
| 5 | Static files are cached by Cloudflare | Informational | Expected; they are public build files with no user data |

## Method

1. **Edge and transport.** Plain HTTP redirects to HTTPS (301). TLS 1.0 and 1.1 are refused;
   TLS 1.2 and 1.3 only. HSTS is set for a year.
2. **Headers on pages, API, and static files.** CSP (no inline script or style, no frames,
   `frame-ancestors 'none'`), X-Frame-Options, nosniff, Referrer-Policy, Permissions-Policy,
   COOP, CORP, COEP. The `Server` header shows only Cloudflare.
3. **Unauthenticated access.** All 67 protected API operations were called without signing
   in; every one answered 401. API documentation (`/api/docs`, `/api/openapi.json`, `/redoc`,
   `/docs`) is not served.
4. **CSRF.** State-changing requests without the `X-Live-Minutes` header and cross-site form
   posts are refused (403).
5. **Path traversal and file disclosure.** Ten encoded and plain traversal attempts
   (`/etc/passwd`, `.env`, `.git/config`, source files, `docker-compose.yml`, Windows paths)
   returned the app shell or 400, never file contents.
6. **Injection.** SQL injection strings in the login form and in path parameters were treated
   as data. Query text is not reflected by the server, and React escapes all output.
7. **Uploads and tokens.** A 3 MB unauthenticated upload was refused before reading (413).
   Forged capture tokens are refused (401) and repeated bad tokens are rate limited.
8. **Accounts.** Weak, common, and breached passwords are refused. Disposable email domains
   and domains with no mail server are refused. Five wrong passwords pause the account
   (then 429). Unknown accounts get the same answers and timing as real ones. Sign-in
   limits use the real client IP from Cloudflare, not the tunnel's address.
9. **Redirects and hosts.** SSO `next` values pointing off-site are not followed. A foreign
   `Host` header does not reach the app.
10. **Errors.** Unknown paths and malformed JSON return short errors with no stack traces.
11. **Host.** Only `127.0.0.1:8000` listens on the machine; PostgreSQL is not published. The
    web and worker containers run as an unprivileged user (uid 10001). The image contains no
    `.env` file and no secrets in its layers or environment. The mail login was confirmed
    without sending any email.
12. **OWASP ZAP baseline** (passive scan of the live site): 0 failures, 63 rules passed, and
    only the informational cache notes above.
13. **Code and dependencies** (CI on every push): 43 automated tests including a check that
    every route needs sign-in, pip-audit, npm audit, Bandit, Semgrep, Gitleaks over the full
    history, and Grype on the built image. All clean at the deployed commit.

During the account checks, one probe sign-up used a password that the old rules allowed and
created an unconfirmed account at an outside address. It was deleted along with its queued
email before any mail was sent, and that gap is finding 1.

## Recommendations

1. Done 2026-10-01: Cloudflare Turnstile is on for sign-up, sign-in, and password reset.
   Requests without a valid check are refused by the server, and the widget loads under the
   strict CSP with no violations. Cloudflare's own Web Analytics beacon is blocked by the CSP,
   which keeps third-party analytics off this site.
2. In Cloudflare, add a rate limiting rule for `/api/auth/*` and keep the free managed WAF
   rules on.
3. Back up the database and `.env` regularly. The site runs on one PC, so keep it updated
   and awake during meetings.
4. Before district handover, repeat this assessment on the district's deployment and invite
   district IT to run their own scan.
