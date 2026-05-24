"""
HTML sanitizer for CKEditor output.

Uses nh3 (Rust-backed ammonia, maintained successor to bleach).
A single Cleaner instance is built once at import time and reused
across requests — construction is the expensive part.

Design decisions
----------------
* Allowlist approach: only known-safe tags and attributes pass through.
* `style` attributes are kept but filtered to a property whitelist so
  CKEditor's inline formatting (color, text-align, …) is preserved while
  `expression()` and other CSS injection vectors are blocked.
* `data-*` prefixes are allowed globally — CKEditor 5 uses them heavily
  for widget metadata.
* `iframe` is allowed so CKEditor's Media Embed plugin (YouTube, Vimeo)
  works.  Only http/https/mailto/tel URL schemes are permitted on href/src.
* nh3 automatically appends rel="noopener noreferrer" to every <a> so
  `rel` is intentionally excluded from the per-tag attribute list.
* DO NOT call sanitize_html() on intentional embed/script fields
  (ScriptP, sCode) — those are purposely raw.
"""

import nh3

# ── Allowed tags ──────────────────────────────────────────────────────
_TAGS = {
    # Block
    "p", "div",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "blockquote", "pre", "hr", "br", "address",
    # Lists
    "ul", "ol", "li", "dl", "dt", "dd",
    # Inline
    "span", "strong", "b", "em", "i", "u", "s", "strike",
    "sub", "sup", "code", "kbd", "mark", "small", "abbr",
    # Media / link
    "a", "img", "picture", "source", "figure", "figcaption",
    # CKEditor 5 Media Embed: <oembed url="..."> inside <figure class="media">
    "oembed",
    # CKEditor 5 video/audio (file upload path)
    "video", "audio",
    # Table
    "table", "thead", "tbody", "tfoot",
    "tr", "th", "td", "caption", "colgroup", "col",
    # Embed (Media Embed plugin)
    "iframe",
    # Misc
    "details", "summary",
}

# ── Allowed attributes ────────────────────────────────────────────────
# "*" applies to every tag; per-tag keys extend on top.
_ATTRIBUTES: dict[str, set[str]] = {
    "*":        {"class", "style", "id", "title", "lang", "dir"},
    "a":        {"href", "target"},         # rel managed by nh3 link_rel
    "img":      {"src", "alt", "width", "height", "loading", "decoding"},
    "picture":  set(),
    "source":   {"src", "srcset", "media", "type", "sizes"},
    "oembed":   {"url"},
    "video":    {"src", "width", "height", "controls", "autoplay", "muted",
                 "loop", "poster", "preload"},
    "audio":    {"src", "controls", "autoplay", "muted", "loop", "preload"},
    "iframe":   {
        "src", "width", "height", "frameborder",
        "allowfullscreen", "allow", "title", "loading",
    },
    "td":       {"colspan", "rowspan", "align", "valign"},
    "th":       {"colspan", "rowspan", "align", "valign", "scope"},
    "table":    {"border", "cellpadding", "cellspacing", "width", "align"},
    "col":      {"span", "width"},
    "colgroup": {"span"},
    "ol":       {"type", "start", "reversed"},
    "li":       {"value"},
    "abbr":     {"title"},
    "details":  {"open"},
}

# ── CSS properties allowed inside style="" ────────────────────────────
# Covers everything CKEditor 4/5 legitimately writes; blocks expression(),
# url(), behavior: and other CSS injection vectors by omission.
_STYLE_PROPS = {
    # Text
    "color", "background-color",
    "font-size", "font-family", "font-weight", "font-style", "font-variant",
    "text-align", "text-decoration", "text-transform",
    "line-height", "letter-spacing", "word-spacing",
    "vertical-align", "white-space",
    # Box
    "width", "height", "max-width", "max-height", "min-width", "min-height",
    "margin", "margin-top", "margin-bottom", "margin-left", "margin-right",
    "padding", "padding-top", "padding-bottom", "padding-left", "padding-right",
    "border", "border-top", "border-bottom", "border-left", "border-right",
    "border-radius", "border-style", "border-width", "border-color",
    # Layout
    "float", "clear", "display", "overflow",
    # Misc
    "list-style-type", "table-layout", "border-collapse", "border-spacing",
    "caption-side", "empty-cells",
}

# Build a single reusable Cleaner instance (construction is expensive).
_cleaner = nh3.Cleaner(
    tags=_TAGS,
    attributes=_ATTRIBUTES,
    url_schemes={"http", "https", "mailto", "tel", "data"},
    # Appends rel="noopener noreferrer" to every <a> automatically.
    link_rel="noopener noreferrer",
    strip_comments=True,
    # Allow data-* on every element (CKEditor 5 widget metadata).
    generic_attribute_prefixes={"data-"},
    filter_style_properties=_STYLE_PROPS,
)


def sanitize_html(raw: str | None) -> str:
    """
    Sanitize CKEditor HTML.

    Strips all script tags, event handlers, javascript: URLs, and unknown
    tags while preserving the rich formatting CKEditor produces.
    Returns an empty string when *raw* is None or empty.
    """
    if not raw:
        return raw or ""
    return _cleaner.clean(raw)
