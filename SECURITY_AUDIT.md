# Production security audit

Static review only; no live deployment, outbound messages, paid searches, or test execution performed.

## Deployment gates

- Configure REDIS_URL on the API service for shared throttles; DRF throttles are best-effort, not atomic hard quotas. Configure edge rate limiting and verify API_NUM_PROXIES against actual proxy topology.
- AUTH_TOKEN_TTL_HOURS defaults to 24. Login rotates the single token per user, invalidating other devices. Existing expired tokens require sign-in. Logout revokes the token if the server is reachable. Browser localStorage remains an XSS exposure; migrate to a carefully designed HttpOnly cookie/session architecture in a separate change with CSRF and cross-origin testing.
- Crawler pins validated public IPs and verifies HTTPS hostname; test IPv6, redirects, robots and network egress. Enforce private-network denial at infrastructure level too.
- Keep OUTREACH_ENABLED=false until provider and approval tests pass. Manual submission is a user attestation, not automatic sending. Review recipient changes after approval, per-lead limits, and concurrent proposal editing/sending before enabling email.
- Public health reports operational metadata; decide whether to separate readiness and authenticated diagnostics. Global discovery strategy metrics and supervisor lease expiry need further tenant/concurrency review.
- Run backend tests, frontend build, dependency vulnerability scans, migration checks and staging smoke tests. Review CI before merge. No production settings or secrets were changed remotely.
