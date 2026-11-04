def refund(payment: dict, amount_paise: int) -> dict:
    """Refund part of a captured payment. payment = {"captured": int, "refunded": int}."""
    if amount_paise > payment["captured"]:
        raise ValueError("refund exceeds captured amount")
    payment["refunded"] += amount_paise
    return payment
