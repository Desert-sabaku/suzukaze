import asyncio

from unity_bridge.core import UnityBridge, iter_lines


def test_iter_lines_keeps_partial_message():
    messages, remainder = iter_lines(b'{"action":"fan"}\n{"action":"water"')

    assert messages == [b'{"action":"fan"}']
    assert remainder == b'{"action":"water"'


def test_iter_lines_handles_multiple_messages_and_empty_lines():
    messages, remainder = iter_lines(b"one\n\ntwo\n")

    assert messages == [b"one", b"", b"two"]
    assert remainder == b""


def test_echo_mode_reports_serial_disabled_only(capsys):
    async def scenario() -> str:
        bridge = UnityBridge("127.0.0.1", 0, serial_port=None)
        task = asyncio.create_task(bridge._run())
        out = ""
        async with asyncio.timeout(1):
            while "Serial disabled" not in out:
                await asyncio.sleep(0.01)
                out += capsys.readouterr().out
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        return out + capsys.readouterr().out

    assert "Serial connected" not in asyncio.run(scenario())
