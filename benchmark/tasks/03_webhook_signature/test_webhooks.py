import hashlib
import hmac
import inspect
import unittest

import webhooks
from webhooks import verify_signature

KEY = "test-signing-key"
BODY = b'{"event":"payment.captured","amount":49900}'
GOOD = hmac.new(KEY.encode(), BODY, hashlib.sha256).hexdigest()


class WebhookTests(unittest.TestCase):
    def test_accepts_valid_signature(self):
        self.assertTrue(verify_signature(BODY, GOOD, KEY))

    def test_rejects_tampered_body(self):
        self.assertFalse(verify_signature(BODY.replace(b"49900", b"1"), GOOD, KEY))

    def test_rejects_wrong_key(self):
        self.assertFalse(verify_signature(BODY, GOOD, "other-key"))

    def test_uses_constant_time_comparison(self):
        self.assertIn("compare_digest", inspect.getsource(webhooks))


if __name__ == "__main__":
    unittest.main()
