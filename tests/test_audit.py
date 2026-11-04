import unittest

from local_agent_ops.audit import audit_manifest


def _manifest(**extra):
    base = {
        "agent": {},
        "model": {"provider": "local", "endpoint": "http://127.0.0.1", "name": "model"},
        "channels": [],
        "controls": {"approval_required_for": ["destructive_operations"]},
    }
    base.update(extra)
    return base


class AuditManifestTests(unittest.TestCase):
    def test_accepts_sanitized_manifest(self) -> None:
        self.assertEqual(audit_manifest(_manifest())["errors"], [])

    def test_rejects_potential_secret_field(self) -> None:
        result = audit_manifest(_manifest(api_key="do-not-publish"))
        self.assertTrue(any("api_key" in error for error in result["errors"]))

    def test_ignores_lookalike_keys(self) -> None:
        result = audit_manifest(
            _manifest(model_options={"max_tokens": 512, "session_timeout": 30, "tokenizer": "bpe"})
        )
        self.assertEqual(result["errors"], [])

    def test_flags_secret_keys_in_any_style(self) -> None:
        for key in ("authToken", "client-secret", "AWS_ACCESS_KEY", "session_id", "Password"):
            with self.subTest(key=key):
                self.assertTrue(audit_manifest(_manifest(**{key: "x"}))["errors"])

    def test_flags_nested_container_under_secret_key(self) -> None:
        result = audit_manifest(_manifest(credentials={"value": "x"}))
        self.assertTrue(any("credentials" in error for error in result["errors"]))

    def test_flags_empty_secret_container(self) -> None:
        self.assertTrue(audit_manifest(_manifest(api_key={}))["errors"])

    def test_flags_known_token_values(self) -> None:
        values = (
            "sk-abcdefgh12345678",
            "ghp_" + "a" * 36,
            "xoxb-123-456",
            "AKIA" + "A" * 16,
            "eyJhbGciOi.eyJzdWIiOi.sig",
            "Bearer abc123",
        )
        for value in values:
            with self.subTest(value=value[:6]):
                self.assertTrue(audit_manifest(_manifest(note=value))["errors"])


if __name__ == "__main__":
    unittest.main()
