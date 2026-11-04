import unittest

from gateway import CardDeclined, GatewayTimeout, call_with_retry


def flaky(failures, error=GatewayTimeout):
    calls = []

    def call():
        calls.append(1)
        if len(calls) <= failures:
            raise error()
        return "ok"

    return call, calls


class RetryTests(unittest.TestCase):
    def test_retries_timeouts_until_success(self):
        call, calls = flaky(2)
        self.assertEqual(call_with_retry(call, attempts=3), "ok")
        self.assertEqual(len(calls), 3)

    def test_gives_up_after_attempts(self):
        call, calls = flaky(5)
        with self.assertRaises(GatewayTimeout):
            call_with_retry(call, attempts=3)
        self.assertEqual(len(calls), 3)

    def test_never_retries_declines(self):
        call, calls = flaky(1, CardDeclined)
        with self.assertRaises(CardDeclined):
            call_with_retry(call, attempts=3)
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
