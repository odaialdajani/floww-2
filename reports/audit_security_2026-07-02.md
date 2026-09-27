# Security & Infrastructure Audit — floww
**Date:** 2026-07-02  
**Auditor:** Claude (automated static + config analysis)  
**Scope:** Backend (FastAPI/Python), Frontend (React), Docker/Compose, Azure Bicep infra, .env files, git history  
**Verdict:** ⛔ 3 CRITICAL issues require immediate action before any production exposure.

---

## Summary Table

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 3 | 🔴 Fix immediately |
| HIGH | 7 | 🟠 Fix within 24-48h |
| MEDIUM | 7 | 🟡 Fix this sprint |
| LOW | 4 | 🟢 Fix next cycle |

---

## CRITICAL Findings

---

### C-01 · Hardcoded JWT Signing Secret in Source Code
```
SEVERITY:    CRITICAL
TYPE:        HardcodedSecret / AuthBypass
FILE:        backend/routes/alphapod_compat.py
LINE:        327
```
**Description:**  
The `dev_token` endpoint signs JWTs with the literal byte string `b"floww-dev-secret"` hardcoded directly in source:
```python
hmac.new(b"floww-dev-secret", f"{header}.{payload}".encode(), hashlib.sha256).digest()
```
This endpoint is mounted under `/api/auth/` which is in `PUBLIC_PATHS` — meaning **no API key is required** to call it. Any caller can POST any `email` and `tier` (e.g. `"tier": "pro"` or `"tier": "admin"`) and receive a valid 30-day JWT. Because the signing secret is in version-controlled source code, it cannot be rotated without a code change and is permanently compromised in git history.

**Impact:** Complete authentication bypass. Anyone with read access to the repo can forge valid JWTs for any user at any tier.

**Remediation:**
1. Move the signing secret to an environment variable: `JWT_DEV_SECRET = os.environ.get("JWT_DEV_SECRET", "")`
2. If `JWT_DEV_SECRET` is empty, return HTTP 404 or 403 so the endpoint is inert in production
3. Gate the entire endpoint behind an `ENVIRONMENT == "development"` check
4. Rotate the secret — any token signed with `floww-dev-secret` should be considered invalid

---

### C-02 · Live API Keys in Plaintext .env Files on Disk
```
SEVERITY:    CRITICAL
TYPE:        HardcodedSecret / CredentialExposure
FILE:        backend/.env, .env (root)
LINE:        N/A (whole file)
```
**Description:**  
Both `.env` files exist on disk with real, active credentials. While gitignored (confirmed `git ls-files` returned errors for both), they are:
- Readable by any process running as the same OS user
- At risk if the machine is ever accessed by another person, shared, imaged, or backed up to cloud storage
- Likely mirrored in any AI coding assistant context (this session read them)

**`backend/.env` — live keys found:**
| Variable | Value prefix | Service |
|----------|-------------|---------|
| `FINNHUB_API_KEY` | `d84ic5pr01...` | Finnhub market data |
| `POLYGON_API_KEY` | `NT_RXlF92z...` | Polygon.io |
| `DATABENTO_API_KEY` | `db-PBRQ7ia...` | Databento (paid per query) |
| `FLASHALPHA_API_KEY` | `wq0ZTRntx...` | FlashAlpha |
| `OPENROUTER_API_KEY` | `sk-or-v1-800005...` | OpenRouter LLM (paid per token) |
| `CVSERVER_API_KEY` | `cv_live_aLarOndc...` | ConvexValue (live prefix) |

**`.env` (root) — live key found:**
| Variable | Value prefix | Service |
|----------|-------------|---------|
| `CVSERVER_API_KEY` | `cv_live_aLarOndc...` | ConvexValue |

**Side note:** `ALPHA_VANTAGE_KEY` value `cDNhZUJ5bXh0...` appears to be Base64-encoded. Decode it to verify the actual key — Base64 is encoding, not encryption.

