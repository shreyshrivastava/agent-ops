import unittest

from orders import PaymentService


class IdempotencyTests(unittest.TestCase):
    def test_retry_returns_same_payment(self):
        service = PaymentService()
        first = service.create_payment(49900, "key-1")
        second = service.create_payment(49900, "key-1")
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(len(service.payments), 1)

    def test_different_keys_create_new_payments(self):
        service = PaymentService()
        service.create_payment(100, "a")
        service.create_payment(100, "b")
        self.assertEqual(len(service.payments), 2)

    def test_reused_key_with_different_amount_is_rejected(self):
        service = PaymentService()
        service.create_payment(100, "k")
        with self.assertRaises(ValueError):
            service.create_payment(200, "k")


if __name__ == "__main__":
    unittest.main()
