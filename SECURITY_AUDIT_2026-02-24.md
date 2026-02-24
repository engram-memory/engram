# Engram SaaS Security Audit Report

**Date:** 2026-02-24
**Auditor:** Claude (Opus 4.6) — Security Reviewer Skill
**Scope:** Full server codebase (`/home/levent/engram/server/`)
**Target:** FastAPI REST API, Stripe Billing, JWT Auth, API Keys, WebSocket

---

## Executive Summary

Engram hat eine solide Basis (Argon2 Passwort-Hashing, parameterisierte SQL-Queries, Tenant-Isolation im Cloud-Mode), aber **3 kritische und 4 hochgradige Schwachstellen** die sofort behoben werden müssen — vor allem im Billing und Auth Bereich.

| Severity | Count |
|----------|-------|
| CRITICAL | 3 |
| HIGH     | 4 |
| MEDIUM   | 3 |
| LOW      | 3 |
| INFO     | 2 |
| **Total** | **15** |

---

## CRITICAL Findings

### C1: Stripe Webhook ohne Signatur-Verifizierung

**Datei:** `server/billing/routes.py:248-263`
**CVSS:** 9.8 (Critical)
**CWE:** CWE-345 (Insufficient Verification of Data Authenticity)

```python
WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")  # LEER!

# Zeile 253-263:
if WEBHOOK_SECRET:
    # ... Signatur wird geprüft
else:
    # Dev/test mode: parse without signature verification
    event = stripe.Event.construct_from(json.loads(payload), stripe.api_key)
```

**Impact:** Jeder kann gefälschte Webhook-Events an `/v1/billing/webhook` senden:
- Sich selbst kostenlos auf "enterprise" upgraden
- Andere User downgraden
- Fake-Accounts mit beliebigem Tier erstellen

**Fix:**
```python
WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
if not WEBHOOK_SECRET:
    raise RuntimeError("STRIPE_WEBHOOK_SECRET must be set! Get it from Stripe Dashboard → Webhooks.")
```

---

### C2: JWT Default Secret im Produktionscode

**Datei:** `server/auth/jwt_handler.py:11-12`
**CVSS:** 9.1 (Critical)
**CWE:** CWE-798 (Use of Hard-Coded Credentials)

```python
_DEFAULT_SECRET = "engram-dev-secret-change-in-production"
_SECRET = os.environ.get("ENGRAM_JWT_SECRET", _DEFAULT_SECRET)
```

**Impact:** Wenn `ENGRAM_JWT_SECRET` nicht gesetzt ist, kann jeder:
- JWT Tokens für beliebige User fälschen
- Sich als Enterprise-User ausgeben
- Auf alle Memories zugreifen

Die Warnung auf Zeile 15-25 loggt nur — **verhindert den Start nicht**.

**Fix:**
```python
_SECRET = os.environ.get("ENGRAM_JWT_SECRET")
if not _SECRET:
    if os.environ.get("ENGRAM_CLOUD_MODE", "").lower() in ("1", "true", "yes"):
        raise RuntimeError("ENGRAM_JWT_SECRET MUST be set in cloud mode!")
    _SECRET = "engram-local-dev-only"  # Nur für lokalen Modus
```

---

### C3: API Key Scopes werden nie enforced

**Datei:** `server/auth/dependencies.py:86-88` + alle Endpoints
**CVSS:** 8.8 (High→Critical wegen Business Impact)
**CWE:** CWE-862 (Missing Authorization)

```python
# JWT Auth gibt IMMER alle Scopes:
scopes=["memories:read", "memories:write", "memories:admin"]

# API Key Scopes werden aus DB geladen, aber...
# KEIN EINZIGER ENDPOINT prüft die Scopes!
```

**Impact:** Ein API Key mit nur `memories:read` kann trotzdem:
- Memories löschen (`DELETE /v1/memories/{id}`)
- Memories schreiben (`POST /v1/memories`)
- Andere API Keys erstellen (`POST /v1/auth/keys`)

