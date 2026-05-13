from services.mcp_import import _sanitize_mcp_prompt


def test_sanitize_none_returns_empty():
    assert _sanitize_mcp_prompt(None) == ""


def test_sanitize_empty_returns_empty():
    assert _sanitize_mcp_prompt("") == ""
    assert _sanitize_mcp_prompt("   ") == ""


def test_sanitize_normal_chinese_prompt_preserved():
    result = _sanitize_mcp_prompt("获取产品需求页面及其子页面的数据")
    assert "产品需求" in result
    assert "子页面" in result


def test_sanitize_html_tags_stripped():
    result = _sanitize_mcp_prompt("hello <script>alert(1)</script> world<img src=x onerror=alert(1)>")
    assert "<script>" not in result
    assert "alert(1)" in result  # text content inside tags is preserved
    assert "<img" not in result


def test_sanitize_long_text_truncated():
    long = "x" * 3000
    result = _sanitize_mcp_prompt(long)
    assert len(result) <= 2000
    assert result == "x" * 2000


def test_sanitize_null_byte_removed():
    result = _sanitize_mcp_prompt("hello\x00world")
    assert "\x00" not in result
    assert "hello" in result
    assert "world" in result


def test_sanitize_bidi_characters_removed():
    # Unicode bidi override characters U+202A–U+202E, U+2066–U+2069
    result = _sanitize_mcp_prompt("normal ‪‫‭ ‮ text")
    assert "‪" not in result
    assert "‫" not in result
    assert "normal" in result
    assert "text" in result


def test_sanitize_whitespace_collapsed():
    result = _sanitize_mcp_prompt("hello   \n\n\r\r\t\t  world")
    assert result == "hello world"


def test_sanitize_leading_trailing_whitespace_stripped():
    result = _sanitize_mcp_prompt("  hello world  ")
    assert result == "hello world"
