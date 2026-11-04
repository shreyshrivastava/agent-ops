class GatewayTimeout(Exception):
    """The bank gateway did not respond in time. Safe to retry."""


class CardDeclined(Exception):
    """The bank declined the card. Never retry."""
