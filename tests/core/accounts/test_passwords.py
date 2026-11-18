from mintrack.core.accounts.passwords import hash_password, needs_rehash, verify_password
from mintrack.core.accounts.tokens import hash_token, new_token


def test_a_password_matches_only_its_hash() -> None:
    password_hash = hash_password("correct horse battery staple")

    assert verify_password(password_hash, "correct horse battery staple") is True
    assert verify_password(password_hash, "wrong") is False
    assert verify_password(None, "anything") is False
    assert verify_password("not a hash", "anything") is False
    assert needs_rehash(password_hash) is False


def test_tokens_are_random_and_stored_as_their_sha256() -> None:
    token, token_hash = new_token()

    assert len(token) >= 43
    assert hash_token(token) == token_hash
    assert len(token_hash) == 32
    assert new_token()[0] != token
