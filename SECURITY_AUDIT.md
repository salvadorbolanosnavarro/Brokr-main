# Broquer Security Audit — pre-fix findings

Base commit: `374b4d16ec4181dbd55fffd929953db6417cff15`
Branch: `agent/security-final`

Scope: authentication, authorization, tenant isolation/IDOR, privileged Supabase access, admin, Meta/WhatsApp, Stripe/RevenueCat, SSRF, uploads/storage, XSS, injection, redirects/CSRF/CORS, rate limits, OTP/sessions, sensitive logging, documents/signatures, AI/API cost abuse, and relevant races. Review is static/local only; no real systems, destructive operations, deployment, or real secrets were used.

## Findings

### SEC-001 — HIGH — deactivated application users can retain authenticated API access
`core/auth.py` validates a Supabase bearer token through `/auth/v1/user`, but the canonical authentication helper does not enforce the application-level `usuarios.activo` flag. `POST /admin/user/activo` only changes that database flag. Endpoints protected only by `require_user_id()` therefore do not inherently reject a still-valid Supabase session after an administrator deactivates the account.

Status: **confirmed; fix planned**. The fix must be fail-closed without weakening Supabase JWT validation.

### SEC-002 — HIGH — server-side IMAP/SMTP connections accept attacker-controlled hosts and ports
`POST /correo/conectar` accepts custom `imap_host`, `imap_port`, `smtp_host`, and `smtp_port`, then connects from the backend using `imaplib`/`smtplib` with no public-network validation. An authenticated paid user can turn the service into a TCP reachability/port-probing primitive against localhost, private, link-local, or cloud-internal destinations.

Status: **confirmed; fix planned**. Restrict to public resolved addresses and the protocol ports actually supported by the product; revalidate before connections.

### SEC-003 — HIGH — AI cost amplification and memory/CPU abuse in image cleanup
`POST /images/clean` can operate anonymously when `EXIGIR_SESION_IA` is omitted because the default is currently false. The endpoint reads an arbitrary number of uploads fully into memory, has no per-file/aggregate input bound, and `asyncio.gather` can issue one Gemini edit per image concurrently while the request rate limiter charges only one request.

Status: **confirmed; fix planned**. Make paid AI/session policy secure by default and bound count, size, MIME and concurrent paid calls.

### SEC-004 — HIGH — expensive ticket OCR/AI endpoint lacks cost rate limiting
`POST /finanzas/ticket` accepts an authenticated user and can send up to 10 MB per request to Anthropic, but does not use the shared paid-operation rate limiter. Automated authenticated calls can create unbounded API spend relative to the controls used elsewhere.

Status: **confirmed; fix planned**.

### SEC-005 — MEDIUM — Stripe webhook signatures have no replay time window
`routers/stripe_webhook.py` authenticates the HMAC but does not reject an old signed timestamp. A captured legitimate request can be replayed indefinitely. Most current mutations are idempotent, reducing impact, but replay resistance is part of the webhook trust boundary.

Status: **confirmed; fix planned** with a bounded timestamp tolerance and support for multiple `v1` signatures.

### SEC-006 — MEDIUM — checkout success/cancel redirects are caller controlled
Both individual and enterprise Stripe checkout creation accept `success_url` and `cancel_url`; when absent they also derive destinations from the caller-controlled `Origin` header. An authenticated user can create a legitimate Stripe Checkout session that redirects to an arbitrary site, enabling phishing/open-redirect abuse of Stripe-hosted trust.

Status: **confirmed; fix planned**. Only configured Broquer frontend origins should be accepted.

### SEC-007 — MEDIUM — public account/email enumeration
`GET /auth/correo-existe` is intentionally unauthenticated and returns whether an email exists in `usuarios`. This enables account discovery useful for privacy attacks and credential stuffing.

Status: **confirmed; pending product-flow decision**. A real fix requires an opaque registration/recovery flow or a dedicated abuse-control mechanism; merely slowing the endpoint does not remove enumeration.

### SEC-008 — MEDIUM — WhatsApp organization visibility includes inactive members
`routers/whatsapp_access.py::_ids_visibles` grants owners/admins visibility to all member user IDs in their org without `activo=true`. Offboarded/inactive membership rows can therefore remain within the WhatsApp visibility set.

Status: **confirmed; fix planned**.

### SEC-009 — MEDIUM — WhatsApp 2 access tokens are stored in plaintext
The WhatsApp connection flow persists `business_token` directly as `wa2_numeros.access_token`. A database exposure therefore directly exposes Meta bearer credentials. Other integration areas already have token-encryption infrastructure, but WhatsApp 2 needs a backward-compatible data migration and read/write transition rather than a one-line code change.

