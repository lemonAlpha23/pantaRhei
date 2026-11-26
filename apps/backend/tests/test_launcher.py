import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from urllib.request import ProxyHandler, Request, build_opener


def test_ready_port_and_exit_on_parent_pipe_close(tmp_path):
    with subprocess.Popen(
        [sys.executable, "-m", "app", "--port", "0", "--watch-stdin"],
        env={**os.environ, "PANTARHEI_DATA_DIR": str(tmp_path), "PANTARHEI_TOKEN": "test-token"},
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    ) as child, ThreadPoolExecutor(1) as reader:
        try:
            ready = json.loads(reader.submit(child.stdout.readline).result(timeout=20))
            req = Request(f"http://127.0.0.1:{ready['port']}/api/health", headers={"Authorization": "Bearer test-token"})
            with build_opener(ProxyHandler({})).open(req, timeout=3) as response:
                assert json.load(response) == {"status": "ok"}
            child.stdin.close()
            assert child.wait(timeout=8) == 0
        finally:
            if child.poll() is None:
                child.kill()
