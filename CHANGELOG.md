# Changelog

## 2.0.0

First public release of Strata.

- Three-tier LLM routing (local, free API, premium API) with circuit breaker, masking, paid-tier approval, monthly budget and per-call cost tracking.
- Built-in on-prem authentication (bcrypt, rotating refresh tokens, CSRF protection, lockout), with Supabase as an option.
- Generic roles: Admin, Department Head, Manager, Member, Guest.
- New Next.js 15 interface: overview, streaming assistant, library, cross-team access, admin console (people, models and cost, audit log, system), settings.
- Backend-for-frontend proxy, so the API stays on the private network.
- Production Docker Compose stack, non-root images, migrations job, JSON logging, CI.
