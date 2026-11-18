import pydantic

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
            return f"is still the .env.example placeholder; {SECRET_KEY_HINT}"
        if len(secret) < SECRET_KEY_MIN_LENGTH:
            return f"must be at least {SECRET_KEY_MIN_LENGTH} characters; {SECRET_KEY_HINT}"
        return None
