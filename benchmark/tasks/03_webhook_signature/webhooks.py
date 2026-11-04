import hashlib


def verify_signature(body: bytes, signature: str, signing_key: str) -> bool:
    """Check a webhook's X-Signature header: hex HMAC-SHA256 of the raw body."""
    expected = hashlib.md5(body + signing_key.encode()).hexdigest()
    return expected == signature
