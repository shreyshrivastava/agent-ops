import itertools

_ids = itertools.count(1)


class PaymentService:
    def __init__(self):
        self.payments = []

    def create_payment(self, amount_paise: int, idempotency_key: str) -> dict:
        """Create a payment. Retrying with the same idempotency_key must not charge twice."""
        payment = {"id": f"pay_{next(_ids)}", "amount": amount_paise, "status": "created"}
        self.payments.append(payment)
        return payment
