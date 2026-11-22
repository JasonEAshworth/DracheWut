"""Command line: `drache-wut` starts the game, `drache-wut server` hosts a game."""

import argparse

from . import TITLE, __version__


def main(argv=None):
    parser = argparse.ArgumentParser(prog="drache-wut", description=f"{TITLE} {__version__}")
    sub = parser.add_subparsers(dest="command")
    server = sub.add_parser("server", help="host a multiplayer game")
    server.add_argument("--port", type=int, default=50000, help="UDP port (default 50000)")
    server.add_argument("--max-players", type=int, default=5)
    server.add_argument("--accounts", default="accounts.dat", help="account file (default ./accounts.dat)")
    server.add_argument("--no-window", action="store_true", help="run without the status window")
    args = parser.parse_args(argv)

    if args.command == "server":
        from .server import Server

        Server(args.max_players, args.port, args.accounts).run(window=not args.no_window)
    else:
        from .client import run

        run()


if __name__ == "__main__":
    main()
