# ADR 0002: Strangler-fig microservices migration

- **Status**: Accepted (2026-05-18)

## Context

The monolith has seven endpoint files (`auth`, `text`, `user_data`,
`subscription`, `passes`, `history`, `share`) and ~22 SQLAlchemy models
spread across three Postgres schemas (`auth`, `activity`, `billing`).
Reconnaissance estimated a full carve into independent FastAPI services
at 8–12 weeks of work — much larger than any prior change.

We need a migration shape that:
- Is reversible at each step (a botched extraction can be rolled back to
  the previous merge without a multi-day cleanup).
- Keeps the product working end-to-end at every commit.
- Doesn't paint us into corners architecturally.

## Decision

Adopt a **strangler-fig migration** across multiple incremental
deliverables, where each step extracts exactly one concern:

| Phase | Deliverable |
|---|---|
| **Foundation (this ADR)** | Monorepo layout, shared package, Kong gateway (routing 100% to monolith), Keycloak (idle). |
| Auth cutover | Extract identity work to Keycloak; monolith stops serving `/api/v1/auth/*`. Physical move of monolith to `services/monolith/`. |
| Extract `ai-svc` | Groq-backed AI tools. |
| Extract `text-svc` | 53 local tools + `tool_registry`. |
| Extract `payments-svc` | Razorpay, subscriptions, passes. |
| Extract `account-svc` | User data, history, share. |
| Decommission monolith | Gateway routes go 100% to extracted services. |

Each phase follows the same shape: pre-flight read-only checks → approve
branches → write files in parallel → approve commit messages → push.

## End-state services (5, not 6)

The original roadmap called for six services (`case-svc`, `encoding-svc`,
`cipher-svc`, `ai-svc`, `auth-svc`, `payments-svc`). After reconnaissance:

- `auth-svc` is **replaced by Keycloak**, not a separate Python service.
- `case-svc` / `encoding-svc` / `cipher-svc` **collapse into `text-svc`** —
  all three are stateless pure-function transforms; three services for
  the same workload triples ops cost without independent scaling benefit.
- `account-svc` is **added** to hold `user_data`, `history`, `share`
  routes that the original roadmap never named.

Final state: `identity` (Keycloak), `text-svc`, `ai-svc`, `payments-svc`,
`account-svc` — five services total.

## Why strangler-fig (not big-bang)

| Approach | Rejected because |
|---|---|
| Big-bang carve | High coordination cost; six PRs all conflicting on `app/`; one bad extraction breaks every service simultaneously; no rollback after merge. |
| Per-service feature flags | Adds runtime branching in every endpoint; flag config drift; production-only state. |
| Scaffold-then-extract-all | Same as big-bang once extraction starts. |

Strangler-fig matches our cadence (single dev, weekly delivery, ~50–100
file changes per PR) and gives us a working product at every commit.

## Consequences

**Positive:**
- Each phase is independently reviewable in a PR.
- Rollback is `git revert` of the most recent merge — at worst, the most
  recently extracted service goes back into the monolith.
- The product is always shippable. No long-lived "v2 branch" to maintain.

**Negative:**
- The full migration takes multiple phases, not one.
- Some duplication during transition (e.g., the foundation phase has shim
  modules that the auth cutover deletes; every extraction duplicates the
  cross-cutting boilerplate via the shared package — accepted as the cost
  of isolation).

**Neutral:**
- Scope decisions (boundaries between services) are deferred until the
  prior phase ships, so we adjust based on real friction.
