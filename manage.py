#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import asyncio
import os
import sys
import threading


def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if sys.platform == "win32":
    import chess.engine as _chess_engine

    # Twisted requires SelectorEventLoop and explicitly rejects ProactorEventLoop,
    # but chess.engine.popen_uci needs subprocess support only available in
    # ProactorEventLoop on Windows. Fix: run a ProactorEventLoop in a background
    # thread and proxy all engine calls through it.

    _proactor_loop = asyncio.ProactorEventLoop()
    _proactor_thread = threading.Thread(target=_proactor_loop.run_forever, daemon=True)
    _proactor_thread.start()

    def _run_in_proactor(coro):
        future = asyncio.run_coroutine_threadsafe(coro, _proactor_loop)
        return future.result()

    async def _bridge(coro):
        return await asyncio.get_running_loop().run_in_executor(
            None, _run_in_proactor, coro
        )

    _orig_popen_uci = _chess_engine.popen_uci

    class _EngineProxy:
        def __init__(self, engine):
            self._engine = engine

        async def configure(self, options):
            return await _bridge(self._engine.configure(options))

        async def play(self, board, limit, **kwargs):
            return await _bridge(self._engine.play(board, limit, **kwargs))

        async def quit(self):
            return await _bridge(self._engine.quit())

    async def _patched_popen_uci(command, **kwargs):
        transport, engine = await _bridge(_orig_popen_uci(command, **kwargs))
        return transport, _EngineProxy(engine)

    _chess_engine.popen_uci = _patched_popen_uci


if __name__ == '__main__':
    main()
