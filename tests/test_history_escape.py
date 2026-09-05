from utils.helpers import escape_md


def test_history_escape():
    text = "client_test-v2(test)[1]!"
    escaped = escape_md(text)

    assert "_" not in escaped.replace("\\_", "")
    assert "\\_" in escaped
    assert "\\-" not in escaped
    assert "\\[" in escaped
    assert "\\]" in escaped
