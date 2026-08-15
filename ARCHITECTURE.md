# Broquer Architecture

This document is the engineering contract for progressively turning the current
Broquer repository into a modular, testable platform without breaking existing
product behavior during migration.

## 1. Target shape

Broquer should have one place per responsibility:

- `core/` — cross-cutting platform infrastructure and policy.
- `routers/` — domain HTTP endpoints and domain orchestration.
- root application bootstrap — composition only: create the app, register
  middleware, mount routers/modules, and expose static assets.
- canonical frontend shell/theme — one executable design system, reused by all
  modules.
- `tests/` — regression contracts for shared behavior and migrated domains.
- `migrations/` — versioned database changes that make Supabase reproducible.

A new module should follow an existing declarative pattern. It should not need
new auth code, new Supabase headers, a forked theme, or another giant metadata
list in `main.py`.

## 2. Core ownership

Shared behavior belongs in `core/`, not in domain routers.

### Configuration

`core.config` owns environment-variable names, defaults, compatibility aliases,
and security-sensitive fallback behavior. Domain modules must import settings
instead of calling `os.getenv()` / `os.environ` directly.

Privileged Supabase access **never** falls back to the anonymous key. Missing
service-role configuration must fail closed.

### Authentication and authorization

`core.auth` owns Supabase bearer-token validation.

`core.permissions` owns organization role/permission policy.

`core.organizations` owns cross-cutting organization context and organization
authorization helpers.

`core.admin` owns administrator authorization. Admin endpoints must not duplicate
token parsing or role checks. A database/configuration failure must not grant
administrative access; it fails closed.

`core.subscriptions` owns paid-feature entitlement checks. An inability to
verify entitlement is not permission to continue.

`core.webhooks` owns shared-secret webhook validation. A webhook secret that is
missing from server configuration means the webhook is unavailable (503), **not
public**. Secret comparison uses constant-time comparison. Query-string secret
support exists only as a compatibility path where explicitly enabled.

### Supabase REST and Storage

`core.database` owns privileged PostgREST calls and service-role headers.

`core.storage` owns Supabase Storage operations and object-path validation.
Domain routers do not construct privileged Storage URLs or service headers.

### External HTTP

`core.http` owns bounded public HTTP fetching for user-supplied URLs. Public
fetching validates schemes/hosts/IPs, revalidates redirects, rejects local and
non-public networks, and bounds response size.

### Design

`brokr-theme.css` is the only executable visual-token source of truth.

`core.design` exposes those tokens to backend-generated HTML/PDF code. Backend
renderers do not maintain copied palettes.

`brokr-theme-v2.css` may temporarily exist only as a compatibility shim that
imports `brokr-theme.css`; it must not define its own tokens. Once the remaining
HTML reference is safely changed, the shim is deleted.

## 3. Module contract

`core.modules.ModuleDefinition` is the canonical module metadata contract.
Module identifiers, route/navigation paths, and permission declarations are
validated centrally.

Visual design is intentionally not configurable per module. Modules inherit the
canonical Broquer shell/theme.

Over time, app composition should discover/register module definitions rather
than editing giant hard-coded lists in `main.py` and `app-shell.js`.

## 4. Migration strategy

Use a strangler migration, not a rewrite.

For each domain:

1. Map current endpoints, callers, side effects, environment variables, tables,
   Storage buckets, and external integrations.
2. Write/extend regression contracts for behavior that must be preserved.
3. Move cross-cutting infrastructure to Core before moving domain logic.
4. Switch one consumer/domain to the shared primitive.
5. Run Quality and inspect any failure before stacking the next migration.
6. Remove the legacy helper only after all callers have moved.
7. Ratchet measurable architecture-debt ceilings downward after each verified
   reduction.

Temporary compatibility adapters are allowed only when they make a staged
migration safer. They must have an explicit removal path; the target repository
must not retain permanent duplicate infrastructure.

## 5. Security rules

- Privileged credentials never downgrade to public/anonymous credentials.
- Missing authorization configuration fails closed.
- Missing webhook secrets fail closed.
- Organization/admin/paid-feature authorization is backend policy, never a
  frontend decision.
- User-supplied outbound URLs pass through the public-HTTP safety layer.
- Secrets/tokens are stored server-side and are never echoed to browser-facing
  responses unless the protocol explicitly requires it.
- Storage paths are normalized and traversal is rejected.
- Existing legacy exceptions are documented and removed progressively rather
  than silently reinterpreted.

## 6. Quality gates

The GitHub `Quality` workflow is part of the architecture, not decoration. It
must remain capable of blocking regressions before `main` is touched.

Current responsibilities include:

- compile shared Core and migrated backend modules;
- discover and execute every `test_*.py` test;
- audit the actively migrated Statistics UI against the design rules;
- verify canonical-theme compatibility;
- enforce migration guards on already-cleaned modules;
- inventory architecture debt and fail if established ceilings grow.

Architecture-debt ceilings are maximums, never targets. When cleanup lowers a
verified count, the corresponding ceiling is lowered in the same branch so the
improvement cannot silently regress.

## 7. Large-file policy

Large files are migration targets, not automatic deletion targets. Do not
rewrite a 50–600 KB production file manually merely to make a small
infrastructure change when tooling cannot apply a safe surgical patch.

Instead:

- extract and test the shared primitive first;
- map exact callers/behavior;
- migrate the large consumer when a reliable edit path is available;
- keep production behavior unchanged until that cut can be validated.

This applies especially to `main.py`, root `whatsapp.py`, Firma electrónica,
large HTML screens, and other monolithic modules.

## 8. Database/Supabase direction

The eventual Supabase cleanup follows the same rule as the repository cleanup:
inventory first, versioned migration second, destructive cleanup last.

The target state is that tables, columns, indexes, RLS/policies, functions,
triggers, Storage buckets/policies, and required seed/config data can be
understood and reconstructed from version-controlled migrations. Manual
production-only database state should progressively disappear.

No destructive production database operation is part of this architecture
cleanup without explicit authorization and a recovery plan.

## 9. Definition of done

The cleanup is complete when:

- `main.py` is a small bootstrap/composition layer rather than a domain
  monolith;
- cross-cutting configuration/auth/database/storage/policy exists once;
- no service-role-to-anon fallbacks remain;
- no duplicated auth helpers remain;
- no domain router reads environment variables directly;
- there is one executable design system;
- active modules are registered consistently;
- Supabase schema/policies are backed by coherent versioned migrations;
- Quality protects the contracts above;
- obsolete patches, previews, accidental copies, and compatibility shims have
  been removed after their callers are proven migrated.
