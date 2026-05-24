"""Unit tests for slugify_vi — Vietnamese slug generation."""
import pytest
from admin.utils.text import slugify_vi

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("text, expected", [
    # Basic Vietnamese diacritics
    ("Sản phẩm Điện tử",     "san-pham-dien-tu"),
    ("Áo thun 100% Cotton",  "ao-thun-100-cotton"),
    # đ/Đ explicit mapping
    ("đường phố",            "duong-pho"),
    ("Đại học",              "dai-hoc"),
    # Tonal marks
    ("Hà Nội",               "ha-noi"),
    ("Hồ Chí Minh",          "ho-chi-minh"),
    # Already ASCII
    ("hello world",          "hello-world"),
    ("  spaces  ",           "spaces"),
    # Numbers
    ("Game 123",             "game-123"),
    # Special chars stripped
    ("100% chất lượng!",     "100-chat-luong"),
    # Multiple hyphens collapsed
    ("a---b",                "a-b"),
    # Empty input
    ("",                     ""),
])
def test_slugify_vi(text, expected):
    assert slugify_vi(text) == expected


def test_slugify_vi_no_leading_trailing_hyphens():
    result = slugify_vi("--hello--")
    assert not result.startswith("-")
    assert not result.endswith("-")
