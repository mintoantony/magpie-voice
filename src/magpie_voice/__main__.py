import sys


def _run() -> int:
    argv = sys.argv[1:]
    if argv[:1] == ["daemon"]:
        import argparse

        from . import config
        from .daemon import main

        p = argparse.ArgumentParser(prog="magpie-voice daemon")
        p.add_argument("--port", type=int, default=config.DAEMON_PORT)
        return main(p.parse_args(argv[1:]).port)
    from .cli import main

    return main(argv)


raise SystemExit(_run())
