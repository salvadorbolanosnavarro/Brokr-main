# Broquer Architecture

This document is the architectural contract for Broquer.

The goal is not only to keep Broquer working. The repository must remain easy to understand, safe to extend, and difficult to degrade.

## 1. Non-negotiable principles

1. **One responsibility, one implementation.** Authentication, database access, permissions, configuration, AI clients, HTTP clients, rate limiting, logging, errors, and design tokens each have one canonical implementation.
2. **No permanent compatibility patches.** Temporary adapters are allowed only during migrations and must have an explicit removal condition.
3. **No historical clutter in production code.** Git is the archive. Files named `copy`, `old`, `legacy`, `v2`, `final`, experiments, previews, and obsolete alternatives do not stay in the production tree once superseded.
4. **No module may bypass platform services.** Modules consume shared platform capabilities instead of recreating them.
5. **A new module must be declarative.** Adding a module must not require hand-editing central navigation, auth, permissions, error handling, or design-system code.
6. **Design has one source of truth.** `DESIGN.md` defines the rules. The executable design system must expose one canonical token/component entry point. Modules consume it; they do not redefine it.
7. **Delete what no longer earns its existence.** Dead code, unused dependencies, duplicated helpers, obsolete assets, and unreachable endpoints are removed after usage is proven absent.
8. **Prefer explicit failure over silent fallback.** Privileged credentials, required configuration, and security assumptions must fail closed.
9. **Main entry points stay boring.** `main.py` should assemble the application, not contain business logic.
10. **Architecture must make the correct path the easiest path.** A future developer should naturally follow the system rather than invent a new pattern.

## 2. Target repository shape

The exact migration order may change, but the intended destination is:

```text
broquer/
├── README.md
├── ARCHITECTURE.md
├── DESIGN.md
├── pyproject.toml
├── Dockerfile
├── .env.example
│
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── auth.py
│   │   │   ├── database.py
│   │   │   ├── permissions.py
│   │   │   ├── security.py
│   │   │   ├── logging.py
│   │   │   └── errors.py
│   │   ├── integrations/
│   │   ├── services/
│   │   └── modules/
│   └── tests/
│
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   ├── design-system/
│   │   └── modules/
│   └── public/
│
├── mobile/
│   └── ios/
├── migrations/
├── scripts/
└── docs/
```

This is a direction, not an excuse to create empty folders. A directory exists only when it has a real responsibility.

## 3. Platform versus modules

### Platform owns

- authentication and session validation
- organization context and tenant isolation
- permissions
- configuration and secrets
- database client and transaction boundaries
- external-service clients
- rate limiting
- logging and observability
- error model
- background jobs
- file/storage primitives
- design system
- navigation/module discovery

### Modules own

- domain models and rules
- routes/use cases for that domain
- domain-specific persistence code
- domain-specific UI
- domain-specific tests

A module must not create its own auth helper, Supabase client, permission model, global CSS tokens, logging system, or generic HTTP client.

## 4. Canonical module contract

Every module must expose metadata through a single declarative manifest. The exact implementation can evolve, but the contract must contain the equivalent of:

```python
Module(
    key="properties",
    name="Propiedades",
    route_prefix="/properties",
    navigation={"section": "commercial", "order": 10},
    permissions=["properties.read", "properties.write"],
    backend_router=router,
    frontend_entry="modules/properties",
)
```

The application discovers manifests and derives from them:

- backend router registration
- navigation entries
- page metadata
- permission declarations
- feature availability
- diagnostics/health information

**Adding a module must not require editing `main.py`, `PAGE_META`, `MODS`, or another central registry by hand.**

## 5. Design-system contract

`DESIGN.md` remains the human-readable design law. The runtime implementation must converge to one canonical design-system entry point.

Rules:

- modules consume tokens/components; they do not redefine global tokens
- no parallel theme files representing different generations
- no hard-coded visual constants when a canonical token exists
- new reusable UI patterns are added to the design system first, then consumed by modules
- module-specific styles are allowed only for domain-specific presentation
- global shell/navigation/page-header behavior is platform-owned

The eventual automated audit must validate both legacy pages during migration and all new module code.

## 6. Security and tenancy contract

Broquer is multi-tenant. Tenant isolation is an architectural invariant, not a convention.

- every authenticated operation resolves a trusted user identity
- every tenant-owned operation resolves organization context centrally
- privileged server credentials never reach the client
- service-role access must be explicit and fail closed if unavailable
- every read/write using privileged credentials must scope data to the authorized tenant or use a reviewed platform service that does so
- authorization is enforced server-side/database-side; hiding UI is never security
- external webhooks are authenticated/verified before side effects
- expensive endpoints require authentication unless deliberately documented as public

## 7. Migration strategy

Broquer will be improved by strangling the current monolith, not by a blind rewrite.

For each extraction:

1. map current behavior and callers
2. add characterization tests where practical
3. create the canonical platform/domain implementation
4. route existing callers through it
5. verify behavior
6. remove the superseded implementation
7. remove temporary adapters once no callers remain

At no point is duplicated permanent logic considered a completed migration.

## 8. Repository cleanliness standard

A file stays in the production repository only if it has a current, explainable purpose.

Candidates for removal/consolidation include:

- duplicated shells/themes/helpers
- copied HTML files
- obsolete redesign previews and mocks
- dead migration helpers after their historical role is captured
- unused scripts
- unused assets
- unused dependencies
- commented-out implementations
- unreachable endpoints
- fallback implementations that hide configuration errors

Deletion requires evidence that the artifact is unused or superseded; cleanup must not become guesswork.

## 9. Definition of done for a new module

A module is not complete unless:

- it follows the canonical module contract
- it uses platform auth/database/permissions/config
- it uses the canonical design system
- it contains no duplicated generic infrastructure
- it has tests for critical domain behavior
- it introduces no new global styling source
- it introduces no manual central-registration requirement
- it passes repository quality/security checks
- a developer unfamiliar with the module can locate its entry point and understand its boundaries quickly

## 10. Architectural review question

Before adding any abstraction, helper, file, dependency, endpoint, migration, or compatibility layer, ask:

> Does this need to exist, and if it does, is this the one canonical place where it belongs?

If the answer to either part is unclear, the change is not ready.