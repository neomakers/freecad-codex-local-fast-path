import os
import unittest
from unittest.mock import patch

from codex_freecad_bridge import (
    DEFAULT_CODEX_MODEL,
    build_codex_prompt,
    encode_codex_stdin,
    resolve_codex_model,
)


class CodexBridgeEncodingTests(unittest.TestCase):
    def test_prompt_is_written_as_utf8_on_windows_locales(self):
        body = {
            "messages": [
                {"role": "user", "content": "\u4f60\u662f\u4ec0\u4e48\u6a21\u578b\uff1f\u8bf7\u521b\u5efa\u4e00\u4e2a\u76d2\u5b50"},
                {
                    "role": "tool",
                    "content": "\u5df2\u521b\u5efa\uff1a40 x 30 x 20 mm",
                    "tool_call_id": "call-1",
                },
            ],
            "tools": [],
        }
        prompt = build_codex_prompt(body)
        encoded = encode_codex_stdin(prompt)

        self.assertEqual(encoded.decode("utf-8"), prompt)
        self.assertIn("\u4f60\u662f\u4ec0\u4e48\u6a21\u578b", encoded.decode("utf-8"))

    def test_malformed_surrogate_cannot_break_the_pipe(self):
        encoded = encode_codex_stdin("prefix\ud800suffix")

        self.assertEqual(encoded.decode("utf-8"), "prefix?suffix")

    def test_cli_model_has_a_supported_default_and_override(self):
        with patch.dict(os.environ, {"CODEX_BRIDGE_MODEL": ""}, clear=False):
            self.assertEqual(resolve_codex_model(), DEFAULT_CODEX_MODEL)
        with patch.dict(os.environ, {"CODEX_BRIDGE_MODEL": "gpt-custom"}, clear=False):
            self.assertEqual(resolve_codex_model(), "gpt-custom")


if __name__ == "__main__":
    unittest.main()
