# Security policy

## Reporting a vulnerability

Please don't open a public issue. Use GitHub's private vulnerability reporting ("Security" tab, then "Report a vulnerability") with steps to reproduce and the affected version. We aim to acknowledge reports within 3 working days.

## Design summary

- Data stays on-prem by default: the local model answers first, and external tiers receive financially masked text only.
- Files are encrypted at rest (Fernet / AES-128-CBC + HMAC) with rotatable keys.
- Passwords use bcrypt (12 rounds). Sessions use httpOnly SameSite cookies, short-lived access tokens, rotating refresh tokens, a CSRF header requirement and login lockout.
- RBAC is enforced in SQL on every file and chunk query; other departments' files return 404, never 403.
- Per-role rate limits, prompt-injection neutralization, magic-byte upload validation and a size limit.
- Every action is audit-logged, and the log can be exported by admins.
- API docs are disabled when `ENVIRONMENT=production`. Errors never return stack traces.
