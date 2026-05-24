"""
Authentication utilities — exact port of Bambu.oNet.Encrypt/Decrypt.

Algorithm (reverse-engineered from Bambu.Portal_2.0.dll):
  - Cipher : DES in CBC mode
  - Key    : b'ZeroCool'  (8 bytes, ASCII)
  - IV     : b'ZeroCool'  (8 bytes, ASCII)
  - Padding: PKCS7 (standard .NET CryptoStream default)
  - Input  : UTF-8 string
  - Output : Base64 string

Bambu.oNet.Encrypt1 / Decrypt1 use the same algorithm with:
  - Key    : b'ZeroCoo1'  (note: digit 1, not letter l)
  - IV     : b'ZeroCoo1'

Evidence trail:
  1. strings(Bambu.Portal_2.0.dll) shows DESCryptoServiceProvider,
     CreateEncryptor, CreateDecryptor, ToBase64String, FromBase64String.
  2. #US heap (UTF-16LE string literals) at offset 0xa9b4 = 'ZeroCool'
     and 0xaad2 = 'ZeroCoo1' — both exactly 8 bytes (DES key size).
  3. Round-trip verified in Python: all plaintext → encrypt → decrypt
     produce the original value.
  4. Cookie simulation: Encrypt("5Admin123123!@#") decrypts back to
     "5Admin123123!@#"; Val() / int(re.match(r'\\d+', ...)) extracts IDU=5.

Requires: pycryptodome  (pip install pycryptodome)
"""

import base64
import re

from Crypto.Cipher import DES

# ── SECURITY NOTE ─────────────────────────────────────────────────────────
# DES with a hardcoded 56-bit key is cryptographically broken.  These
# constants CANNOT be changed without migrating every password hash in the
# DB AND updating the parallel VB pages that use the same Bambu.oNet DLL.
#
# Migration path (once VB is fully retired):
#   1. Add a `bcrypt_hash` column to tblUser.
#   2. On first successful DES login, compute bcrypt hash and store it.
#   3. Transition login to prefer bcrypt; fall back to DES until all users
#      have a bcrypt hash.
#   4. Drop DES paths and the _KEY constants.
# ──────────────────────────────────────────────────────────────────────────

# Primary pair — used by Encrypt() / Decrypt() in login.aspx, pass.aspx
_KEY = b'ZeroCool'
_IV = b'ZeroCool'

# Secondary pair — used by Encrypt1() / Decrypt1() (less common)
_KEY1 = b'ZeroCoo1'
_IV1 = b'ZeroCoo1'


def _pad(data: bytes) -> bytes:
    """PKCS7 pad to 8-byte DES block boundary."""
    pad_len = 8 - (len(data) % 8)
    return data + bytes([pad_len] * pad_len)


def _unpad(data: bytes) -> bytes:
    """Remove PKCS7 padding."""
    return data[: -data[-1]]


# ------------------------------------------------------------------ #
# Public API — mirrors Bambu.oNet exactly
# ------------------------------------------------------------------ #

def encrypt(plain: str) -> str:
    """
    Replicate Bambu.oNet.Encrypt(plain).
    Use for: verifying login, storing new passwords, building cookies.
    """
    cipher = DES.new(_KEY, DES.MODE_CBC, _IV)
    ct = cipher.encrypt(_pad(plain.encode("utf-8")))
    return base64.b64encode(ct).decode()


def decrypt(ciphertext: str) -> str:
    """
    Replicate Bambu.oNet.Decrypt(ciphertext).
    Use for: reading __tkad_id cookie to extract IDU.
    """
    raw = base64.b64decode(ciphertext)
    cipher = DES.new(_KEY, DES.MODE_CBC, _IV)
    return _unpad(cipher.decrypt(raw)).decode("utf-8")


def encrypt1(plain: str) -> str:
    """Replicate Bambu.oNet.Encrypt1(plain)."""
    cipher = DES.new(_KEY1, DES.MODE_CBC, _IV1)
    ct = cipher.encrypt(_pad(plain.encode("utf-8")))
    return base64.b64encode(ct).decode()


def decrypt1(ciphertext: str) -> str:
    """Replicate Bambu.oNet.Decrypt1(ciphertext)."""
    raw = base64.b64decode(ciphertext)
    cipher = DES.new(_KEY1, DES.MODE_CBC, _IV1)
    return _unpad(cipher.decrypt(raw)).decode("utf-8")


def extract_user_id_from_cookie(cookie_value: str) -> int:
    """
    Replicate the VB pattern:
        Val(Bambu.oNet.Decrypt(Request.Cookies("__tkad_id").Value))

    Cookie stores: Encrypt(str(IDU) + "Admin123123!@#")
    Decrypt gives: "5Admin123123!@#"
    Val() stops at first non-digit → 5
    """
    decrypted = decrypt(cookie_value)
    match = re.match(r"\d+", decrypted)
    if not match:
        raise ValueError(
            f"Cookie did not start with a numeric IDU: {decrypted!r}"
        )
    return int(match.group())


def make_auth_cookie(user_id: int) -> str:
    """
    Build the __tkad_id cookie value.
    Replicate: Bambu.oNet.Encrypt(IDU & "Admin123123!@#")
    """
    return encrypt(f"{user_id}Admin123123!@#")


def kill_chars(value: str) -> str:
    """
    Replicate Bambu.oNet.KillChars() — strips SQL-injection characters.
    Applied to the username field before the login query.
    Removes: single quotes, double quotes, semicolons, angle brackets,
    backslashes.
    Note: SQLAlchemy uses parameterised queries so this is redundant for
    injection safety, but must stay to match the VB login query exactly.
    """
    for ch in ("'", '"', ";", "<", ">", "\\"):
        value = value.replace(ch, "")
    return value.strip()
