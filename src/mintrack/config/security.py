import pydantic
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

SECRET_KEY_MIN_LENGTH = 32
SECRET_KEY_PLACEHOLDER = "change-me-to-the-output-of-openssl-rand-hex-32"  # noqa: S105
SECRET_KEY_HINT = "generate one with `openssl rand -hex 32`"  # noqa: S105


class SecurityConfig(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(hide_input_in_errors=True)

    secret_key: pydantic.SecretStr | None = None

    def secret_key_problem(self) -> str | None:
        if self.secret_key is None:
            return f"is required in prod; {SECRET_KEY_HINT}"
        secret = self.secret_key.get_secret_value()
        if secret == SECRET_KEY_PLACEHOLDER:
            return f"is still the placeholder of docker-compose.yml; {SECRET_KEY_HINT}"
        if len(secret) < SECRET_KEY_MIN_LENGTH:
            return f"must be at least {SECRET_KEY_MIN_LENGTH} characters; {SECRET_KEY_HINT}"
        return None

    def derive_key(self, purpose: bytes, length: int = 32) -> bytes:
        """A key for one purpose, derived from the secret key with HKDF-SHA256 (RFC 5869)."""
        if self.secret_key is None:
            msg = "MINTRACK__SECURITY__SECRET_KEY is not set"
            raise ValueError(msg)
        hkdf = HKDF(algorithm=hashes.SHA256(), length=length, salt=None, info=purpose)
        return hkdf.derive(self.secret_key.get_secret_value().encode())
