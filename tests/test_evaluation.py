import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class EvaluationSmokeTests(unittest.TestCase):
    def test_identical_synthetic_predictions_score_one(self) -> None:
        root = Path(__file__).resolve().parents[1]
        script = root / "scripts" / "evaluation" / "score_gold_predictions.py"
        gold = root / "examples" / "evaluation" / "gold"
        predictions = root / "examples" / "evaluation" / "predictions"

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "score"
            subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--gold-dir",
                    str(gold),
                    "--pred-dir",
                    str(predictions),
                    "--static-metric",
                    "combined",
                    "--match-mode",
                    "relaxed_ultra",
                    "--eval-scope",
                    "positive_only",
                    "--output",
                    str(output),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            metrics = json.loads(output.with_suffix(".json").read_text(encoding="utf-8"))

        for stage in ("static", "event", "temporal", "causal"):
            with self.subTest(stage=stage):
                self.assertEqual(metrics[stage]["precision"], 1.0)
                self.assertEqual(metrics[stage]["recall"], 1.0)
                self.assertEqual(metrics[stage]["f1"], 1.0)

    def test_identical_synthetic_predictions_have_perfect_slot_scores(self) -> None:
        root = Path(__file__).resolve().parents[1]
        script = root / "scripts" / "evaluation" / "score_gold_finegrained.py"
        gold = root / "examples" / "evaluation" / "gold"
        predictions = root / "examples" / "evaluation" / "predictions"

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "fine"
            subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--gold-dir",
                    str(gold),
                    "--pred-dir",
                    str(predictions),
                    "--output",
                    str(output),
                    "--model",
                    "synthetic",
                    "--match-mode",
                    "relaxed_ultra",
                    "--eval-scope",
                    "positive_only",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            metrics = json.loads(output.with_suffix(".json").read_text(encoding="utf-8"))

        for stage in ("entity", "event", "temporal", "causal"):
            with self.subTest(stage=stage):
                self.assertEqual(metrics["slot_f1"][stage]["f1"], 1.0)


if __name__ == "__main__":
    unittest.main()
