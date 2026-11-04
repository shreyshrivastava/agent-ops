import unittest

from money import format_inr


class FormatInrTests(unittest.TestCase):
    def test_small_amounts(self):
        self.assertEqual(format_inr(0), "₹0.00")
        self.assertEqual(format_inr(99900), "₹999.00")

    def test_indian_digit_grouping(self):
        self.assertEqual(format_inr(100000), "₹1,000.00")
        self.assertEqual(format_inr(12345678), "₹1,23,456.78")
        self.assertEqual(format_inr(1000000000), "₹1,00,00,000.00")

    def test_negative(self):
        self.assertEqual(format_inr(-150050), "-₹1,500.50")


if __name__ == "__main__":
    unittest.main()
