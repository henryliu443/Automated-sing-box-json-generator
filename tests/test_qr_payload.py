import unittest

from automated_sing_box_generator.qr_payload import (
    COMPRESSED_JSON_MODE,
    MULTIPART_JSON_MODE,
    base45_decode,
    base45_encode,
    compact_json,
    decode_qr_json_tokens,
    make_qr_json_payload_plan,
)


class QRPayloadTests(unittest.TestCase):
    def test_base45_rfc_example_round_trips(self):
        self.assertEqual(base45_encode(b"AB"), "BB8")
        self.assertEqual(base45_decode("BB8"), b"AB")

    def test_compressed_payload_round_trips(self):
        config = {
            "dns": {"servers": [{"tag": "dns-remote", "address": "https://1.1.1.1/dns-query"}]},
            "outbounds": [{"type": "direct", "tag": "direct"}],
        }

        plan = make_qr_json_payload_plan(config, lambda token: not token.startswith("{"))

        self.assertEqual(plan.mode, COMPRESSED_JSON_MODE)
        self.assertEqual(decode_qr_json_tokens(plan.tokens), compact_json(config))

    def test_multipart_payload_round_trips_when_single_token_is_too_large(self):
        config = {
            "route": {
                "rules": [
                    {
                        "domain_suffix": f"example-{index}.invalid",
                        "outbound": f"proxy-{index}",
                    }
                    for index in range(250)
                ]
            }
        }

        plan = make_qr_json_payload_plan(
            config,
            lambda token: not token.startswith("{") and len(token) <= 180,
            chunk_body_size=90,
        )

        self.assertEqual(plan.mode, MULTIPART_JSON_MODE)
        self.assertGreater(len(plan.tokens), 1)
        self.assertTrue(all(len(token) <= 180 for token in plan.tokens))
        self.assertEqual(decode_qr_json_tokens(reversed(plan.tokens)), compact_json(config))

    def test_missing_multipart_chunk_is_rejected(self):
        config = {"items": [f"value-{index}" for index in range(300)]}
        plan = make_qr_json_payload_plan(
            config,
            lambda token: not token.startswith("{") and len(token) <= 160,
            chunk_body_size=80,
        )

        self.assertEqual(plan.mode, MULTIPART_JSON_MODE)
        with self.assertRaisesRegex(ValueError, "missing multipart QR chunk"):
            decode_qr_json_tokens(plan.tokens[:-1])


if __name__ == "__main__":
    unittest.main()
