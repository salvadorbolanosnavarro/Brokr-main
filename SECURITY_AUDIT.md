# Broquer Security Audit — final report

Base commit: `374b4d16ec4181dbd55fffd929953db6417cff15`  
Branch: `agent/security-final`  
Certified code HEAD before this report-only commit: `bf98c788ed42d8ee0536ace8c8176dae6f8ef2f5`  
Canonical Quality run: `33345015267` — **PASS** (`scripts/run_quality.sh`)

Scope: authentication, authorization, tenant isolation/IDOR, privileged Supabase access, admin endpoints, Meta/WhatsApp, Stripe/RevenueCat, SSRF, caller-controlled URLs, uploads/storage, path traversal, types/sizes, XSS, injection, SQL/RPC boundaries, redirects/CSRF/CORS, rate limits, OTP/sessions, sensitive logging, documents/signatures, AI/API cost abuse, and relevant races. Review was static/unit/CI only. No production deployment, real-system attack, destructive data operation, or real secret use was performed.

## Executive summary

No confirmed **CRITICAL** vulnerability was found. Three **HIGH** vulnerabilities were confirmed and all three were remediated on this branch. Several clear **MEDIUM** issues were also fixed. Medium findings that require a database migration/transaction, end-to-end OAuth redesign, or product-flow decision remain explicitly open rather than receiving unsafe partial fixes.

The audit also corrected two important false-positive risks during review: Supabase JWTs were already validated through `/auth/v1/user`, so there was no unsigned-JWT authentication flaw; and the Meta/WhatsApp webhooks reviewed already validated HMAC signatures and failed closed when their secret was unavailable.

## Findings and remediation

### SEC-001 — HIGH — deactivated application users could retain authenticated API access — FIXED
Before remediation, `core/auth.py` validated the Supabase bearer token but did not enforce Broquer's application-level `usuarios.activo` flag. `POST /admin/user/activo` only changed that database flag, so an already-issued Supabase JWT could continue to pass endpoints guarded only by canonical authentication.

Remediation:
- `8894c092b0056a600c14cb7bddc986d5a2f97d81` — canonical authentication now verifies `usuarios.activo` after Supabase validates the JWT and fails closed if the authorization state cannot be established.
- `f2947c3a7162648232865c68c42df7a9467efcc4` — shared `get_user_access_state()` also fails closed instead of returning `activo=True` on configuration/DB uncertainty.
- `bf98c788ed42d8ee0536ace8c8176dae6f8ef2f5` — regression guard updated to require the fail-closed contract.

Residual risk: application deactivation does not itself revoke the Supabase refresh token; the server-side active check is therefore intentionally retained on authenticated requests.

### SEC-002 — HIGH — attacker-controlled IMAP/SMTP destinations enabled server-side network probing — FIXED
`POST /correo/conectar` accepted custom IMAP/SMTP hosts and ports and opened backend sockets without validating whether the target was localhost/private/link-local/reserved infrastructure.

Remediation:
- `949a7ed3a0bd395f5a3c745f0074f320077c7241` — only supported mail ports are allowed (IMAP 993; SMTP 465/587), localhost/`.local` targets are rejected, direct IPs must be globally routable, DNS results are resolved and every returned address must be global, and validation is repeated immediately before stored IMAP/SMTP connections.
- `34193dab4c18d0b3d8b3b68fbf1b5f5e2addabe0` — regression coverage for loopback, RFC1918, arbitrary ports, and a hostname resolving to link-local metadata space.

Residual risk: like most hostname validation done before a library opens its own socket, DNS rebinding between validation and connect remains a theoretical TOCTOU. Eliminating that fully would require connecting to the validated address while separately preserving TLS/SNI hostname verification.

### SEC-003 — HIGH — anonymous and batched image cleanup amplified Gemini spend and memory use — FIXED
Pre-fix `POST /images/clean` could be anonymous by default, accepted an arbitrary number of fully buffered uploads, and could fan one request into many concurrent Gemini calls while charging only one request to the shared limiter.

Remediation:
- `b3a8c341c8e9d9243c939b12b16e5a14b0c67d8b` — `EXIGIR_SESION_IA` is secure-by-default (`true` unless an operator explicitly opts out).
- `fe10b1fc5c3cc000c3f86c48845f0689d3e3cefa` — max 8 images, 12 MiB/image, 40 MiB/batch, 40M pixels/image, JPG/PNG/WEBP MIME allowlist, Gemini concurrency capped at 2, empty/oversized uploads rejected, and rate-limit quota is charged per image rather than per batch.
- `c3731ae8a64d3cbc507627ac019cc86eab130c70` — configuration tests now freeze the secure default while preserving an explicit operator opt-out.

