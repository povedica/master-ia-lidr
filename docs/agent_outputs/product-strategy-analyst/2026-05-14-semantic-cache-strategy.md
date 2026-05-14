# Product Strategy: Semantic Cache for LLM Estimation Backend

**Date:** 2026-05-14
**Scope:** Strategic guidance for a feature spec adding semantic caching in front of the LLM estimation pipeline (FastAPI, versioned Jinja2 prompts, typed Pydantic I/O, input/output guardrails). No code; this informs the spec only.

---

## Executive summary

Estimation requests cluster around a small set of recurring shapes (scope phrasing, complexity tier, team size, similar feature notes). A semantic cache placed **after input guardrails** and **before LLM rendering** can cut latency and cost on near-duplicate requests with negligible quality loss, provided we (1) cache only validated, guardrail-passed outputs, (2) gate hits by deterministic bucket equality + embedding similarity threshold, and (3) ship a **log-only shadow phase first** so the threshold and false-positive rate are measured before any user-visible behavior change.

The bet is conservative: we expect meaningful hit rate on **internal/iterative use** (re-running the same estimation with light tweaks) and limited but useful hits on **organic traffic**. The strategy below is built around proving the bet cheaply, then ramping behind a kill switch.

---

## 1. Product hypothesis

**If** we add a semantic cache keyed by `(tenant, deterministic_bucket, prompt_version, model_version, embedding_model_version)` and gated by an embedding similarity threshold over the guardrail-cleaned request,
**then** we will serve ≥X% of validated estimation requests from cache with median latency under ~Y ms and per-request cost reduction of ≥Z%,
**without** measurable degradation in output quality (no increase in guardrail failures, no increase in user override/regenerate rate, no drop in user-reported usefulness).

X / Y / Z are intentionally placeholders. Phase 0 (shadow) exists to set them with data, not opinion.

### Why it should work
- Estimation requests have strong locality: same team re-runs near-identical inputs during scoping.
- Deterministic structured fields (complexity tier, team composition, scope category) already partition the space; embeddings add tolerance to phrasing differences in free-text notes.
- Outputs are structured Pydantic objects that are easy to re-validate on read, so trust in cached payloads is bounded by schema + guardrails, not by LLM whim.

### Why it might not
- True repetition rate may be low in customer-facing traffic.
- "Looks similar" inputs can still diverge on a single critical field (e.g., "2 devs" vs "2 senior devs"). The deterministic bucket must carry those fields, not the embedding.
- Prompt or model upgrades silently invalidate cached reasoning; the cache key must be versioned end-to-end.

---

## 2. Target users and use cases

Ranked by likely value:

1. **Internal estimators iterating on the same item** (highest hit rate, highest value)
   - Pain: re-running estimation after small wording tweaks is slow and costly.
   - Cache value: sub-second response on near-duplicates, preserving validated output.
2. **Workshops / sprint planning** with batches of related work items
   - Pain: long sessions, repeated LLM calls on similar shapes.
   - Cache value: lower latency keeps the meeting flowing.
3. **API consumers retrying or polling** (e.g., flaky network, idempotency)
   - Pain: duplicate spend on the same request within minutes.
   - Cache value: idempotency at near-zero cost.
4. **Cross-user reuse within the same tenant** (lowest hit rate, opt-in)
   - Pain: different users estimate similar features independently.
   - Cache value: marginal; should be feature-flagged and only after isolation rules are proven.

Cross-tenant reuse is **out of scope** (privacy + drift risk > value).

---

## 3. Rollout strategy (log-only first)

Five phases, each with an explicit exit criterion. Default state: cache **disabled for serving** in production until Phase 2 exit.

### Phase 0 — Shadow / log-only (default ON, no user impact)
- Compute embedding, bucket, and lookup on every request.
- Always serve fresh LLM response; **never** return cached payload.
- Emit structured event per request: `bucket_hit`, `similarity`, `would_have_served_cache`, `latency_saved_estimate`, `prompt_version`, `model_version`.
- Write cache entries only when output validation + guardrails pass.
- **Exit when:** ≥N (e.g., 1–2k) shadow requests collected across representative buckets.

### Phase 1 — Threshold calibration (offline)
- Build a labeled set of `(request_A, request_B, cached_output, fresh_output)` pairs from shadow data.
- Score each pair by output equivalence (schema-level diff + optional human review on a sample).
- Choose similarity threshold that hits a documented **precision target** for "cache hit would have been correct" (e.g., ≥98% on the validation set). Document recall as a side effect, not a target.
- **Exit when:** threshold is chosen, documented in the spec, and reproducible from logs.

### Phase 2 — Internal canary (real serving, narrow surface)
- Enable real cache serving for one internal tenant or a single deterministic bucket family (e.g., one project type).
- Kill switch via config flag, default OFF elsewhere.
- Compare cached-served vs fresh-served on the canary: guardrail failure rate, override/regenerate rate, latency, cost.
- **Exit when:** no regression vs Phase 0 shadow predictions over a defined observation window.

### Phase 3 — Gradual ramp by bucket
- Enable real serving per `(tenant, bucket_family)` where calibration confidence is high.
- Keep shadow logging running for buckets still in observation.
- **Exit when:** target hit rate / cost reduction achieved on enabled segments, no quality regression.

### Phase 4 — General availability
- Cache on by default with kill switch, documented rollback, TTL policy, and dashboards.
- Quarterly review of threshold and TTL against drift.

---

## 4. Success metrics

Split into **product**, **quality**, and **operational** so we never trade one silently for another.

