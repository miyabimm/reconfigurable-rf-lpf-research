# Historical Phase 2 repository reviews

Research source evidence and the original review decisions are immutable Git history, not active operational data. This directory continues to hold evidence recovery records which current manual verification scripts use.

The original Step 4 static tree inventories were removed from today's checkout for lightweight maintenance; recover original bytes from commit [`cd129eabaebb`](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/tree/cd129eabaebb3a5581533d4cfcbd55cef4765117):

- [Historical `step4_historical_documents_20261017.csv`](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/cd129eabaebb3a5581533d4cfcbd55cef4765117/data/repository_reviews/step4_historical_documents_20261017.csv) — fixed dated audit output, not an RF numerical result.
- [Historical `step4_identical_blob_groups_20261017.csv`](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/cd129eabaebb3a5581533d4cfcbd55cef4765117/data/repository_reviews/step4_identical_blob_groups_20261017.csv) — fixed dated audit output, not an RF numerical result.
- [Historical `step4_summary_20261017.json`](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/cd129eabaebb3a5581533d4cfcbd55cef4765117/data/repository_reviews/step4_summary_20261017.json) — fixed dated audit output, not an RF numerical result.
- [Historical `step5_integration_20261017.json`](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/cd129eabaebb3a5581533d4cfcbd55cef4765117/data/repository_reviews/step5_integration_20261017.json) — fixed dated audit output, not an RF numerical result.

Active historical evidence retained in this directory includes the [original 46-item preservation list](step4_retention_46_20261017.csv), EXP-042 recovered original ZIP and members, and EXP-046/047 original-source crosswalk. This directory's original Step 4 explanatory report is [the fixed pre-retirement Step 4 report](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/0bf0e3a41e2ed2a5ae4e734ccec71bc530c19a53/docs/phase2_repository_step4_review_20261017.md). The retired report generator is recoverable at the same pinned commit: [`scripts/audit_repository_reorganization_step4.py`](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/f4fee54a4f4a48c1cb42bc1eae2ed8e3ad52d6a3/scripts/audit_repository_reorganization_step4.py).

Original B/C review of 225 experiment/validation paths (128 preserve originals, 81 numeric equivalence not verified, 16 consolidation-review candidates): [historical CSV](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/214cbb21e87d3f3e99177d4a7c9eaf741a74394b/data/repository_reviews/phase2_Bc_evidence_screening_225_20261018.csv). It is a dated, non-numerical *review classification*, not a substitute for any of the 225 retained original files or modern RF validation. For the original per-path SHAs and gates use this immutable CSV.

## Issue #170: all-data path classification (read-only)

The [2026-10-28 353-path inventory](issue170_data_path_classification_20261028.csv) classifies **every tracked `data/` blob at fixed main `abd17302b9e5fda20f697e60e691add8514a0f9a`** by functional role and Git blob SHA-1. The inventory itself was created later on the Draft PR branch and is not among those 353 original files. The [data entrypoint](../README.md) explains all 10 groups, formal/trial versus dated report semantics, and exact blob duplicates.

The inventory lists byte-identical Git blobs without treating them as disposable replicas. In particular, preserved EXP-042 ZIP/member bytes, EXP-046/047 source crosswalk, old validation logs, source/checkpoint SHA, and immutable formal inputs **remain unchanged**. Every row explicitly indicates that a complete per-path consumer/manifest/workflow/dynamic-reference audit is **not yet performed**; neither byte identity nor this classification authorizes any deletion, file migration or new RF conclusion. Recheck the baseline tree and individual evidence before proposing retirement. Follow the owner-approval gates in [Issue #170](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/170).

Phase 2 continues; Phase 3 requires explicit owner approval.
