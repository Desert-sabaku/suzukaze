from src.core import iter_lines


def test_iter_lines_keeps_partial_message():
    messages, remainder = iter_lines(b'{"action":"fan"}\n{"action":"water"')

    assert messages == [b'{"action":"fan"}']
    assert remainder == b'{"action":"water"'


def test_iter_lines_handles_multiple_messages_and_empty_lines():
    messages, remainder = iter_lines(b"one\n\ntwo\n")

    assert messages == [b"one", b"", b"two"]
    assert remainder == b""