Status: **confirmed; pending migration design**.

### SEC-010 — MEDIUM — OAuth callback does not enforce `state` and accepts request-provided redirect URI
`GET /facebook/callback` receives `state` but never validates it, and accepts a `redirect_uri` query parameter for the token exchange. This leaves the Meta connection flow without server-side OAuth CSRF binding and expands redirect-URI trust to request input.

Status: **confirmed control gap; pending end-to-end OAuth flow hardening**. The frontend/session state lifecycle must be changed coherently rather than adding a comparison with no issued server state.

### SEC-011 — MEDIUM — signature OTP attempt counter is not atomic
Signature OTP attempts use read/increment/write. Concurrent invalid requests can race around the five-attempt threshold; successful signing can also be submitted concurrently after the same pre-check. Tokens, expiry, hashing and constant-time comparison are otherwise sound.

Status: **confirmed race; pending DB-atomic/RPC change**.

### SEC-012 — MEDIUM — organization seat/invitation enforcement has a race
The invitation flow counts active members + pending invitations and then inserts a new invitation in separate operations. Concurrent invitations can exceed `asientos_max`.

Status: **confirmed race; pending transactional/database constraint**.

### SEC-013 — MEDIUM — remote email HTML can trigger privacy-tracking requests
The frontend renders received HTML inside `iframe sandbox=""`, which prevents script execution in Broquer's origin and avoids a direct stored-XSS finding. However, unsanitized remote images/resources may still load and disclose open/IP/browser metadata to the sender.

Status: **confirmed privacy issue; pending HTML sanitization/proxy policy**.

### SEC-014 — MEDIUM — finance relationships accept unverified foreign IDs
Movement creation/editing accepts `categoria_id`, `cuenta_id`, `propiedad_id`, and `contacto_id` without checking that the referenced object belongs to the caller before writing with Service Role. This is primarily cross-tenant integrity risk rather than a demonstrated read primitive.

Status: **confirmed; pending organization-aware reference-validation design**.

### SEC-015 — MEDIUM — compressed spreadsheet/image inputs retain decompression-bomb DoS surface
Several upload paths cap compressed/upload bytes, but parsers such as openpyxl/Pillow can expand attacker-controlled content substantially beyond wire size. Image cleanup additionally lacks dimension bounds in the pre-fix state.

Status: **confirmed hardening gap; image-cleaner portion planned for fix; spreadsheet archive expansion remains pending**.

### SEC-016 — LOW — wildcard CORS broadens browser-callable API surface
The application uses `allow_origins=["*"]`, `allow_methods=["*"]`, and `allow_headers=["*"]`. Because authentication is bearer-header based and credentials are not enabled, this is not classic cookie CSRF; nevertheless it unnecessarily permits any browser origin to call the API and complicates abuse containment.

Status: **confirmed; pending deployment-origin inventory before restriction**.

### SEC-017 — LOW — raw upstream error text is returned/logged in several privileged paths
Some Stripe/Supabase/admin error paths expose truncated upstream response text to authenticated/admin callers or logs. No secret value was found directly interpolated, but schema/request metadata can leak unnecessarily.

Status: **confirmed hardening item; pending**.

### SEC-018 — INFORMATIONAL — Service Role makes router scoping the primary tenant boundary
The shared database layer performs privileged Supabase operations with Service Role. This is required by current architecture but bypasses normal client RLS protections, so every object lookup/mutation must include trusted `user_id`/`org_id` scoping. Review found strong explicit scoping in Firmas, organization administration, Bolsa publication mutations, video job reads, and much of Finanzas; the missing finance foreign-reference validation above is one concrete consequence of this architecture.

### SEC-019 — INFORMATIONAL — Meta/WhatsApp webhook authentication is present and fails closed
The Facebook/WhatsApp webhook paths reviewed validate HMAC signatures and do not process events when the required secret is absent. RevenueCat likewise requires a configured shared authorization secret and compares it in constant time. These were specifically checked to avoid a false positive.

### SEC-020 — INFORMATIONAL — common Storage path traversal protections are present
`core/storage.py` validates bucket names, strips leading slash, rejects empty/`.`/`..` path segments, URL-encodes each segment and uses signed URLs for private-object access where requested. No common-layer path traversal was found.

## Fix policy

Critical/High findings that can be corrected safely will be fixed on this branch. Clear Medium findings with bounded behavior changes will also be fixed. Findings requiring schema migrations, distributed/transactional enforcement, or end-to-end product-flow redesign remain explicitly pending rather than being hidden or papered over.

This file intentionally records the **pre-fix** state. It will be updated after remediation and `scripts/run_quality.sh` certification with exact fix commits and residual risk.