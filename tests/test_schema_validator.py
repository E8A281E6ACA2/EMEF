import json
import unittest
from pathlib import Path

from src.core.extraction.four_stage.pipeline.schema_validator import validate_payload


class SchemaValidatorTests(unittest.TestCase):
    def test_synthetic_gold_matches_stage_contracts(self) -> None:
        root = Path(__file__).resolve().parents[1]
        fixture = root / "examples" / "evaluation" / "gold" / "wheat_gold_001"

        for stage in ("static", "event", "temporal", "causal"):
            with self.subTest(stage=stage):
                payload = json.loads((fixture / f"{stage}.json").read_text(encoding="utf-8"))
                valid, reason = validate_payload(stage, payload)
                self.assertTrue(valid, reason)


if __name__ == "__main__":
    unittest.main()
