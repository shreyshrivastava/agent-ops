import unittest

from payments import to_paise


class ToPaiseTests(unittest.TestCase):
    def test_whole_rupees(self):
        self.assertEqual(to_paise("500"), 50000)

    def test_float_trap_amounts(self):
        self.assertEqual(to_paise("0.29"), 29)
        self.assertEqual(to_paise("19.99"), 1999)
        self.assertEqual(to_paise("1.15"), 115)

    def test_rejects_sub_paise(self):
        with self.assertRaises(ValueError):
            to_paise("1.005")


if __name__ == "__main__":
    unittest.main()
