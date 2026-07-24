# Evaluation implementation

The released evaluator supports micro-averaged precision, recall, and F1. The
synthetic smoke test in this repository can be run with:

```yaml
static_metric: combined
match_mode: relaxed_ultra
eval_scope: positive_only
```

`combined` joins static entities and static relations for the static score.
`positive_only` evaluates each knowledge type only on documents whose gold
annotation contains at least one item of that type.

For `relaxed_ultra`, names are lowercased, whitespace/punctuation are normalized,
and exact or containment matching is attempted first. Longer strings also use
`SequenceMatcher` with a threshold of 0.80; short strings use 0.85. Once names
match, entity type, event category, and relation type do not constrain the match.
This is intentionally permissive and can be interpreted together with the
fine-grained slot metrics.

The evaluator also supports `strict`, `relaxed`, and `relaxed_plus`. No
paper-level scores or real-dataset aggregate statistics are included in this
prepublication artifact.
