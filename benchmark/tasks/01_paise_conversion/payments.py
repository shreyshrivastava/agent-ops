def to_paise(amount: str) -> int:
    """Convert a rupee amount string like '19.99' to integer paise (1999)."""
    return int(float(amount) * 100)
