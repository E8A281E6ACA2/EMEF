# Model configuration and reproducibility boundary

The method performs zero-shot prompted inference through an OpenAI-compatible
API. There are no training epochs, learning rate, optimizer, fine-tuned weights,
or model checkpoints produced by this repository.

`configs/paper_models.yaml` provides a reference inference configuration
supported by the current code. It is not a record of the withheld paper runs.

Provider endpoints and paper-run model identities are intentionally omitted.
Because online models are mutable, the repository does not claim bitwise
reproduction of model responses.
