"""Tests for streamed extraction calls, explicit context and degraded reasons.

Aldeia-IT/aldeia-box#1427 AC3 (``stream: true``, NDJSON assembly, the read
timeout as a stall detector), AC4 (``num_ctx``/``num_predict``, source
truncation) and AC5 (``extraction_degraded: <reason>``).
"""

import json

import httpx
import pytest
import respx

OLLAMA_BASE = "http://127.0.0.1:11434"
GENERATE = f"{OLLAMA_BASE}/api/generate"
CHAT = f"{OLLAMA_BASE}/api/chat"

VALID = {
    "entities": [{"name": "Mestre Bimba", "description": "Founder of Capoeira Regional."}],
    "concepts": [{"name": "Capoeira Regional", "description": "A capoeira style."}],
}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.delenv("WIKI_EXTRACT_ENDPOINT", raising=False)
    monkeypatch.delenv("WIKI_EXTRACT_OUTPUT_TOKENS", raising=False)
    monkeypatch.delenv("WIKI_EXTRACT_MAX_INPUT_TOKENS", raising=False)


def _ndjson(*chunks: dict) -> bytes:
    return b"".join(json.dumps(c).encode() + b"\n" for c in chunks)


def _generate_stream(text: str, *, parts: int = 4, done_reason: str = "stop") -> bytes:
    size = max(1, len(text) // parts)
    pieces = [text[i : i + size] for i in range(0, len(text), size)]
    chunks = [{"response": p, "done": False} for p in pieces]
    chunks.append({"response": "", "done": True, "done_reason": done_reason})
    return _ndjson(*chunks)


def _chat_stream(text: str, *, done_reason: str = "stop") -> bytes:
    half = len(text) // 2
    return _ndjson(
        {"message": {"role": "assistant", "content": text[:half]}, "done": False},
        {"message": {"role": "assistant", "content": text[half:]}, "done": False},
        {"message": {"role": "assistant", "content": ""}, "done": True, "done_reason": done_reason},
    )


class _StallingStream(httpx.SyncByteStream):
    """Yields one chunk, then stalls past the read timeout."""

    def __iter__(self):
        yield b'{"response": "{\\"entities\\": [", "done": false}\n'
        raise httpx.ReadTimeout("no chunk within the read timeout")


class TestStreamedCalls:
    """AC3: streamed NDJSON is assembled until ``done: true``."""

    @respx.mock
    def test_multi_chunk_generate_is_assembled_and_parsed(self):
        captured = []

        def on_generate(request):
            captured.append(json.loads(request.content))
            return httpx.Response(200, content=_generate_stream(json.dumps(VALID)))

        respx.post(GENERATE).mock(side_effect=on_generate)
        chat = respx.post(CHAT).mock(return_value=httpx.Response(500))

        from anytype_llm_wiki.wiki.extraction import extract

        result = extract(markdown="# Mestre Bimba\n\nBody.", space_id="s")
        assert "error" not in result, result
        assert [e["name"] for e in result["entities"]] == ["Mestre Bimba"]
        assert captured[0]["stream"] is True
        assert not chat.called

    @respx.mock
    def test_chat_fallback_assembles_message_content(self):
        respx.post(GENERATE).mock(
            return_value=httpx.Response(200, content=_generate_stream("not json {{"))
        )
        chat_bodies = []

        def on_chat(request):
            chat_bodies.append(json.loads(request.content))
            return httpx.Response(200, content=_chat_stream(json.dumps(VALID)))

        respx.post(CHAT).mock(side_effect=on_chat)

        from anytype_llm_wiki.wiki.extraction import extract

        result = extract(markdown="# Mestre Bimba\n\nBody.", space_id="s")
        assert "error" not in result, result
        assert result["concepts"][0]["name"] == "Capoeira Regional"
        assert chat_bodies[0]["stream"] is True

    @respx.mock
    def test_chunk_gap_timeout_gives_reason_timeout(self):
        respx.post(GENERATE).mock(return_value=httpx.Response(200, stream=_StallingStream()))
        chat = respx.post(CHAT).mock(return_value=httpx.Response(500))

        from anytype_llm_wiki.wiki.extraction import extract

        result = extract(markdown="# T\n\nBody.", space_id="s")
        assert result["error"] == "extraction_degraded: timeout"
        assert result["entities"] == [] and result["concepts"] == []
        assert not chat.called, "a timeout is not retried on /api/chat (fallback order unchanged)"

    def test_read_timeout_is_the_configured_stall_window(self, monkeypatch):
        """WIKI_EXTRACT_TIMEOUT is the httpx read timeout (max silence between chunks)."""
        from anytype_llm_wiki.wiki import extraction

        monkeypatch.setenv("WIKI_EXTRACT_TIMEOUT", "42")
        seen = {}
        real_client = httpx.Client

        def spy_client(*a, **kw):
            seen["timeout"] = kw.get("timeout")
            return real_client(*a, **kw)

        monkeypatch.setattr(extraction.httpx, "Client", spy_client)
        with respx.mock:
            respx.post(GENERATE).mock(
                return_value=httpx.Response(200, content=_generate_stream(json.dumps(VALID)))
            )
            extraction.extract(markdown="# T\n\nBody.", space_id="s")
        assert seen["timeout"].read == 42.0

    @respx.mock
    def test_mid_stream_error_line_is_a_failed_call(self):
        broken = _ndjson(
            {"response": '{"entities": [', "done": False},
            {"error": "llama runner process has terminated"},
        )
        respx.post(GENERATE).mock(return_value=httpx.Response(200, content=broken))
        respx.post(CHAT).mock(return_value=httpx.Response(200, content=broken))

        from anytype_llm_wiki.wiki.extraction import extract

        result = extract(markdown="# T\n\nBody.", space_id="s")
        assert result["error"] == (
            "extraction_degraded: stream_error: llama runner process has terminated"
        )

    @respx.mock
    def test_mid_stream_error_falls_back_to_chat(self):
        broken = _ndjson({"error": "boom"})
        respx.post(GENERATE).mock(return_value=httpx.Response(200, content=broken))
        respx.post(CHAT).mock(
            return_value=httpx.Response(200, content=_chat_stream(json.dumps(VALID)))
        )

        from anytype_llm_wiki.wiki.extraction import extract

        result = extract(markdown="# T\n\nBody.", space_id="s")
        assert "error" not in result, result
        assert result["entities"][0]["name"] == "Mestre Bimba"

    @respx.mock
    def test_stream_without_done_is_a_failed_call(self):
        cut = _ndjson({"response": json.dumps(VALID), "done": False})
        respx.post(GENERATE).mock(return_value=httpx.Response(200, content=cut))
        respx.post(CHAT).mock(return_value=httpx.Response(200, content=cut))

        from anytype_llm_wiki.wiki.extraction import extract

        result = extract(markdown="# T\n\nBody.", space_id="s")
        assert result["error"].startswith("extraction_degraded: stream_error: ")
        assert result["entities"] == []

    @respx.mock
    def test_404_model_not_pulled_unchanged(self):
        respx.post(GENERATE).mock(
            return_value=httpx.Response(
                404, json={"error": "model 'granite4.1:8b' not found, try pulling it first"}
            )
        )
        chat = respx.post(CHAT).mock(return_value=httpx.Response(500))

        from anytype_llm_wiki.wiki.extraction import extract

        result = extract(markdown="# T\n\nBody.", space_id="s")
        assert result["error"].startswith("[CONFIG ERROR] ollama_model_not_pulled")
        assert not chat.called

    @respx.mock
    def test_call_ollama_prompt_keeps_its_two_tuple_contract(self):
        """ingest's alias/contradiction prompts unpack ``(parsed, resp)``."""
        respx.post(GENERATE).mock(
            return_value=httpx.Response(200, content=_generate_stream('{"match": null}'))
        )
        from anytype_llm_wiki.wiki.extraction import _call_ollama_prompt

        parsed, resp = _call_ollama_prompt(OLLAMA_BASE, "prompt")
        assert parsed == {"match": None}
        assert resp.status_code == 200


class TestExplicitContext:
    """AC4: every call carries num_ctx and num_predict; long sources are cut."""

    @respx.mock
    def test_options_carry_num_ctx_and_num_predict(self):
        bodies = []

        def capture(request):
            bodies.append(json.loads(request.content))
            return httpx.Response(200, content=_generate_stream("not json"))

        respx.post(GENERATE).mock(side_effect=capture)
        respx.post(CHAT).mock(side_effect=capture)

        from anytype_llm_wiki.wiki.extraction import _DETERMINISTIC_OPTS, extract

        extract(markdown="# T\n\nBody.", space_id="s")
        assert len(bodies) == 4  # generate + chat, twice (one repair round)
        for body in bodies:
            opts = body["options"]
            assert opts["num_ctx"] == 8192 + 4096
            assert opts["num_predict"] == 4096
            for key, value in _DETERMINISTIC_OPTS.items():
                assert opts[key] == value

    @respx.mock
    def test_env_overrides(self, monkeypatch):
        monkeypatch.setenv("WIKI_EXTRACT_OUTPUT_TOKENS", "2048")
        monkeypatch.setenv("WIKI_EXTRACT_MAX_INPUT_TOKENS", "6000")
        bodies = []

        def capture(request):
            bodies.append(json.loads(request.content))
            return httpx.Response(200, content=_generate_stream(json.dumps(VALID)))

        respx.post(GENERATE).mock(side_effect=capture)

        from anytype_llm_wiki.wiki.extraction import extract

        extract(markdown="# T\n\nBody.", space_id="s")
        assert bodies[0]["options"]["num_ctx"] == 8048
        assert bodies[0]["options"]["num_predict"] == 2048

    def test_output_tokens_config(self, monkeypatch):
        from anytype_llm_wiki.wiki import config

        assert config.extract_output_tokens() == 4096
        monkeypatch.setenv("WIKI_EXTRACT_OUTPUT_TOKENS", "0")
        assert config.extract_output_tokens() == 4096
        monkeypatch.setenv("WIKI_EXTRACT_OUTPUT_TOKENS", "junk")
        assert config.extract_output_tokens() == 4096
        monkeypatch.setenv("WIKI_EXTRACT_OUTPUT_TOKENS", "1024")
        assert config.extract_output_tokens() == 1024

    @respx.mock
    def test_source_over_the_cap_is_cut_at_a_paragraph_and_reported(self, monkeypatch):
        monkeypatch.setenv("WIKI_EXTRACT_MAX_INPUT_TOKENS", "1000")  # 3,000 chars
        prompts = []

        def capture(request):
            prompts.append(json.loads(request.content)["prompt"])
            return httpx.Response(200, content=_generate_stream(json.dumps(VALID)))

        respx.post(GENERATE).mock(side_effect=capture)

        from anytype_llm_wiki.wiki.extraction import _load_prompt, extract

        paragraphs = [f"Paragraph {i} " + ("x" * 180) for i in range(40)]
        source = "\n\n".join(paragraphs)
        result = extract(markdown=source, space_id="s")

        template_len = len(_load_prompt()) - len("{source}")
        assert len(prompts[0]) <= 1000 * 3, "the whole prompt fits the input cap"
        kept = result["truncated"]["kept_chars"]
        assert result["truncated"]["total_chars"] == len(source)
        assert 0 < kept < len(source)
        assert kept <= 1000 * 3 - template_len
        kept_text = source[:kept]
        assert kept_text.rstrip().endswith("x"), "cut at a paragraph boundary"
        assert source[kept:].lstrip().startswith("Paragraph "), "the next paragraph starts the cut"
        assert "Paragraph 39" not in prompts[0]

    @respx.mock
    def test_source_under_the_cap_is_untouched(self):
        prompts = []

        def capture(request):
            prompts.append(json.loads(request.content)["prompt"])
            return httpx.Response(200, content=_generate_stream(json.dumps(VALID)))

        respx.post(GENERATE).mock(side_effect=capture)

        from anytype_llm_wiki.wiki.extraction import extract

        source = "# T\n\n" + ("Body text. " * 50)
        result = extract(markdown=source, space_id="s")
        assert "truncated" not in result
        assert source in prompts[0]


class TestDegradedReasons:
    """AC5: ``error`` is ``extraction_degraded: <reason>``."""

    @respx.mock
    def test_malformed_json(self):
        respx.post(GENERATE).mock(return_value=httpx.Response(200, content=_generate_stream("{bad")))
        respx.post(CHAT).mock(return_value=httpx.Response(200, content=_chat_stream("{bad")))
        from anytype_llm_wiki.wiki.extraction import extract

        assert extract(markdown="# T", space_id="s")["error"] == "extraction_degraded: malformed_json"

    @respx.mock
    def test_output_truncated(self):
        cut = _generate_stream('{"entities": [{"name": "Mes', done_reason="length")
        respx.post(GENERATE).mock(return_value=httpx.Response(200, content=cut))
        respx.post(CHAT).mock(
            return_value=httpx.Response(
                200, content=_chat_stream('{"entities": [{"na', done_reason="length")
            )
        )
        from anytype_llm_wiki.wiki.extraction import extract

        assert extract(markdown="# T", space_id="s")["error"] == "extraction_degraded: output_truncated"

    @respx.mock
    def test_http_error_status(self):
        respx.post(GENERATE).mock(return_value=httpx.Response(500, text="internal"))
        respx.post(CHAT).mock(return_value=httpx.Response(503, text="busy"))
        from anytype_llm_wiki.wiki.extraction import extract

        assert extract(markdown="# T", space_id="s")["error"] == "extraction_degraded: http_error: 503"

    @respx.mock
    def test_http_error_exception_class(self):
        respx.post(GENERATE).mock(
            side_effect=httpx.ConnectError("connect failed to http://user:secret@host")
        )
        from anytype_llm_wiki.wiki.extraction import extract

        error = extract(markdown="# T", space_id="s")["error"]
        assert error == "extraction_degraded: http_error: ConnectError"
        assert "secret" not in error

    @respx.mock
    def test_connect_timeout_is_timeout(self):
        respx.post(GENERATE).mock(side_effect=httpx.ConnectTimeout("slow"))
        from anytype_llm_wiki.wiki.extraction import extract

        assert extract(markdown="# T", space_id="s")["error"] == "extraction_degraded: timeout"
