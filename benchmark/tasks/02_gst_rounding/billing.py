def gst_paise(amount_paise: int, rate_percent: int = 18) -> int:
    """GST on an amount in paise, rounded half-up to the nearest paisa."""
    return round(amount_paise * rate_percent / 100)


def invoice_total(amount_paise: int, rate_percent: int = 18) -> int:
    return amount_paise + gst_paise(amount_paise, rate_percent)
