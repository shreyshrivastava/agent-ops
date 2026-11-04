import unittest

from settlements import settlement_report

PAYMENTS = [
    {"id": "1", "method": "upi", "status": "captured", "amount": 49900},
    {"id": "2", "method": "card", "status": "failed", "amount": 120000},
    {"id": "3", "method": "upi", "status": "captured", "amount": 100},
    {"id": "4", "method": "card", "status": "captured", "amount": 5000},
    {"id": "5", "method": "netbanking", "status": "refunded", "amount": 700},
]


class SettlementReportTests(unittest.TestCase):
    def test_captured_totals_by_method(self):
        self.assertEqual(settlement_report(PAYMENTS), {"upi": 50000, "card": 5000})

    def test_empty(self):
        self.assertEqual(settlement_report([]), {})


if __name__ == "__main__":
    unittest.main()
