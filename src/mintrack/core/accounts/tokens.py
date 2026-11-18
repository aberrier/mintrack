import hashlib
import secrets


def hash_token(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


def new_token() -> tuple[str, bytes]:
    """A random token for the client and the hash stored in its place."""
    token = secrets.token_urlsafe(32)
    return token, hash_token(token)


def password_link(public_origin: str, token: str) -> str:
    """The page that sets a password; the token sits in the fragment, which browsers never send to servers."""
    return f"{public_origin}/password#{token}"