### SEC-004 — MEDIUM — ticket OCR/AI lacks a per-user paid-operation quota — OPEN
This was initially classified HIGH during broad review, then reassessed after reading the full endpoint. `/finanzas/ticket` requires an authenticated user, caps each upload at 10 MiB, restricts MIME, and caps Anthropic output at 500 tokens. Those bounds materially reduce exploitability, so final severity is **MEDIUM**, not HIGH.

The endpoint still lacks the shared paid-operation quota/rate limit, so an authenticated user can automate many paid OCR calls.

Pending because a correct fix should align Finance with the product's subscription/usage accounting rather than silently borrowing an unrelated quota. This is not being hidden as "fixed".

### SEC-005 — MEDIUM — Stripe webhook accepted indefinitely old valid signatures — FIXED
Pre-fix HMAC verification did not enforce the signed timestamp, allowing replay of a captured legitimate event indefinitely. Current mutations are largely idempotent, which limits impact but does not remove the trust-boundary flaw.

Remediation:
- `fb7c7c558469ddcabe7fec3206e731750fdb90fb` / finalized in `289507f258c261b7aa9cda9b416486e6fa45bd5f` — 300-second timestamp tolerance and support for multiple `v1` signatures while retaining constant-time comparison.
- `a6087237a4072aad38a5b2e8ac88713de127518f` and `34193dab4c18d0b3d8b3b68fbf1b5f5e2addabe0` — source and behavioral replay regression guards.

### SEC-006 — MEDIUM — caller-controlled Stripe checkout redirects — FIXED
Individual and enterprise checkout accepted caller-provided `success_url`/`cancel_url`; defaults also trusted the browser `Origin`. This allowed a legitimate Stripe-hosted checkout flow to redirect to an arbitrary attacker site.

Remediation:
- `ff13368ddc2d272e08c7d4e68f82f7f290f5cc73` — centralized trusted frontend-origin validation.
- `e241f9b3ed6f36a8811709ef0b690a8f13c40cf5` — individual checkout restricted to trusted Broquer frontend origins.
- `9db28dbc9123b0110fca061b6d539b789330b15c` — enterprise checkout receives the same restriction.
- `34193dab4c18d0b3d8b3b68fbf1b5f5e2addabe0` — external redirect rejection regression test.

### SEC-007 — MEDIUM — public account/email enumeration — OPEN
`GET /auth/correo-existe` is intentionally unauthenticated and reveals whether an email exists in `usuarios`. This can aid privacy attacks and credential stuffing.

Pending because a real fix requires an opaque registration/recovery UX or a dedicated anti-abuse design. Returning a different status or adding a small delay would not remove the enumeration oracle and could break registration behavior.

### SEC-008 — MEDIUM — WhatsApp org visibility included inactive members — FIXED
Organization owners/admins built their WhatsApp-visible user set from all membership rows without requiring active membership.

Remediation:
- `d563d15a28c8f709b36601d184d3e0ed4fd9c388` — `_ids_visibles` now filters `organizacion_miembros.activo=eq.true`.

### SEC-009 — MEDIUM — WhatsApp 2 access tokens are stored plaintext — OPEN
The connection flow persists the Meta `business_token` as `wa2_numeros.access_token`. Database disclosure would therefore directly expose Meta bearer credentials.

Pending because safe remediation requires a backward-compatible encryption migration, key lifecycle, dual-read transition for existing rows, and eventual plaintext cleanup. A one-sided code encryption change would strand existing connections.

### SEC-010 — MEDIUM — Meta OAuth callback does not enforce server-issued `state` — OPEN
`GET /facebook/callback` accepts `state` but does not validate it, and takes a request-provided `redirect_uri` into the token exchange. The connection flow therefore lacks a complete server-bound OAuth CSRF state lifecycle.

Pending because the fix must begin when OAuth is initiated: issue/store a high-entropy state bound to the user/session, validate-and-consume it exactly once in the callback, and derive the redirect URI from server configuration. Adding a callback-only comparison without an issued state would be cosmetic and unsafe.

### SEC-011 — MEDIUM — signature OTP attempt/use state is non-atomic — OPEN
OTP token generation, expiry, hashing and constant-time comparison are sound, but attempt counting and successful-use transitions are read/modify/write operations. Concurrent submissions can race around attempt or single-use enforcement.

Pending DB-atomic/RPC/transactional enforcement.

### SEC-012 — MEDIUM — organization seat/invitation enforcement has a race — OPEN
Active member + pending invitation count and invitation creation are separate operations. Concurrent invitations can exceed `asientos_max`.

Pending a transactional database constraint/RPC rather than a second application-side count.

### SEC-013 — MEDIUM — received email HTML can load remote tracking resources — OPEN
The frontend renders received HTML in `iframe sandbox=""`; this prevents direct script execution in Broquer's origin, so the audit did **not** classify this as stored XSS. Remote images/resources may nevertheless load and reveal open/IP/browser metadata to a sender.