**Remediation:**
1. **Rotate all keys above immediately** — assume any key that has existed in a `.env` file on a developer machine is compromised
2. Use a secrets manager (1Password, AWS Secrets Manager, Azure Key Vault — already wired in the Bicep) for local dev via `op run` or equivalent
3. Consider using `direnv` + a secrets manager rather than raw `.env` files

---

### C-03 · Weak / Guessable API Secret Key in Dev Environment
```
SEVERITY:    CRITICAL
TYPE:        WeakCredential / AuthBypass
FILE:        backend/.env
LINE:        15
```
**Description:**  
```
API_SECRET_KEY=dev-local-testing-key
```
This key is the **only authentication** protecting all mutating HTTP routes (POST/PUT/DELETE/PATCH that aren't in `PUBLIC_PATHS`). The value `dev-local-testing-key` is:
- A dictionary-guessable string
- Likely reused across developer machines ("dev" convention)
- If this `.env` ever reaches staging or production it unlocks the entire API

**Remediation:**
1. Generate a cryptographically random key: `python -c "import secrets; print(secrets.token_urlsafe(32))"`
2. Add a startup check: if `API_SECRET_KEY` is shorter than 32 characters or matches known weak values, refuse to start
3. Never share the same key between dev/staging/production

---

## HIGH Findings

---

### H-01 · Grafana Admin Password Hardcoded as "admin"
```
SEVERITY:    HIGH
TYPE:        HardcodedSecret / WeakCredential
FILE:        docker-compose.observability.yml, line 43
            docker-compose.prod.yml, line 82 (default)
```
**Description:**  
Observability compose hardcodes `GF_SECURITY_ADMIN_PASSWORD=admin`. The production compose uses `${GRAFANA_PASSWORD:-admin}`, defaulting to `admin` if the env var is unset. Grafana at the default admin/admin exposes all dashboards, data source credentials, and the ability to add/modify alert rules.

**Remediation:**
1. In `docker-compose.observability.yml`: replace with `${GRAFANA_PASSWORD}` (no default — fail loudly if unset)
2. Set `GRAFANA_PASSWORD` to a strong random value in your local `.env` and in the production secrets manager
3. Enable Grafana's anonymous auth disable (`GF_AUTH_ANONYMOUS_ENABLED=false`) explicitly

---

### H-02 · Broker Account/Position GET Routes Unprotected
```
SEVERITY:    HIGH
TYPE:        AuthBypass / InformationDisclosure
FILE:        backend/routes/schwab.py (all GET routes)
            backend/routes/alpaca.py (all GET routes)
```
**Description:**  
The auth middleware (`verify_api_key`) only runs for `PROTECTED_METHODS = {"POST", "PUT", "DELETE", "PATCH"}`. GET requests are allowed through with no authentication check unless the path is in `PUBLIC_PATHS`. None of the broker paths are in `PUBLIC_PATHS`, but they're all GET routes:

| Endpoint | Data Exposed |
|----------|-------------|
| `GET /api/schwab/accounts` | All Schwab account numbers & balances |
| `GET /api/schwab/positions/{account_hash}` | Full position holdings |
| `GET /api/schwab/sweeps/{account_hash}` | Cash sweep history |
| `GET /api/alpaca/account` | Alpaca account info & buying power |
| `GET /api/alpaca/positions` | All open positions |
| `GET /api/alpaca/orders` | Order history |

Any unauthenticated caller can enumerate account data.

**Remediation:**
```python
# Add to each route in schwab.py and alpaca.py:
from auth import get_api_key
from fastapi import Depends

async def _require_read_auth(request: Request) -> bool:
    api_key = request.headers.get("X-API-Key", "")
    expected = get_api_key()
    if not expected or api_key != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True

@router.get("/schwab/accounts")
async def schwab_accounts(_: bool = Depends(_require_read_auth)):
    ...
```
Or extend `PROTECTED_METHODS` to include `"GET"` for sensitive prefixes via middleware path matching.

---

### H-03 · `GET /api/errors/summary` Publicly Accessible
```
SEVERITY:    HIGH
TYPE:        AuthBypass / InformationDisclosure
FILE:        backend/routes/admin.py
LINE:        36-42
```
**Description:**  
The `errors_summary` route has no auth dependency and GET is not in `PROTECTED_METHODS`:
```python
@router.get("/errors/summary")
async def errors_summary():   # ← no Depends(_require_admin_auth)
    from server import db
    errors = db.errors.find(...).sort("ts", -1).limit(100)
    return {"errors": await errors.to_list(length=100)}
```
Error documents in MongoDB likely contain stack traces, internal file paths, exception messages, and potentially fragments of request data — useful for attackers doing reconnaissance.

**Remediation:**
```python
@router.get("/errors/summary")
async def errors_summary(_: bool = Depends(_require_admin_auth)):
```

---

### H-04 · Production Docker Build Target Does Not Exist
```
SEVERITY:    HIGH
TYPE:        InfrastructureMisconfiguration / DeployBlocker
FILE:        docker-compose.prod.yml, line 38
            Dockerfile.backend (entire file)
```
**Description:**  
`docker-compose.prod.yml` specifies:
```yaml
build:
  dockerfile: Dockerfile.backend
  target: production
```
`Dockerfile.backend` is a **single-stage** build with no named targets. Running `docker compose -f docker-compose.prod.yml up --build` will fail with:
```
failed to solve: target stage "production" could not be found
```
Production deploys are broken.

**Remediation:**
```dockerfile
# Dockerfile.backend — add a production target
FROM python:3.11-slim AS base
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ .
RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser
EXPOSE 8000
HEALTHCHECK ...

FROM base AS production
ENV PYTHONDONTWRITEBYTECODE=1
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000", \
     "--log-level", "warning", "--workers", "2"]
```

---

### H-05 · CORS Set to Wildcard `*` in Dev Docker Compose
```
SEVERITY:    HIGH
TYPE:        CORSMisconfiguration
FILE:        docker-compose.yml, line 21
```
**Description:**  
```yaml
- CORS_ORIGINS=*
```
The server itself enforces non-wildcard CORS in production/staging (will refuse to start if `CORS_ORIGINS` is unset). But the dev compose overrides this with `*`. If this compose is used to run a service that faces external traffic (e.g., developer sharing their machine via ngrok/Tailscale), all CORS protections are defeated.

**Remediation:**
```yaml
- CORS_ORIGINS=http://localhost:3000,http://localhost:8000
```

---

### H-06 · MongoDB Exposed to Host with No Authentication
```
SEVERITY:    HIGH
TYPE:        InfrastructureMisconfiguration / DataExposure
FILE:        docker-compose.yml, line 47-50
```
**Description:**  
```yaml
mongo:
  image: mongo:7
  ports:
    - "27017:27017"   # ← published to 0.0.0.0 on the host
```
MongoDB runs with no `--auth` flag and no `MONGO_INITDB_ROOT_USERNAME` / `MONGO_INITDB_ROOT_PASSWORD`. Port 27017 is bound to all host interfaces. If the developer machine has any port accessible externally (VPN, port forward, cloud dev box), the database is open to the world.

**Remediation:**
```yaml
mongo:
  image: mongo:7
  ports:
    - "127.0.0.1:27017:27017"   # bind to loopback only
  environment:
    MONGO_INITDB_ROOT_USERNAME: ${MONGO_USER}
    MONGO_INITDB_ROOT_PASSWORD: ${MONGO_PASSWORD}
```
Update `MONGO_URL` to include credentials: `mongodb://${MONGO_USER}:${MONGO_PASSWORD}@mongo:27017`.

---

### H-07 · `POST /api/errors/clear` Lacks Route-Level Auth Dependency
```
SEVERITY:    HIGH
TYPE:        AuthBypass
FILE:        backend/routes/admin.py
LINE:        55-60
```
**Description:**  
```python
@router.post("/errors/clear")
async def errors_clear():   # ← no Depends(_require_admin_auth)
```
While the global middleware does protect POST routes when `API_SECRET_KEY` is set, relying solely on middleware for destructive operations is fragile — any future refactor that changes middleware ordering or route prefix could silently un-protect this route. Defense-in-depth requires explicit auth on admin-destructive endpoints.

**Remediation:** Add `_: bool = Depends(_require_admin_auth)` to this route, matching the pattern used by every other route in admin.py.

---

## MEDIUM Findings

---

### M-01 · Prometheus & AlertManager Ports Publicly Exposed
```
SEVERITY:    MEDIUM
TYPE:        InfrastructureMisconfiguration / InformationDisclosure
FILE:        docker-compose.observability.yml, lines 8, 28
```
**Description:**  
Prometheus (`9090`) and AlertManager (`9093`) are bound to `0.0.0.0` with no authentication. Prometheus exposes all metric names, labels, and time series. AlertManager exposes alert routing config including any receiver webhook URLs.

**Remediation:**
```yaml
ports:
  - "127.0.0.1:9090:9090"
  - "127.0.0.1:9093:9093"
```
Access remotely via SSH tunnel if needed.

---

### M-02 · WebSocket Auth Bypass in Development Mode
```
SEVERITY:    MEDIUM
TYPE:        AuthBypass
FILE:        backend/auth.py, lines 107-110
```
**Description:**  
```python
expected = get_ws_token()
if not expected:
    # No token configured — allow (dev mode)
    return True
```
When `WS_API_TOKEN` is not set, all WebSocket connections are unconditionally accepted. If this backend ever faces the internet without `WS_API_TOKEN` configured, live trade tape, alerts, and ML signal streams are fully public.

**Remediation:**  
Add a startup check that logs a loud warning (or refuses to start in staging/production) when `WS_API_TOKEN` is empty. The HTTP API already does this (`API_SECRET_KEY not set → 503`); apply the same pattern to the WS token.

---

### M-03 · Azure Container Registry Admin User Enabled
```
SEVERITY:    MEDIUM
TYPE:        InfrastructureMisconfiguration / PrivilegeEscalation
FILE:        infra/azure/main.bicep, line ~192
```
**Description:**  
```bicep
properties: {
  adminUserEnabled: true
  // In production, disable public access and use private endpoint
```
ACR admin credentials (username + 2 passwords) are long-lived static secrets. They're being passed into the App Service via `acr.listCredentials()` — this means the credentials are embedded in the ARM deployment state and visible to anyone with access to the resource group. A compromise of ACR admin credentials allows pushing malicious container images.

**Remediation:**
1. Set `adminUserEnabled: false`
2. Use the App Service's System-Assigned Managed Identity + `AcrPull` RBAC role to pull images — this is already partially wired (the MSI is created in the bicep)
3. Remove the `DOCKER_REGISTRY_SERVER_USERNAME/PASSWORD` app settings and configure the App Service to use managed identity for ACR instead

---

### M-04 · Azure App Service Allows All IPs (Unfulfilled TODO)
```
SEVERITY:    MEDIUM
TYPE:        InfrastructureMisconfiguration
FILE:        infra/azure/main.bicep, lines 434-436
```
**Description:**  
```bicep
{
  action: 'Allow'
  ipAddress: '0.0.0.0/0'
  name: 'allow-all-temp'
  description: 'TODO: restrict to known IPs in production'
}
```
The `ipSecurityRestrictionsDefaultAction: 'Deny'` is in place, but this explicit `Allow 0.0.0.0/0` rule effectively negates it. The entire internet can reach the App Service. The TODO has not been acted upon.

**Remediation:** Replace `0.0.0.0/0` with actual allowed CIDR blocks (home IP, VPN IP, Caddy/CDN egress IPs). If the app is fully public-facing, remove the IP restriction entirely and rely on the application-layer auth — but document that choice explicitly.

---

### M-05 · `latest` Docker Image Tags in Production Compose
```
SEVERITY:    MEDIUM
TYPE:        SupplyChainRisk / NonDeterministicBuild
FILE:        docker-compose.prod.yml, lines 63, 70
```
**Description:**  
```yaml
prometheus:
  image: prom/prometheus:latest
grafana:
  image: grafana/grafana:latest
```
Using `latest` in production means `docker compose pull` on different dates pulls different versions. A breaking change or a supply-chain compromise in upstream images would silently affect the deployment.

**Remediation:** Pin to specific digests or at minimum specific version tags (already done in observability compose — `prom/prometheus:v3.2.1`, `grafana/grafana:11.6.0`). Use those same pinned versions in prod.

---

### M-06 · Content-Security-Policy Allows `unsafe-eval`
```
SEVERITY:    MEDIUM
TYPE:        SecurityHeaderWeakness
FILE:        infra/caddy/Caddyfile, line 21
```
**Description:**  
```
Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; ..."
```
`'unsafe-eval'` enables `eval()`, `setTimeout(string)`, and `new Function()`. Combined with `'unsafe-inline'`, CSP provides almost no XSS protection. An XSS vulnerability anywhere in the React app can execute arbitrary code.

**Remediation:**  
React production builds do not require `unsafe-eval`. Remove it. Replace `'unsafe-inline'` with a nonce-based or hash-based CSP. Test with `report-uri` before enforcing.

---

### M-07 · Grafana Production Root URL Set to HTTP Localhost
```
SEVERITY:    MEDIUM
TYPE:        InfrastructureMisconfiguration
FILE:        docker-compose.prod.yml, line 83
```
**Description:**  
```yaml
- GF_SERVER_ROOT_URL=http://localhost:3000
```
In production (where Grafana is behind Caddy with HTTPS), this misconfigures Grafana's redirect URLs and can cause session cookie `Secure` flag issues and mixed-content warnings.

**Remediation:**
```yaml
- GF_SERVER_ROOT_URL=https://${DOMAIN}/grafana
```

---

## LOW Findings

---

### L-01 · Azure Monitor Instrumentation Key Exposed in Bicep Output
```
SEVERITY:    LOW
TYPE:        InformationDisclosure
FILE:        infra/azure/main.bicep (outputs section)
```
**Description:**  
```bicep
output monitorInstrumentationKey string = monitor.properties.InstrumentationKey
```
The Application Insights instrumentation key is output as a plain string in the ARM deployment output. Anyone with `Microsoft.Resources/deployments/read` on the resource group can retrieve it. Instrumentation keys can be used to inject fake telemetry.

**Remediation:** Mark the output `@secure()`:
```bicep
@secure()
output monitorInstrumentationKey string = monitor.properties.InstrumentationKey
```
Or better: switch to connection-string based auth for App Insights (the modern approach) and store it in Key Vault.

---

### L-02 · ALPHA_VANTAGE_KEY Uses Base64 Obfuscation (Not Encryption)
```
SEVERITY:    LOW
TYPE:        FalseSecuritySense
FILE:        backend/.env, line 3
```
**Description:**  
```
ALPHA_VANTAGE_KEY=<REDACTED 2026-09-27 — was a live Base64-encoded key>
```
Decoding this Base64 string reveals the actual API key. This is not encryption — it is trivially reversible. If this was done to "hide" the key from casual viewing, it provides no real protection and may create a false sense of security.

**Remediation:** Store the raw key in the secrets manager and remove the base64 wrapper. If the key value is itself base64 (some APIs use this format), document it clearly so it's not confused with obfuscation.

---

### L-03 · Dev-Token Endpoint Accessible in All Environments
```
SEVERITY:    LOW
TYPE:        InformationDisclosure / AuthBypass (conditional)
FILE:        backend/routes/alphapod_compat.py, line 302
```
**Description:**  
Beyond the hardcoded secret (covered in C-01), the endpoint itself is mounted unconditionally — there's no environment check. Even after rotating the signing secret to an env var, the endpoint remains reachable in production unless explicitly gated.

**Remediation:**
```python
import os
if os.environ.get("ENVIRONMENT", "development") == "development":
    @router.post("/auth/dev-token")
    async def dev_token(...):
        ...
```
Or use a startup hook to remove the route if not in development mode.

---

### L-04 · `scripts/` Directory Contains Python Processes That Hit Live APIs
```
SEVERITY:    LOW
TYPE:        OperationalRisk
FILE:        scripts/ (various .py files)
```
**Description:**  
Scripts like `train_production.py`, `warm_cache.py`, `compute_qqq_features.py` load from `backend/.env` and make authenticated calls to paid APIs (Polygon, Databento). Running these scripts accidentally in a CI environment, or by another developer who inherited the repo, would consume paid quota or trigger suspicious activity alerts.

**Remediation:**  
Add a `DRY_RUN=1` guard at the top of any script that calls external APIs. Ensure scripts print which env they're using before making requests. Consider adding `if __name__ == "__main__"` guards and documenting the expected env in a comment header.

---

## Infrastructure Positives (What's Done Well)
These were explicitly checked and found to be correctly implemented:

- ✅ **Non-root Docker users** — both `Dockerfile.backend` and `Dockerfile.frontend` create and switch to non-root `appuser`
- ✅ **Key Vault integration in Azure Bicep** — secrets are referenced via `@Microsoft.KeyVault(SecretUri=...)` rather than inline values
- ✅ **HTTPS-only App Service** — `httpsOnly: true` enforced in bicep
- ✅ **TLS 1.2 minimum** — `minTlsVersion: '1.2'` set on App Service
- ✅ **FTPS disabled** — `ftpsState: 'Disabled'` in App Service
- ✅ **HTTP/2 enabled** — `http2Enabled: true`
- ✅ **Auth fail-closed** — `API_SECRET_KEY` absent → 503 (not open)
- ✅ **Rate limiting middleware** — per-IP sliding window in `server.py`
- ✅ **Security headers via Caddy** — HSTS, X-Frame-Options, X-Content-Type-Options, Referrer-Policy all set
- ✅ **CORS non-wildcard enforced in production** — server refuses to start if `CORS_ORIGINS` is unset in prod/staging
- ✅ **`.env` properly gitignored** — confirmed `git ls-files` does not track any `.env` files
- ✅ **Admin trading routes gated with 2FA** — `trading_transition` requires TOTP + email code
- ✅ **Circuit breaker on live trading** — `main_breaker` pattern exists
- ✅ **MongoDB private endpoint in Azure** — Cosmos DB has a private endpoint configured in bicep
- ✅ **Key Vault network ACL** — `defaultAction: 'Deny'` with VNet whitelist

---

## Remediation Priority Order

| # | Finding | Effort | Impact |
|---|---------|--------|--------|
| 1 | C-01: Rotate hardcoded JWT secret | 30 min | Auth bypass closed |
| 2 | C-02: Rotate all live API keys | 1 hour | Credential exposure closed |
| 3 | C-03: Generate strong API_SECRET_KEY | 5 min | Weak auth closed |
| 4 | H-02: Add auth to broker GET routes | 1 hour | Account data protected |
| 5 | H-03/H-07: Add auth to errors routes | 15 min | Error data protected |
| 6 | H-01: Fix Grafana passwords | 10 min | Admin panel secured |
| 7 | H-04: Fix Dockerfile multi-stage build | 30 min | Prod deploys unblocked |
| 8 | H-06: Add MongoDB auth + loopback bind | 30 min | DB secured |
| 9 | H-05: Fix CORS to explicit origins | 5 min | CORS locked down |
| 10 | M-01: Bind Prometheus/AM to 127.0.0.1 | 5 min | Metrics private |
| 11 | M-03: Disable ACR admin user | 30 min | Registry secured |
| 12 | M-04: Resolve Azure IP restriction TODO | 15 min | Infra hardened |
| 13 | M-05: Pin Docker image tags in prod | 10 min | Build deterministic |

---

*Report generated by automated static analysis. Manual penetration testing recommended before production deployment.*
