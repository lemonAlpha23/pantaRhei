import argparse
import json
import os
import socket
import sys
from collections.abc import Callable
from threading import Thread

import uvicorn
from fastapi import FastAPI


class LocalServer(uvicorn.Server):
    async def startup(self, sockets=None):
        await super().startup(sockets=sockets)
        if self.started:
            port = sockets[0].getsockname()[1]
            print(json.dumps({"port": port}), flush=True)


def watch_stdin(server: LocalServer) -> None:
    while os.read(sys.stdin.fileno(), 1024):
        pass
    server.should_exit = True


def run(create_app: Callable[[], FastAPI]) -> None:
    parser = argparse.ArgumentParser(description="Start the local Panta Rhei service")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--watch-stdin", action="store_true", help="Stop when the parent closes stdin")
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("port must be between 0 and 65535")

    host = "127.0.0.1"
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind((host, args.port))
        config = uvicorn.Config(create_app(), host=host, port=args.port, access_log=False)
        server = LocalServer(config)
        if args.watch_stdin:
            Thread(target=watch_stdin, args=(server,), daemon=True).start()
        server.run(sockets=[listener])