Pending a product decision between sanitizing/blocking remote resources by default and proxying them through a privacy-preserving fetch layer.

### SEC-014 — MEDIUM — Finance accepts unverified related-object IDs — OPEN
Movement create/edit accepts `categoria_id`, `cuenta_id`, `propiedad_id`, and `contacto_id` without proving each referenced object belongs to the caller before the privileged Service Role write. This is a cross-tenant integrity risk; the audit did not demonstrate a direct cross-tenant read from it.

Pending organization-aware reference validation so future shared-org semantics are not broken by a user-only check.

### SEC-015 — MEDIUM — decompression-bomb surface in parsed uploads — PARTIALLY FIXED
Wire-size limits do not always bound decompressed parser work for ZIP-based spreadsheets or images.

Fixed for image cleanup by adding pixel-count and batch/input limits in `fe10b1fc5c3cc000c3f86c48845f0689d3e3cefa`. Spreadsheet archive expansion remains pending parser-level uncompressed-size/member-count guards.

### SEC-016 — LOW — wildcard CORS broadens browser-callable surface — OPEN
The app uses wildcard origins/methods/headers. Bearer-header authentication and disabled credential sharing mean this is not classic cookie CSRF, but wildcard CORS unnecessarily broadens browser-origin access.

Pending an authoritative production/staging frontend-origin inventory before narrowing it, to avoid breaking legitimate clients.

### SEC-017 — LOW — some upstream error details are returned/logged — OPEN
Several privileged integrations return or log truncated upstream response text. No directly interpolated secret was found, but schema/request metadata can be disclosed unnecessarily.

Pending systematic error normalization.

### SEC-018 — INFORMATIONAL — Service Role is the primary tenant-isolation hazard
The common DB layer legitimately performs privileged Supabase REST operations with Service Role. Consequently RLS cannot be treated as the second barrier for those calls; router scoping by trusted `user_id`/`org_id` is mandatory.

The audit found explicit owner/org scoping in Firmas, organization administration, Bolsa mutations, video job reads and most Finance reads/writes. SEC-014 is one concrete integrity gap created by accepting related IDs without equivalent ownership proof.

### SEC-019 — INFORMATIONAL — webhook authentication controls already present
Meta/Facebook/WhatsApp webhooks reviewed validate HMAC signatures and fail closed when their required secret is absent. RevenueCat requires a configured shared authorization secret and compares it in constant time. These were reviewed specifically to avoid reporting nonexistent "unsigned webhook" vulnerabilities.

### SEC-020 — INFORMATIONAL — common Storage path traversal controls already present
`core/storage.py` validates bucket names, normalizes leading slash, rejects empty/`.`/`..` path segments, URL-encodes path components and supports signed URLs for private access. No common-layer path traversal was found.

## Quality certification

Canonical gate executed from the security branch at `bf98c788ed42d8ee0536ace8c8176dae6f8ef2f5`:

- `scripts/run_quality.sh`: **PASS**
- Python unit tests: **715 passed**
- frontend `audit.py`: **0 violations in 42 files**
- architecture debt guard: **PASS; debt did not grow**
  - direct env reads: 0 / ceiling 0
  - duplicated auth helpers: 0 / ceiling 0
  - service-key fallbacks: 0 / ceiling 0
  - direct Supabase REST: 0 / ceiling 0
  - embedded JWT secrets: 0 / ceiling 0
  - fail-open webhook secrets: 0 / ceiling 0
  - fail-open entitlements: 0 / ceiling 0

Security-specific CI uses `.github/workflows/security-quality.yml` with `contents: read` and executes only `bash scripts/run_quality.sh`; it has no branch-write or deployment step.

## Integration notes

No merge was performed. `main` was not written. `agent/architecture-cleanup` was not written. A temporary draft PR (#57) created solely to trigger the existing Quality workflow was immediately closed after it also selected a historical architecture workflow. That architecture job failed in its deterministic transform step; its commit/push step was skipped, so it made no write to `agent/architecture-cleanup`.

Potential conflicts when integrating with parallel Core/Architecture/WhatsApp work:
- `core/auth.py` and `core/config.py` are likely conflict points with Core changes; preserve the security semantics, not necessarily this exact text.
- `routers/whatsapp_access.py` may conflict with WhatsApp decomposition; preserve the `activo=eq.true` organization-member filter.
- `routers/correo.py`, `routers/image_cleaner.py`, Stripe routers and `core/redirects.py` are security-owned changes and should not be dropped during architectural moves.
- Tests that formerly froze fail-open behavior were intentionally updated only after exact Quality tracebacks showed they contradicted the remediations.
