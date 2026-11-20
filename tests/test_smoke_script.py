"""The smoke-test script gates every deploy, so it gets real tests against a real local HTTP server."""

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import smoke_test  # noqa: E402


class FakeService:
    """Serves /version and /health; `commits` is the sequence of commits it reports, one per /version call."""

    def __init__(self, commits, health="ok"):
        self.commits = list(commits)
        self.health = health
        self.version_calls = 0
        service = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/version":
                    index = min(service.version_calls, len(service.commits) - 1)
                    service.version_calls += 1
                    self._send(200, {"commit": service.commits[index]})
                elif self.path == "/health":
                    self._send(200, {"status": service.health})
                else:
                    self._send(404, {})

            def _send(self, status, body):
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def service():
    created = []

    def make(*args, **kwargs):
        svc = FakeService(*args, **kwargs)
        created.append(svc)
        return svc

    yield make
    for svc in created:
        svc.close()


class FakeTime:
    """A clock that only moves when the script 'sleeps', so no test really waits."""

    def __init__(self):
        self.now = 0.0

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def run(url, sha, timeout=60, interval=5):
    t = FakeTime()
    ok = smoke_test.wait_for_commit(
        url, sha, timeout, interval, sleep=t.sleep, clock=t.clock, log=lambda m: None
    )
    return ok, t.now


def test_passes_immediately_when_the_new_commit_is_already_running(service):
    svc = service(["new"])
    assert run(svc.url, "new") == (True, 0.0)


def test_keeps_waiting_while_the_old_version_answers_then_passes(service):
    svc = service(["old", "old", "new"])
    ok, waited = run(svc.url, "new", interval=5)
    assert ok and waited == 10 and svc.version_calls == 3


def test_fails_when_the_old_version_never_goes_away(service):
    svc = service(["old"])
    ok, waited = run(svc.url, "new", timeout=20, interval=5)
    assert not ok and waited <= 20


def test_fails_when_the_new_commit_runs_but_health_is_not_ok(service):
    svc = service(["new"], health="degraded")
    ok, _ = run(svc.url, "new", timeout=20, interval=5)
    assert not ok


def test_unreachable_service_counts_as_not_ready_not_as_a_crash():
    ok, _ = run("http://127.0.0.1:9", "new", timeout=10, interval=5)  # nothing listens on port 9
    assert not ok


def test_main_exit_codes(service, capsys):
    good = service(["abc1234"])
    assert smoke_test.main([good.url, "--sha", "abc1234", "--timeout", "5", "--interval", "1"]) == 0
    stale = service(["old"])
    assert smoke_test.main([stale.url, "--sha", "abc1234", "--timeout", "2", "--interval", "1"]) == 1
    assert "did not report commit abc1234" in capsys.readouterr().out
