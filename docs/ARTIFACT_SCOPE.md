# Artifact scope

This directory is a clean, prepublication snapshot assembled for peer review.
It is intentionally narrower than the development workspace.

## Included

- Four independent extraction stages: static, event, temporal, and causal.
- The Chinese prompt versions used by those stages.
- Source-location, schema-validation, retry, normalization, and Cypher helpers
  required by the four stages.
- The coarse and fine-grained evaluation implementation.
- Synthetic examples that contain no source-paper text.

## Excluded

- Original PDFs, processed source paragraphs, and full annotations.
- The 16,000-relation silver dataset and full prediction directories.
- Dataset-level statistics and all paper-level experimental results.
- Credentials, provider URLs, local paths, logs, and Git history.
- PDF preprocessing, table/image extraction, Phase 2 retrieval and QA, DSPy
  experiments, enterprise services, and future-work modules.
- The Qwen 2.5 32B ablation result until its recorded model identity is verified.

The exclusions protect third-party text rights and prepublication work. They also
mean that the public synthetic fixture validates the implementation and metric
code, but cannot independently regenerate every number in the paper table.
