import unittest

from debate.schema import (
    parse_json_object,
    strip_json_fence,
    validate_agent_reply,
    validate_chair_reply,
)


class DebateSchemaTests(unittest.TestCase):
    def test_strip_fence(self):
        raw = """```json
{"side": "hold", "confidence": 0.5, "rationale": "x"}
```"""
        self.assertIn('"side"', strip_json_fence(raw))

    def test_parse_agent(self):
        text = '{"role":"TrendAgent","side":"buy","entry_price":25000,"confidence":0.6,"rationale":"ok"}'
        obj = parse_json_object(text)
        a = validate_agent_reply(obj)
        self.assertEqual(a["side"], "buy")
        self.assertEqual(a["entry_price"], 25000.0)

    def test_parse_chair(self):
        text = '{"side":"hold","entry_price":null,"confidence":0.4,"rationale":"wait","dissent_summary":"split"}'
        obj = parse_json_object(text)
        c = validate_chair_reply(obj)
        self.assertEqual(c["side"], "hold")
        self.assertIsNone(c["entry_price"])

    def test_invalid_side_raises(self):
        with self.assertRaises(ValueError):
            validate_agent_reply({"side": "long", "confidence": 1, "rationale": ""})


if __name__ == "__main__":
    unittest.main()
