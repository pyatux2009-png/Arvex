from app.api.routes import _password_hash, _verify_password


def test_password_hash_verifies_correct_password():
    encoded = _password_hash("correct horse battery staple")
    assert encoded != "correct horse battery staple"
    assert _verify_password("correct horse battery staple", encoded)


def test_password_hash_rejects_wrong_password():
    encoded = _password_hash("correct horse battery staple")
    assert not _verify_password("incorrect password", encoded)


def test_password_hash_uses_a_random_salt():
    first = _password_hash("same password")
    second = _password_hash("same password")
    assert first != second
