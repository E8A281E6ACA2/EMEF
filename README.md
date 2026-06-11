# EMEF

**EMEF: An Evidence-Grounded Multi-View Extraction Framework for Fine-Grained Agricultural Knowledge Organization**

## Overview

Agricultural scientific literature contains rich knowledge about crops, environments, management practices, temporal processes, and causal mechanisms. Traditional knowledge graph construction methods mainly rely on static entity–relation triples, making it difficult to represent complex agronomic processes involving events, temporal evolution, and condition-dependent causality.

EMEF (Evidence-Grounded Multi-View Extraction Framework) is a framework designed for fine-grained agricultural knowledge organization from scientific literature.

The framework organizes extracted knowledge into four complementary agronomic views:

* **Static Facts** – What it is
* **Dynamic Events** – What was done
* **Temporal Flow** – When it happened
* **Causal Mechanisms** – Why it happened

To improve reliability and traceability, EMEF integrates:

* Evidence-grounded extraction
* Agronomic view isolation
* Candidate downgrading and quality control
* Paragraph-level evidence anchoring
* Global Virtual Anchors (GVAs)
* Non-destructive global soft alignment

The framework aims to transform open-ended LLM extraction into a more structured, auditable, and evidence-verifiable knowledge organization process.

---

## Framework

<p align="center">
  <img src="figures/framework.png" width="900">
</p>

*Overall architecture of EMEF.*

---

## Key Features

### Multi-View Knowledge Organization

EMEF separates agricultural knowledge into four mutually exclusive yet complementary views:

| View              | Description                                         |
| ----------------- | --------------------------------------------------- |
| Static Facts      | Entities, attributes and stable relations           |
| Dynamic Events    | Agricultural operations and experimental treatments |
| Temporal Flow     | Phenological and procedural temporal relations      |
| Causal Mechanisms | Condition-dependent factor–response relations       |

---

### Evidence-Grounded Extraction

Each extracted knowledge unit is linked to paragraph-level evidence spans and source document coordinates.

This enables:

* Traceability
* Evidence verification
* Auditable knowledge services

---

### Candidate Downgrading

Instead of directly discarding uncertain outputs, EMEF introduces a candidate pool for:

* Boundary-conflicting knowledge
* Structurally incomplete results
* Low-confidence extractions

This preserves potentially useful mechanistic information while protecting the high-confidence graph.

---

### Global Soft Alignment

EMEF introduces **Global Virtual Anchors (GVAs)** to connect semantically equivalent entities across documents.

Unlike hard entity merging, soft alignment:

* Preserves local context
* Retains source evidence
* Avoids semantic collapse
* Supports cross-document retrieval

---

## Experimental Results

Experiments on large-scale wheat literature demonstrate that:

* Multi-view extraction significantly increases knowledge granularity.
* Evidence-grounded extraction improves extraction precision and reliability.
* Candidate downgrading reduces information loss caused by strict filtering.
* Global soft alignment alleviates entity fragmentation while preserving contextual evidence.
* The framework consistently improves extraction performance across different LLM backbones.

---

## Repository Status

🚧 The repository is currently under active development.

Code, datasets, prompts, and evaluation scripts will be released progressively.

Planned releases include:

* [ ] Extraction pipeline
* [ ] Multi-view schemas
* [ ] Prompt templates
* [ ] Quality-control modules
* [ ] Soft-alignment implementation
* [ ] Evaluation benchmarks



---

## License

License information will be released together with the source code.
