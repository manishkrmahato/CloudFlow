from app.security import hash_password, verify_password


def test_password_hash_verifies():
    stored = hash_password("long-secure-password")
    assert stored != "long-secure-password"
    assert verify_password("long-secure-password", stored)
    assert not verify_password("incorrect", stored)
