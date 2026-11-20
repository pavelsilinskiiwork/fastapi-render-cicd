from fastapi.testclient import TestClient

from main import app, commit_sha

client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_version_reports_the_commit_from_the_environment(monkeypatch):
    monkeypatch.delenv("RENDER_GIT_COMMIT", raising=False)
    monkeypatch.setenv("GIT_SHA", "abc123")
    assert client.get("/version").json()["commit"] == "abc123"


def test_render_commit_wins_over_git_sha(monkeypatch):
    monkeypatch.setenv("RENDER_GIT_COMMIT", "from-render")
    monkeypatch.setenv("GIT_SHA", "from-ci")
    assert commit_sha() == "from-render"


def test_version_defaults_to_dev(monkeypatch):
    monkeypatch.delenv("RENDER_GIT_COMMIT", raising=False)
    monkeypatch.delenv("GIT_SHA", raising=False)
    assert commit_sha() == "dev"


def test_wordcount_counts_words_case_insensitively_and_unicode():
    r = client.post("/wordcount", json={"text": "Hello, hello WORLD! Привет мир"})
    assert r.status_code == 200
    assert r.json() == {"words": 5, "unique_words": 4, "characters": 30}


def test_wordcount_rejects_empty_and_oversized_text():
    assert client.post("/wordcount", json={"text": ""}).status_code == 422
    assert client.post("/wordcount", json={"text": "x" * 10_001}).status_code == 422
    assert client.post("/wordcount", json={}).status_code == 422
