from __future__ import annotations
import json
from tj import llm


def test_no_key_returns_none(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(llm, "gemini_key", lambda paid=False: None)
    assert llm.has_llm() is False
    assert llm.complete("sys", "user") is None


def test_gemini_key_routing(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "free")
    monkeypatch.setenv("GEMINI_COST_API_KEY", "paid")
    assert llm.gemini_key() == "free"
    assert llm.gemini_key(paid=True) == "paid"


def test_complete_parses_text(monkeypatch):
    monkeypatch.setattr(llm, "gemini_key", lambda paid=False: "k")
    captured = {}

    class _Resp:
        status_code = 200
        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": "разбор ок"}]}}],
                    "usageMetadata": {"promptTokenCount": 12, "candidatesTokenCount": 30}}
        def raise_for_status(self): pass

    def _post(url, json=None, timeout=None):
        captured["url"] = url; captured["body"] = json
        return _Resp()

    monkeypatch.setattr(llm.httpx, "post", _post)
    out = llm.complete("СИСТЕМА", "ДАННЫЕ", max_output_tokens=500)
    assert out == "разбор ок"
    assert "generateContent" in captured["url"]
    parts = captured["body"]["contents"][0]["parts"][0]["text"]
    assert "СИСТЕМА" in parts and "ДАННЫЕ" in parts
    assert captured["body"]["generationConfig"]["maxOutputTokens"] == 500


def test_complete_http_error_returns_none(monkeypatch):
    monkeypatch.setattr(llm, "gemini_key", lambda paid=False: "k")

    def _boom(*a, **k):
        raise RuntimeError("net")
    monkeypatch.setattr(llm.httpx, "post", _boom)
    assert llm.complete("s", "u") is None


def test_vision_parses_text(monkeypatch):
    monkeypatch.setattr(llm, "gemini_key", lambda paid=False: "k")
    captured = {}

    class _Resp:
        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": "распознано"}]}}],
                    "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 9}}
        def raise_for_status(self): pass

    def _post(url, json=None, timeout=None):
        captured["body"] = json
        return _Resp()

    monkeypatch.setattr(llm.httpx, "post", _post)
    out = llm.vision(b"\xff\xd8imgbytes", "ПРОМПТ")
    assert out == "распознано"
    parts = captured["body"]["contents"][0]["parts"]
    assert parts[0]["inline_data"]["mime_type"] == "image/jpeg"
    assert parts[0]["inline_data"]["data"]
    assert parts[1]["text"] == "ПРОМПТ"
