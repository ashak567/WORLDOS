---
name: worldos-provenance-fusion
description: Playbook and rules for entity resolution, multi-source data fusion, publisher identifier prioritization, and strict evidence and provenance tracking in WORLDOS.
---

# WORLDOS Provenance and Data Fusion Engineering

This skill defines the rules, contracts, and algorithms for entity resolution, evidence linking, and multi-source fusion within WORLDOS.

---

## 1. Core Principle: Evidence First

Every entity, event, relationship, or observation stored in WORLDOS must be anchored to verifiable evidence.

```
Registered Source (e.g. World Bank, USGS)
       │
       ▼
Raw Ingestion Payload (Immutable JSON/Binary + SHA-256 Hash)
       │
       ▼
Evidence Record (evidence_id, source_id, fetched_at, payload_hash)
       │
       ▼
Observation (observed_at, metric_name, value, confidence, epistemic_tier)
       │
       ▼
Entity State / Event / Relationship (reconciled through Fusion Engine)
```

Never insert or mutate an entity state without an accompanying `evidence_id` and `source_id`.

---

## 2. Entity Resolution & Identity Hierarchy

Entity resolution reconciles observations from disparate external sources (e.g., World Bank country code `IND` and Natural Earth feature `ADM0_A3: IND`).

### Strict Identity Resolution Precedence:
1. **Primary Key / Internal UUID**: System-generated immutable entity ID.
2. **Publisher Identifiers (Highest External Authority)**:
   - ISO country codes (`ISO_A2`, `ISO_A3`, `ISO_N3`)
   - Official national identifiers (FAA, ICAO, MMSI, USGS Event IDs)
   - Canonical URI / Wikidata ID / OpenStreetMap relation ID
3. **Exact Normalized Name Match with Spatial Disambiguation**:
   - Only consider matches if the spatial bounding box or coordinates coincide within tolerance.
4. **Name-Only Match (NEVER AUTO-MERGE)**:
   - Identical or fuzzy string matches without matching publisher IDs or spatial confirmation must **NOT** be merged automatically.
   - Flag as `CONFLICT_PENDING_REVIEW` or keep as distinct entities with a `POTENTIAL_MATCH` relationship.

---

## 3. Epistemic Classification

All statements produced by fusion algorithms must be tagged:
- **`OBSERVED`**: Direct extraction from the raw feed without alteration.
- **`DERIVED`**: Deterministic computation (e.g. centroid calculation, population density from total population / area).
- **`INFERRED`**: Statistical or heuristic deduction (e.g. assigning a country based on nearest neighbor or fuzzy name).
- **`PREDICTED`**: Forward extrapolation beyond observed time.
- **`SIMULATED`**: Synthetic data generated for testing or scenarios.

---

## 4. Confidence Propagation and Degradation

Confidence is a floating-point value in $[0.0, 1.0]$.

### Rules for Confidence Scoring:
- Single official source (e.g. World Bank official API): $C_0 \approx 0.90 - 0.95$.
- Multi-source corroboration:
  $$C_{\text{fused}} = 1.0 - \prod_{i=1}^n (1.0 - C_i)$$
  Two independent sources with confidence $0.90$ yield $1.0 - (0.10 \times 0.10) = 0.99$.
- Conflicting sources:
  If Source A asserts $V_A$ and Source B asserts $V_B$ ($V_A \neq V_B$), confidence must be penalised:
  $$C_{\text{penalized}} = \frac{|C_A - C_B|}{\max(C_A, C_B) + \epsilon}$$
  Record both observations in the evidence history. Never silently overwrite or average conflicting claims without recording the contradiction.
- Temporal Decay:
  For volatile observations (e.g. live vehicle position, weather alert), apply exponential or half-life decay:
  $$C(t) = C_0 \cdot e^{-\lambda(t - t_{\text{observed}})}$$

---

## 5. Anti-Patterns to Avoid

- **Anti-Pattern 1: Auto-merging on Fuzzy String Match**: Merging "Georgia (country)" and "Georgia (US State)" because of string similarity.
- **Anti-Pattern 2: Overwriting History**: Using SQL `UPDATE entities SET value = new_val` without creating an `Observation` or audit history row.
- **Anti-Pattern 3: Uncited Syntheses**: An agent creating a combined profile without back-referencing each attribute's `evidence_id`.
- **Anti-Pattern 4: Silent Fallback to Average**: Averaging two completely contradictory numbers from two sources without logging a data conflict.
