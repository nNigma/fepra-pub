import httpx
import pytest
from tj.adapters import whoop


def _client(handler, tokens):
    saved = []
    def load():
        return dict(tokens)
    def save(t):
        tokens.update(t)
        saved.append(dict(t))
    http = httpx.Client(transport=httpx.MockTransport(handler))
    c = whoop.WhoopClient(("cid", "sec"), load, save, http=http)
    return c, saved


def test_collection_paginates():
    pages = [
        {"records": [{"id": 1}], "next_token": "T2"},
        {"records": [{"id": 2}], "next_token": None},
    ]
    calls = []
    def handler(req):
        calls.append(dict(req.url.params))
        return httpx.Response(200, json=pages[len(calls) - 1])
    c, _ = _client(handler, {"access_token": "A", "refresh_token": "R"})
    recs = c.collection("/recovery", "2026-07-08T00:00:00Z", "2026-07-11T00:00:00Z")
    assert [r["id"] for r in recs] == [1, 2]
    assert "nextToken" not in calls[0] and calls[1]["nextToken"] == "T2"


def test_retry_on_401_refreshes_and_rotates():
    state = {"n": 0}
    def handler(req):
        if req.url.path.endswith("/token"):
            body = dict(p.split("=", 1) for p in req.content.decode().split("&"))
            assert body["grant_type"] == "refresh_token"
            assert body["refresh_token"] == "R1"
            return httpx.Response(200, json={"access_token": "A2", "refresh_token": "R2",
                                             "expires_in": 3600})
        state["n"] += 1
        if state["n"] == 1:
            return httpx.Response(401)
        assert req.headers["Authorization"] == "Bearer A2"
        return httpx.Response(200, json={"records": [], "next_token": None})
    tokens = {"access_token": "A1", "refresh_token": "R1"}
    c, saved = _client(handler, tokens)
    c.collection("/recovery", "s", "e")
    assert tokens["access_token"] == "A2" and tokens["refresh_token"] == "R2"
    assert saved


def test_second_401_raises():
    def handler(req):
        if req.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "A2", "refresh_token": "R2",
                                             "expires_in": 3600})
        return httpx.Response(401)
    c, _ = _client(handler, {"access_token": "A1", "refresh_token": "R1"})
    with pytest.raises(httpx.HTTPStatusError):
        c.collection("/recovery", "s", "e")
