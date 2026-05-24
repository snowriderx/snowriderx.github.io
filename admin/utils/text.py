"""
Text utilities — Vietnamese slug generation.

Vietnamese text requires two steps beyond standard slugify:
  1. đ → d  (doesn't decompose via NFD)
  2. NFD decompose → strip combining diacritical marks (category Mn)
     e.g. ả → a + ̉ → a

The JS mirror in product/form.html must produce identical output so that
the client-side preview matches what the server will persist.
"""

import re
import unicodedata


# Characters whose NFD decomposition doesn't strip cleanly — map explicitly.
_EXPLICIT = str.maketrans(
    "đĐ",
    "dD",
)


def slugify_vi(text: str) -> str:
    """
    Convert a Vietnamese product name to a lowercase ASCII URL slug.

    Steps:
      1. Explicit replacements (đ→d)
      2. NFD decompose; drop combining marks (category Mn)
      3. Lowercase
      4. Keep only [a-z0-9] and whitespace/hyphens
      5. Collapse whitespace → single hyphen
      6. Strip leading/trailing hyphens

    Examples:
      "Sản phẩm Điện tử"   → "san-pham-dien-tu"
      "Áo thun  100% Cotton" → "ao-thun-100-cotton"
    """
    if not text:
        return ""

    text = text.translate(_EXPLICIT)
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s\-]+", "-", text.strip())
    return text.strip("-")
