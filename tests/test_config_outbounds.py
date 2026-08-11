import unittest
from automated_sing_box_generator.config import build_client_outbounds, build_domain_resolver, build_protocol_hosts


class TestClientOutboundsConfig(unittest.TestCase):

    def test_client_direct_outbound_uses_domain_resolver(self):
        creds = {
            "uuid": "test-uuid",
            "private_key": "test-prvkey",
            "public_key": "test-pubkey",
            "short_id": "test-shortid",
            "pwd_anytls": "pass1",
            "pwd_tuic": "pass2",
            "pwd_hy2": "pass3",
            "pwd_obfs": "pass4",
        }
        prefixes = {"reality": "r1", "hy2": "h1", "tuic": "t1"}
        hosts = build_protocol_hosts("example.com", prefixes)
        outbounds = build_client_outbounds(creds, hosts)
        
        direct_outbound = None
        for ob in outbounds:
            if ob.get("tag") == "direct":
                direct_outbound = ob
                break

        self.assertIsNotNone(direct_outbound, "direct outbound missing")
        self.assertNotIn("domain_strategy", direct_outbound, "legacy domain_strategy should be removed")
        self.assertIn("domain_resolver", direct_outbound, "domain_resolver should be present")
        self.assertEqual(direct_outbound["domain_resolver"], build_domain_resolver())


if __name__ == "__main__":
    unittest.main()