**Fix:** Scope-Check Dependency hinzufügen:
```python
def require_scope(scope: str):
    def checker(user: AuthUser = Depends(require_auth)):
        if scope not in user.scopes:
            raise HTTPException(403, f"Missing scope: {scope}")
        return user
    return checker

# Usage:
@app.delete("/v1/memories/{memory_id}")
def delete_memory(user: AuthUser = Depends(require_scope("memories:write"))):
    ...
```

---

## HIGH Findings

### H1: WebSocket Endpoint ohne Authentication

**Datei:** `server/api.py:720-727`
**CVSS:** 7.5
**CWE:** CWE-306 (Missing Authentication for Critical Function)

```python
@app.websocket("/v1/ws/{namespace}")
async def ws_endpoint(websocket: WebSocket, namespace: str):
    await manager.connect(websocket, namespace)  # Keine Auth-Prüfung!
```

**Impact:** Jeder kann sich auf beliebige Namespaces verbinden und:
- Echtzeit-Events mitlesen (memory_stored, memory_deleted, etc.)
- Sehen wenn andere User Memories speichern/löschen

**Fix:**
```python
@app.websocket("/v1/ws/{namespace}")
async def ws_endpoint(websocket: WebSocket, namespace: str):
    # Auth via query parameter oder first message
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001, reason="Auth required")
        return
    payload = decode_token(token)
    if not payload:
        await websocket.close(code=4001, reason="Invalid token")
        return
    await manager.connect(websocket, namespace)
    ...
```

---

### H2: Registration ohne Rate Limiting → Trial Abuse

**Datei:** `server/auth/routes.py:33-51`
**CVSS:** 7.1
**CWE:** CWE-770 (Allocation of Resources Without Limits)

```python
@router.post("/register", response_model=TokenResponse)
def register(body: RegisterRequest):
    # Keine Rate-Limiting Prüfung!
    # Jeder bekommt automatisch 7 Tage Pro-Trial
    trial_end = (datetime.now(timezone.utc) + timedelta(days=TRIAL_DAYS)).isoformat()
    db.create_user(user_id, body.email, pw_hash, tier="pro", trial_end=trial_end)
```

**Impact:** Attacker kann:
- Tausende Accounts mit Wegwerf-Emails registrieren
- Jeder bekommt 7 Tage kostenlosen Pro-Zugang (250K Memories, Semantic Search)
- Keine Email-Verifizierung erforderlich

**Fix:**
1. Rate-Limit auf `/v1/auth/register` (z.B. 3/Stunde pro IP)
2. Email-Verifizierung vor Trial-Aktivierung
3. Captcha oder Proof-of-Work

---

### H3: Login ohne Brute-Force Protection

**Datei:** `server/auth/routes.py:54-68`
**CVSS:** 7.0
**CWE:** CWE-307 (Improper Restriction of Excessive Authentication Attempts)

```python
@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest):
    user = db.get_user_by_email(body.email)
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(401, "Invalid email or password")
    # Keine Zählung fehlgeschlagener Versuche!
```

**Impact:** Unbegrenzte Passwort-Versuche pro Account.

**Fix:** Account Lockout nach N fehlgeschlagenen Versuchen:
```python
_failed_attempts: dict[str, int] = defaultdict(int)
MAX_ATTEMPTS = 5
LOCKOUT_MINUTES = 15

# In login():
if _failed_attempts[body.email] >= MAX_ATTEMPTS:
    raise HTTPException(429, f"Account locked. Try again in {LOCKOUT_MINUTES} minutes.")
```

---

### H4: Activate Endpoint ohne Auth → Session ID Enumeration

**Datei:** `server/billing/routes.py:125-180`
**CVSS:** 6.5
**CWE:** CWE-200 (Exposure of Sensitive Information)

```python
@router.get("/activate")
def activate(session_id: str = Query(...)):
    # Keine Authentication!
    session = stripe.checkout.Session.retrieve(session_id)
```

**Impact:**
- Stripe Session IDs sind erratbar (`cs_test_...` oder `cs_live_...`)
- Error Messages leaken User-Existenz ("API key was already issued")
- Ein Angreifer kann gültige Sessions brute-forcen

