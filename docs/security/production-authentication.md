# Production authentication

ProductOS uses OIDC access tokens signed with RS256. The API retrieves and caches the issuer JWKS, verifies signature, issuer, audience, expiry, issued-at time, and subject, then requires UUID-valued user and tenant claims. Request body or query scopes cannot override those claims.

Production startup fails when authentication is disabled. `/health` remains unauthenticated for infrastructure probes; all `/v1/*` routes require a bearer token. Browser login uses Authorization Code with PKCE and stores the access token in session storage. The API remains the enforcement boundary.

The SPA discards expired tokens and clears its local session on an API 401. Deploy it with a restrictive Content Security Policy, no unreviewed third-party scripts, secure HTTPS-only hosting, and short access-token lifetimes. Session storage reduces persistence but does not mitigate script injection; XSS prevention remains mandatory.

Required claims:

- `sub`: provider identity
- `productos_user_id`: ProductOS user UUID, configurable with `PRODUCTOS_OIDC_USER_CLAIM`
- `productos_tenant_id`: ProductOS organization UUID, configurable with `PRODUCTOS_OIDC_TENANT_CLAIM`
- `scope`: space-separated workload scopes where applicable

The proactive CronJob requires `productos:scheduler`; representative evaluation execution requires `productos:evaluator`. `productos:admin` satisfies either workload boundary. Human interactive tokens should not receive workload scopes by default.

The configured user UUID is a stable ProductOS identity and must not be reassigned to another person. The tenant claim selects the active organization scope. Tenant-owned records—including knowledge, management intelligence, artifacts, traces, proactive state, and evaluations—are filtered by both claims; personal conversation and memory records remain user-scoped by design.

Never place access tokens, client secrets, model keys, or JWKS private keys in the repository, image, ConfigMap, logs, or trace attributes. Use a managed secret store and short-lived workload identity. Rotate signing keys through the issuer JWKS and retain an overlap window during rotation.
