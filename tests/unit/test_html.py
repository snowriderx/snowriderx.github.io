"""Unit tests for sanitize_html — CKEditor output sanitizer."""
import pytest
from admin.utils.html import sanitize_html

pytestmark = pytest.mark.unit


def test_none_returns_empty():
    assert sanitize_html(None) == ""

def test_empty_string():
    assert sanitize_html("") == ""

def test_plain_text_preserved():
    assert sanitize_html("hello world") == "hello world"

def test_allowed_tags_preserved():
    result = sanitize_html("<p>Hello <strong>world</strong></p>")
    assert "<p>" in result
    assert "<strong>" in result

def test_script_tag_stripped():
    result = sanitize_html("<p>ok</p><script>alert(1)</script>")
    assert "<script>" not in result
    assert "alert" not in result

def test_event_handler_stripped():
    result = sanitize_html('<p onclick="alert(1)">click</p>')
    assert "onclick" not in result
    assert "<p>" in result

def test_javascript_href_stripped():
    result = sanitize_html('<a href="javascript:alert(1)">link</a>')
    assert "javascript:" not in result

def test_iframe_allowed():
    result = sanitize_html(
        '<iframe src="https://www.youtube.com/embed/abc" width="560"></iframe>'
    )
    assert "<iframe" in result
    assert "youtube.com" in result

def test_img_allowed():
    result = sanitize_html('<img src="/images/test.jpg" alt="test">')
    assert "<img" in result
    assert 'alt="test"' in result

def test_table_structure_preserved():
    html = "<table><tr><td>cell</td></tr></table>"
    result = sanitize_html(html)
    assert "<table>" in result
    assert "<td>" in result

def test_style_attribute_kept():
    result = sanitize_html('<p style="color: red;">text</p>')
    assert "color" in result

def test_data_attribute_kept():
    result = sanitize_html('<div data-id="123">content</div>')
    assert 'data-id="123"' in result

def test_unknown_tag_stripped():
    result = sanitize_html("<custom-tag>content</custom-tag>")
    assert "<custom-tag>" not in result
    assert "content" in result