**Fix:** Rate-Limit + generische Error Messages + One-Time-Token statt Session ID.

---

## MEDIUM Findings

### M1: CORS allow_headers=["*"]

**Datei:** `server/api.py:67`

`allow_headers=["*"]` erlaubt beliebige Custom Headers. Sollte auf die tatsächlich benötigten beschränkt werden:
```python
allow_headers=["Authorization", "X-API-Key", "X-Namespace", "Content-Type"]
```

### M2: In-Memory Rate Limiter nicht persistent

**Datei:** `server/middleware.py`

- Server-Restart resettet alle Rate-Limits
- Kein Schutz bei Multiple Instances
- **Fix:** Redis-basierter Rate Limiter oder SQLite-basiert

### M3: Local Mode = Enterprise Access

**Datei:** `server/auth/dependencies.py:125-130`

Wenn `ENGRAM_CLOUD_MODE` nicht gesetzt ist, bekommt JEDER Request `tier="enterprise"` ohne Auth.
Gefährlich wenn jemand den Server versehentlich ohne Cloud-Mode auf einem öffentlichen Port startet.

---

## LOW Findings

### L1: Bind to 0.0.0.0

**Datei:** `server/api.py:738` — Hinter Cloudflare Tunnel kein direktes Risiko, aber sollte auf `127.0.0.1` geändert werden.

### L2: API Key Expiry nicht enforced

**Datei:** `server/auth/api_keys.py` — `expires_at` Spalte existiert in DB, wird bei Validierung nie geprüft. Keys leben ewig.

### L3: Demo Endpoint — keine Content-Sanitization

**Datei:** `server/demo_routes.py` — User-Content wird gespeichert ohne Sanitization. XSS-Risiko wenn Frontend den Content rendert.

---

## INFO

### I1: Stripe Test Keys in .env

Die `.env` Datei enthält Stripe TEST Keys. Nicht in Git committed (`.gitignore` schützt), aber lokale Datei existiert. **Wenn live:** Sicherstellen dass Live-Keys NUR via Environment Variables gesetzt werden, nie in Dateien.

### I2: Bandit SAST — 1 Finding

`server/api.py:738` — Binding to all interfaces (CWE-605). Bereits in L1 erfasst.

---

## Positiv — Was gut gemacht ist

| Feature | Status |
|---------|--------|
| Passwort-Hashing | Argon2id — State of the Art |
| SQL Queries | Parameterisiert — kein SQL Injection |
| API Key Storage | SHA256-Hashed, Prefix-Only Display |
| Tenant Isolation | Separate SQLite DBs pro User (Cloud Mode) |
| JWT Token Expiry | 15min Access, 7d Refresh — angemessen |
| Demo Endpoint | Rate-Limited, Content-Length-Limited |
| CORS Origins | Auf eigene Domains beschränkt (engram-ai.dev) |
| Stripe Idempotency | Checkout-Session-basierte Key-Issuance |

---

## Prioritisierte Empfehlungen

### SOFORT (vor nächstem Deploy)
1. **STRIPE_WEBHOOK_SECRET setzen** — Stripe Dashboard → Webhooks → Signing Secret
2. **JWT Secret enforced** — Crash bei fehlendem Secret in Cloud-Mode
3. **Scope Enforcement** — Middleware die Scopes auf Endpoints prüft

### DIESE WOCHE
4. **WebSocket Auth** — Token-basierte Auth für WS Connections
5. **Registration Rate Limit** — IP-basiert, max 3/Stunde
6. **Login Brute-Force Protection** — Account Lockout nach 5 Fehlversuchen
7. **CORS Headers einschränken** — Explizite Header-Liste

### NÄCHSTE WOCHE
8. **API Key Expiry enforced** — `expires_at` in validate_api_key prüfen
9. **Redis Rate Limiter** — Persistent, multi-instance ready
10. **Email-Verifizierung** — Vor Trial-Aktivierung

---

*Report generiert am 2026-02-24 von Claude Opus 4.6 mit security-reviewer + tob-insecure-defaults Skills.*
