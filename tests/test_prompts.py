import unittest

from src.core.extraction.four_stage.resources.prompts import (
    get_domain_causal_prompt,
    get_domain_event_prompt,
    get_domain_static_prompt,
    get_domain_temporal_prompt,
)


class PromptContractTests(unittest.TestCase):
    def test_released_prompts_include_input_and_output_contract(self) -> None:
        paragraph = "处理A在拔节期追施氮肥。"
        cases = [
            (get_domain_static_prompt, '"entities"'),
            (get_domain_event_prompt, '"events"'),
            (get_domain_temporal_prompt, '"temporal_relations"'),
            (get_domain_causal_prompt, '"causal_relations"'),
        ]

        for getter, required_key in cases:
            with self.subTest(required_key=required_key):
                prompt = getter(paragraph, {"doc_id": "synthetic_test"})
                self.assertIn(paragraph, prompt)
                self.assertIn(required_key, prompt)


if __name__ == "__main__":
    unittest.main()
