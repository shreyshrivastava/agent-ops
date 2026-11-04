import unittest

from billing import gst_paise, invoice_total


class GstTests(unittest.TestCase):
    def test_exact(self):
        self.assertEqual(gst_paise(10000), 1800)

    def test_rounds_half_up_not_to_even(self):
        self.assertEqual(gst_paise(125), 23)  # 22.5 -> 23
        self.assertEqual(gst_paise(25, 18), 5)  # 4.5 -> 5

    def test_invoice_total(self):
        self.assertEqual(invoice_total(125), 148)


if __name__ == "__main__":
    unittest.main()
