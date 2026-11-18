import base64

import sqlalchemy as sa
from cryptography.fernet import Fernet, InvalidToken

from mintrack.config import get_config


class EncryptedText(sa.TypeDecorator[str]):
    """Text encrypted with Fernet under a key derived from the secret key for `purpose`.

    A value that no longer decrypts (the secret key changed) reads as None.
    """

    impl = sa.TEXT
    cache_ok = True

    def __init__(self, purpose: bytes) -> None:
        super().__init__()
        self.purpose = purpose

    def _fernet(self) -> Fernet:
        return Fernet(base64.urlsafe_b64encode(get_config().security.derive_key(self.purpose)))

    def process_bind_param(self, value: str | None, dialect: sa.Dialect) -> str | None:  # noqa: ARG002
        return None if value is None else self._fernet().encrypt(value.encode()).decode()

    def process_result_value(self, value: str | None, dialect: sa.Dialect) -> str | None:  # noqa: ARG002
        if value is None:
            return None
        try:
            return self._fernet().decrypt(value).decode()
        except InvalidToken:
            return None
