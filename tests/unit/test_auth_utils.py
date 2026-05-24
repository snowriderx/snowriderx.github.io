"""Unit tests for DES auth utilities — encrypt/decrypt round-trips."""
import pytest
from admin.utils.auth import (
    encrypt, decrypt,
    encrypt1, decrypt1,
    extract_user_id_from_cookie,
    make_auth_cookie,
    kill_chars,
)

pytestmark = pytest.mark.unit


class TestEncryptDecrypt:
    def test_round_trip(self):
        assert decrypt(encrypt("hello")) == "hello"

    def test_round_trip_vietnamese(self):
        plain = "Mật khẩu 123"
        assert decrypt(encrypt(plain)) == plain

    def test_round_trip1(self):
        assert decrypt1(encrypt1("test123")) == "test123"

    def test_different_keys(self):
        ct = encrypt("same")
        ct1 = encrypt1("same")
        assert ct != ct1

    def test_known_pattern(self):
        # Cookie stores IDU + "Admin123123!@#"
        ct = encrypt("5Admin123123!@#")
        assert decrypt(ct) == "5Admin123123!@#"


class TestMakeAuthCookie:
    def test_extractable(self):
        cookie = make_auth_cookie(42)
        assert extract_user_id_from_cookie(cookie) == 42

    def test_user_id_1(self):
        assert extract_user_id_from_cookie(make_auth_cookie(1)) == 1

    def test_user_id_large(self):
        assert extract_user_id_from_cookie(make_auth_cookie(9999)) == 9999


class TestExtractUserIdFromCookie:
    def test_valid(self):
        cookie = make_auth_cookie(7)
        assert extract_user_id_from_cookie(cookie) == 7

    def test_invalid_raises(self):
        bad = encrypt("Admin123123!@#")   # no leading digit
        with pytest.raises(ValueError):
            extract_user_id_from_cookie(bad)


@pytest.mark.parametrize("ch", ["'", '"', ";", "<", ">", "\\"])
def test_kill_chars_strips_injection(ch):
    assert ch not in kill_chars(f"user{ch}name")


def test_kill_chars_clean_input_unchanged():
    assert kill_chars("admin") == "admin"


def test_kill_chars_strips_whitespace():
    assert kill_chars("  admin  ") == "admin"
