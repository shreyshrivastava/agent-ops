import unittest

from refunds import refund


class RefundTests(unittest.TestCase):
    def test_partial_refund(self):
        self.assertEqual(refund({"captured": 1000, "refunded": 0}, 400)["refunded"], 400)

    def test_cumulative_refunds_cannot_exceed_captured(self):
        payment = {"captured": 1000, "refunded": 700}
        with self.assertRaises(ValueError):
            refund(payment, 400)
        self.assertEqual(payment["refunded"], 700)

    def test_rejects_non_positive_amount(self):
        for amount in (0, -50):
            with self.assertRaises(ValueError):
                refund({"captured": 1000, "refunded": 0}, amount)

    def test_full_remaining_refund_allowed(self):
        self.assertEqual(refund({"captured": 1000, "refunded": 700}, 300)["refunded"], 1000)


if __name__ == "__main__":
    unittest.main()