### Product (the bet)
- **Cache hit rate** overall and per bucket family.
- **p50 / p95 latency** for cache-served vs LLM-served requests.
- **$ / 1k requests** trend before vs after enablement.
- **Repeat-request rate** within a session/tenant (validates the hypothesis premise).

### Quality (the guardrails on the bet)
- **Guardrail failure rate on read** (must stay at ~0; cached payloads re-validated on serve).
- **User override / regenerate rate** on cache-served vs fresh-served responses (no statistically meaningful increase).
- **Shadow-vs-fresh agreement rate** on output schema fields (sampled, ongoing in Phase 3+).
- **Sampled human review** of cache hits on a small rolling sample.

### Operational (the system is healthy)
- **False-positive rate at chosen threshold** (from rolling shadow comparison).
- **Cache write rate / store growth** vs TTL eviction.
- **Embedding latency** added on miss path (budget it; it is not free).
- **Kill-switch activation count** (should be near zero in steady state).

A north-star pairing keeps this honest: **hit rate × (1 − quality-regression rate)**. Pure hit rate is not a success signal on its own.

---

## 5. Risks and mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Stale outputs after prompt/model upgrade | High | High | Include `prompt_version` and `model_version` in cache key; bump invalidates atomically. |
| Embedding model change silently shifts space | Medium | High | Include `embedding_model_version` in cache key/namespace; ramp new model in shadow first. |
| Subtle critical-field difference (e.g., seniority) treated as same | Medium | High | Put critical structured fields in the **deterministic bucket**, never rely on embedding to catch them. |
| Cross-tenant leakage | Low | Critical | Tenant ID is part of the cache key; isolation is enforced at the storage layer, not by convention. |
| Cache poisoning via unsafe outputs | Low | High | Already mitigated: only validated + guardrail-passed responses are written. Re-validate on read as defense-in-depth. |
| Hit rate too low to justify infra | Medium | Medium | Phase 0 is cheap; if shadow hit rate stays below threshold, kill the feature before Phase 2. |
| User perceives "canned" responses | Low | Medium | UX metadata (`served_from_cache`, `cache_age_seconds`) + optional client `x-cache-bypass` header. |
| Drift over long TTLs | Medium | Medium | Conservative default TTL (24h–7d); revisit per bucket family in Phase 4. |
| Privacy/PII in embeddings index | Low | High | Apply input guardrails **before** embedding; document what fields contribute to embeddings. |
| Observability gap delays calibration | Medium | Medium | Ship dashboards and event schema in Phase 0, not retrofitted later. |

---

## 6. Acceptance criteria for the spec

The spec is ready to implement when it commits to all of the following. These are intentionally outcome-shaped, not implementation-shaped.

1. **Pipeline order is explicit and immutable:** input guardrails → embedding → semantic cache lookup → (hit) re-validate cached payload and return / (miss) render Jinja2 prompt → LLM → output validation + guardrails → cache write.
2. **Cache writes are gated** on output validation + guardrails passing. No exceptions.
3. **Cache reads re-validate** the cached payload against the current output schema before returning. Schema drift fails closed (treat as miss).
4. **Cache key includes** `tenant`, `deterministic_bucket` (structured critical fields), `prompt_version`, `model_version`, `embedding_model_version`. Any change to any of these invalidates the entry.
5. **Hit gate is two-stage:** deterministic bucket equality is required; embedding similarity ≥ threshold is required on top.
6. **Phase 0 ships log-only.** Cache serving is OFF behind a config flag in production until calibration is documented.
7. **Calibration artifact exists:** a documented dataset and procedure that produced the chosen similarity threshold, with a stated precision target and observed false-positive rate.
8. **Kill switch** is one config flag, documented, and exercised at least once in staging.
9. **UX metadata** is returned on responses: `served_from_cache`, `cache_age_seconds`, `prompt_version`, `model_version`. A client opt-out (e.g., header) bypasses the cache.
10. **Observability** is in place before Phase 1: structured events per request, dashboards for hit rate, latency saved, cost saved, guardrail failures on read, and shadow agreement rate.
11. **TTL policy** is defined, conservative by default, and configurable per bucket family.
12. **Tenant isolation** is enforced at the storage boundary, not by application convention, and covered by tests.
13. **Rollback procedure** is documented (flip flag → cache becomes inert; entries expire via TTL or manual purge).
14. **No regression** in existing input/output guardrail behavior, verified by the existing test suite plus targeted tests for the cache read/write paths.

---

## 7. Assumptions to validate (cheaply, in Phase 0)

- Repeat-request rate within a tenant/session is non-trivial (otherwise the feature is not worth shipping).
- Deterministic bucket + similarity threshold can hit the stated precision target on real traffic, not just synthetic pairs.
- Embedding latency on the miss path stays within the latency budget (it is added to every request, not just hits).
- Output schema is stable enough that re-validation on read is cheap and rarely fails.

---

## 8. Recommended next steps

1. Write the feature spec against the acceptance criteria above; resist adding scope beyond Phase 0–2.
2. Define the **event schema** for shadow logging before any code lands; dashboards depend on it.
3. Decide upfront which structured fields belong in the **deterministic bucket**; this is the single most consequential design choice and is a product decision, not an infra one.
4. Pick the embedding model and pin its version in config; treat upgrades as a migration, not a config tweak.
5. Plan the calibration dataset collection in Phase 0 explicitly (target N, bucket coverage, sampling rule).
6. Add a single ADR capturing the cache key shape, the two-stage hit gate, and the log-only rollout decision.

---

**Status:** Strategy draft for spec authoring. No implementation guidance included by design.
