"""wiki/extraction.py — LLM extraction pipeline (AC#7, AC#11, AC#12, AC-S1/S2).

extract() is a best-effort ENRICHMENT layer: it POSTs the source to a local
Ollama instance (or WIKI_EXTRACT_ENDPOINT) and parses entities/concepts. On
malformed JSON it makes ONE repair attempt, then degrades gracefully to an
empty result so the ingest pipeline can continue from heading-derived
candidates. A 404 / "not found" / "pull it first" Ollama response short-circuits
with a [CONFIG ERROR] ollama_model_not_pulled marker.

Name/value sanitization and the remote-endpoint consent banner live here too.
"""

import hashlib
import json
import logging
import os
import re
from pathlib import Path

import httpx

from . import config
from .util import scrub_credentials, strip_control_chars

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "extraction.md"
_CONSOLIDATE_PROMPT_PATH = Path(__file__).parent / "prompts" / "consolidate.md"

# Prompt-like name prefixes that must never be written as object names (AC#12).
_NAME_POLICY_PREFIXES = ("system:", "assistant:", "ignore", "<|", "[inst]")
_NAME_MAX_LEN = 200

_DEFAULT_ACK_DIR = os.path.expanduser("~/.local/share/anytype-llm-wiki")
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]", "0.0.0.0"}  # nosec B104 — membership test, not a bind address

# Deterministic decoding for extraction. Without this Ollama defaults to
# temperature 0.8, so re-extracting the same source yields different entity
# titles, which breaks entity resolution (exact-title match) and produces
# duplicate objects on re-ingest. Greedy decoding (temperature 0 + fixed seed)
# makes extraction reproducible so re-ingest is idempotent.
_DETERMINISTIC_OPTS = {"temperature": 0, "seed": 0, "top_p": 1}

# Conservative chars-per-token estimate for sizing the extraction source (AC4).
# Measured ~3.3 on a real capoeira page; ``len // 4`` undercounts.
_CHARS_PER_TOKEN = 3


def _load_prompt() -> str:
    try:
        return _PROMPT_PATH.read_text(encoding="utf-8")
    except OSError:
        return "Extract entities and concepts from:\n<source>\n{source}\n</source>"


def _load_consolidate_prompt() -> str:
    try:
        return _CONSOLIDATE_PROMPT_PATH.read_text(encoding="utf-8")
    except OSError:
        return (
            "You are a wiki knowledge consolidator. Reconcile new_knowledge into "
            "existing_facts for a wiki {kind} stored in {property_name}.\n"
            "<existing_facts>\n{existing_facts}\n</existing_facts>\n"
            "<new_knowledge>\n{new_knowledge}\n</new_knowledge>"
        )


def _ollama_url() -> str:
    from .. import config as root_config

    return getattr(root_config, "OLLAMA_URL", "http://127.0.0.1:11434")


def _parse_json_text(text: str | None) -> dict | None:
    """Parse the model's text as a JSON object (tolerating a fenced block)."""
    if not text:
        return None
    text = text.strip()
    # Tolerate fenced ```json blocks.
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    try:
        parsed = json.loads(text)
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _chunk_text(chunk: dict) -> str:
    """The text one generate/chat payload carries (``response`` or ``message.content``)."""
    if "response" in chunk:
        return chunk.get("response") or ""
    message = chunk.get("message")
    if isinstance(message, dict):
        return message.get("content") or ""
    return ""


def _parse_json_response(payload: dict) -> dict | None:
    """Pull the model's text out of an Ollama generate/chat response and parse it."""
    if not isinstance(payload, dict):
        return None
    return _parse_json_text(_chunk_text(payload))


def _is_model_not_pulled(resp: httpx.Response) -> bool:
    if resp.status_code != 404:
        return False
    body = resp.text.lower()
    return "not found" in body or "pull it first" in body or "model" in body


def _model_options() -> dict:
    """Decoding options for every extraction-family call (AC4).

    ``num_ctx`` is the input cap plus the output budget and ``num_predict`` the
    output budget. Both are fixed per config, not per prompt, so Ollama never
    reloads the model runner between calls.
    """
    output_tokens = config.extract_output_tokens()
    return {
        **_DETERMINISTIC_OPTS,
        "num_ctx": config.extract_max_input_tokens() + output_tokens,
        "num_predict": output_tokens,
    }


def _read_stream(resp: httpx.Response) -> tuple[str | None, str | None, str | None]:
    """Assemble a streamed Ollama NDJSON body until ``done: true``.

    Returns ``(text, done_reason, failure)``. ``failure`` is set (and ``text`` is
    None) when the stream carries an ``{"error": ...}`` line, a line that is not
    a JSON object, or ends without ``done: true``. A read timeout between chunks
    propagates as ``httpx.TimeoutException``.
    """
    parts: list[str] = []
    for line in resp.iter_lines():
        line = line.strip()
        if not line:
            continue
        try:
            chunk = json.loads(line)
        except ValueError:
            return None, None, "stream_error: invalid chunk"
        if not isinstance(chunk, dict):
            return None, None, "stream_error: invalid chunk"
        if chunk.get("error"):
            message = scrub_credentials(strip_control_chars(str(chunk["error"])))
            return None, None, f"stream_error: {message[:200]}"
        parts.append(_chunk_text(chunk))
        if chunk.get("done"):
            return "".join(parts), chunk.get("done_reason"), None
    return None, None, "stream_error: stream ended before done"


def _call_ollama_prompt_detailed(
    base: str, prompt: str
) -> tuple[dict | None, httpx.Response | None, str | None]:
    """Stream a pre-built ``prompt`` to {base}/api/generate, then /api/chat.

    Both calls send ``"stream": true``; the httpx read timeout
    (``WIKI_EXTRACT_TIMEOUT``) therefore caps the silence between chunks, not the
    whole generation. A 404 model-not-pulled answer is detected from the status
    before any stream is parsed and returned at once. Returns
    ``(parsed_or_None, last_resp, failure_reason)``; ``failure_reason`` is the
    last call's reason (``http_error: <status>``, ``stream_error: <msg>``,
    ``output_truncated`` or ``malformed_json``) when nothing parsed. Transport
    errors (timeouts included) propagate to the caller.
    """
    model = config.extract_model()
    think = config.extract_think()
    options = _model_options()
    timeout = httpx.Timeout(connect=5, read=config.extract_timeout(), write=10, pool=5)
    last_resp: httpx.Response | None = None
    reason: str | None = None
    requests = (
        ("/api/generate", {"prompt": prompt}),
        ("/api/chat", {"messages": [{"role": "user", "content": prompt}]}),
    )

    with httpx.Client(timeout=timeout) as client:
        for path, body in requests:
            payload = {
                "model": model,
                **body,
                "stream": True,
                "format": "json",
                "think": think,
                "options": options,
            }
            with client.stream("POST", f"{base}{path}", json=payload) as resp:
                last_resp = resp
                if resp.status_code != 200:
                    resp.read()
                    if _is_model_not_pulled(resp):
                        return None, resp, None
                    reason = f"http_error: {resp.status_code}"
                    continue
                text, done_reason, failure = _read_stream(resp)
            if failure is not None:
                reason = failure
                continue
            parsed = _parse_json_text(text)
            if parsed is not None:
                return parsed, resp, None
            reason = "output_truncated" if done_reason == "length" else "malformed_json"

    return None, last_resp, reason


def _call_ollama_prompt(
    base: str, prompt: str
) -> tuple[dict | None, httpx.Response | None]:
    """POST a pre-built ``prompt`` to {base}/api/generate then /api/chat.

    Same streamed generate→chat→model-not-pulled wire behaviour as
    ``_call_ollama_prompt_detailed`` without the failure reason. Returns
    ``(parsed_or_None, last_resp)``.
    """
    parsed, resp, _reason = _call_ollama_prompt_detailed(base, prompt)
    return parsed, resp


def _fit_source(markdown: str, template: str) -> tuple[str, dict | None]:
    """Cut ``markdown`` so the whole prompt fits ``extract_max_input_tokens()`` (AC4).

    Estimates 3 chars per token (conservative for prose; ``len // 4``
    undercounts) and cuts at the last paragraph break, else line break, inside
    the budget. Returns ``(source, truncated)`` where ``truncated`` is
    ``{"kept_chars", "total_chars"}`` or None when nothing was cut.
    """
    budget = config.extract_max_input_tokens() * _CHARS_PER_TOKEN - (
        len(template) - len("{source}")
    )
    budget = max(budget, 0)
    total = len(markdown)
    if total <= budget:
        return markdown, None
    cut = markdown.rfind("\n\n", 0, budget + 1)
    if cut <= budget // 2:
        cut = markdown.rfind("\n", 0, budget + 1)
    if cut <= budget // 2:
        cut = budget
    kept = markdown[:cut]
    return kept, {"kept_chars": len(kept), "total_chars": total}


def _call_ollama(
    base: str, markdown: str
) -> tuple[dict | None, httpx.Response | None, str | None]:
    """Substitute ``{source}`` into the extraction prompt and stream it.

    Returns ``(parsed_or_None, last_resp, failure_reason)``.
    """
    prompt = _load_prompt().replace("{source}", markdown)
    return _call_ollama_prompt_detailed(base, prompt)


def _transport_reason(exc: httpx.HTTPError) -> str:
    """Map a transport error to a degraded reason without its message (AC5)."""
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    return f"http_error: {type(exc).__name__}"


def extract(markdown: str, space_id: str, **kw) -> dict:
    """Run LLM extraction. Best-effort; degrades to empty entities/concepts.

    Returns a dict with at least ``entities`` and ``concepts`` keys. On a
    not-pulled Ollama model returns a dict whose str() contains
    ``[CONFIG ERROR] ollama_model_not_pulled``. A degraded run sets ``error`` to
    ``extraction_degraded: <reason>``, reason one of ``timeout``,
    ``http_error: <ExceptionClass or status>``, ``malformed_json``,
    ``output_truncated`` or ``stream_error: <msg>``. When the source had to be cut
    to fit the input cap, ``truncated`` is ``{"kept_chars", "total_chars"}``.
    """
    base = os.environ.get("WIKI_EXTRACT_ENDPOINT") or _ollama_url()
    base = base.rstrip("/")
    source, truncated = _fit_source(markdown, _load_prompt())

    def _done(result: dict) -> dict:
        if truncated is not None:
            result["truncated"] = truncated
        return result

    def _degraded(reason: str) -> dict:
        return _done(
            {"entities": [], "concepts": [], "error": f"extraction_degraded: {reason}"}
        )

    reason = "malformed_json"
    # One repair round: a second identical call when the first parses nothing.
    for attempt in range(2):
        try:
            parsed, resp, failure = _call_ollama(base, source)
        except httpx.HTTPError as exc:
            return _degraded(_transport_reason(exc))

        if resp is not None and _is_model_not_pulled(resp):
            error = "[CONFIG ERROR] ollama_model_not_pulled"
            if attempt == 0:
                error += (
                    f": the extraction model '{config.extract_model()}' is not "
                    "available — pull it first"
                )
            return {"entities": [], "concepts": [], "error": error}

        if parsed is not None:
            return _done(filter_extraction_output(parsed))
        reason = failure or "malformed_json"

    # Still nothing usable after the repair round → graceful empty result.
    return _degraded(reason)


def _degraded_consolidation(existing_text: str, reason: str) -> dict:
    return {
        "consolidated_text": existing_text,
        "changed": False,
        "fact_actions": [],
        "conflicts": [],
        "error": f"consolidation_degraded: {reason}",
    }


def consolidate(
    existing_text: str,
    new_facts: str,
    kind: str,
    space_id: str,
    **kw,
) -> dict:
    """Run LLM consolidation for one resolved subject (#289 D1/D2).

    Loads ``consolidate.md``, substitutes the kind/property/text placeholders,
    POSTs via ``_call_ollama_prompt`` with ``_DETERMINISTIC_OPTS``, and parses the
    ``{consolidated_text, changed, fact_actions, conflicts}`` JSON. Makes ONE
    repair retry on malformed JSON. On a not-pulled model OR malformed-after-retry
    returns a degraded result whose ``error`` contains ``consolidation_degraded``
    (and ``ollama_model_not_pulled`` on the not-pulled path).
    """
    base = os.environ.get("WIKI_EXTRACT_ENDPOINT") or _ollama_url()
    base = base.rstrip("/")

    property_name = "wiki_definition" if kind == "concept" else "wiki_facts"
    prompt = (
        _load_consolidate_prompt()
        .replace("{kind}", str(kind))
        .replace("{property_name}", property_name)
        .replace("{existing_facts}", existing_text or "")
        .replace("{new_knowledge}", new_facts or "")
    )

    try:
        parsed, resp = _call_ollama_prompt(base, prompt)
    except httpx.HTTPError as exc:
        return _degraded_consolidation(existing_text, str(exc))

    if resp is not None and _is_model_not_pulled(resp):
        return _degraded_consolidation(
            existing_text,
            f"ollama_model_not_pulled: the consolidation model "
            f"'{config.extract_model()}' is not available — pull it first",
        )

    if not _is_consolidation_shape(parsed):
        # Malformed JSON (or a parseable-but-wrong-shape payload, e.g. an empty
        # object lacking consolidated_text) → one repair attempt.
        try:
            parsed, resp = _call_ollama_prompt(base, prompt)
        except httpx.HTTPError as exc:
            return _degraded_consolidation(existing_text, str(exc))
        if resp is not None and _is_model_not_pulled(resp):
            return _degraded_consolidation(
                existing_text, "ollama_model_not_pulled"
            )
        if not _is_consolidation_shape(parsed):
            return _degraded_consolidation(existing_text, "malformed_json")

    return _normalize_consolidation(parsed, existing_text)


def _is_consolidation_shape(parsed) -> bool:
    """A usable consolidation payload is a dict carrying ``consolidated_text``."""
    return isinstance(parsed, dict) and "consolidated_text" in parsed


def _normalize_consolidation(parsed: dict, existing_text: str) -> dict:
    """Coerce a parsed consolidation payload into the stable result shape."""
    if not isinstance(parsed, dict):
        return _degraded_consolidation(existing_text, "malformed_json")
    consolidated_text = parsed.get("consolidated_text")
    if not isinstance(consolidated_text, str):
        consolidated_text = existing_text
    fact_actions = parsed.get("fact_actions")
    if not isinstance(fact_actions, list):
        fact_actions = []
    conflicts = parsed.get("conflicts")
    if not isinstance(conflicts, list):
        conflicts = []
    return {
        "consolidated_text": consolidated_text,
        "changed": bool(parsed.get("changed")),
        "fact_actions": fact_actions,
        "conflicts": conflicts,
    }


def sanitize_name(name: str) -> str | None:
    """Apply the name policy (AC#12/AC#16). Returns the cleaned name or None.

    Rejects prompt-like prefixes and over-length names; strips control/bidi/tag
    chars from the remainder.
    """
    if not isinstance(name, str):
        return None
    stripped = strip_control_chars(name).strip()
    if not stripped:
        return None
    lowered = stripped.lstrip().lower()
    for prefix in _NAME_POLICY_PREFIXES:
        if lowered.startswith(prefix):
            return None
    if len(stripped) > _NAME_MAX_LEN:
        return None
    return stripped


# Identifier-like name shapes (Aldeia-IT/aldeia-box#1426 D2/D4). Kept apart from
# sanitize_name on purpose: sanitize_name also guards existing object names in
# query.py, where a slug filter would redact real objects.
_SNAKE_LABEL_RE = re.compile(r"^[A-Za-z0-9]+(_[A-Za-z0-9]+)+$")
_KEBAB_SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+){2,}$")
_URL_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")
_DOTTED_HOST_PATH_RE = re.compile(r"^[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+/")
_FILE_SUFFIXES = (
    ".md", ".markdown", ".json", ".yaml", ".yml", ".toml", ".txt", ".csv",
    ".sql", ".py", ".ts", ".tsx", ".html", ".pdf",
)


def is_identifier_like_name(name: str) -> bool:
    """Tell whether a name looks like a key, slug, URL or file path, not a title.

    Meant for names a model extracted from narrated text (``wiki_remember``
    refuses them, Aldeia-IT/aldeia-box#1426). Do not apply it to a caller-given
    name such as ``subject_hint`` or to existing objects: those are deliberate.
    The name is stripped first. It is identifier-like when any of these holds:

    1. snake_case label: ``founding_date_conflict``, ``Mestra_Janja``;
    2. lowercase ASCII kebab slug with 3+ segments:
       ``associacao-de-capoeira-mestre-bimba`` (two segments such as ``bge-m3``
       or ``gpt-4o`` pass; any uppercase, space or non-ASCII letter passes);
    3. URL-like, no whitespace: a scheme (``https://example.org/x``), ``www.``,
       or a dotted host followed by a slash (``pt.wikipedia.org/wiki/X``); a bare
       dotted name (``Node.js``, ``ASP.NET``, ``capoeira.com``) passes;
    4. file name or path, no whitespace, whose last ``/`` segment ends in a
       document or code suffix (``persons/mestre-bimba.md``, ``notes.yaml``);
       ``.js`` is deliberately not a suffix (``Node.js``).

    Args:
        name: the candidate object name.

    Returns:
        ``True`` when the name matches a rule above; ``False`` otherwise,
        including for non-str or blank input (``sanitize_name`` rejects those).
    """
    if not isinstance(name, str):
        return False
    stripped = name.strip()
    if not stripped:
        return False
    if _SNAKE_LABEL_RE.match(stripped) or _KEBAB_SLUG_RE.match(stripped):
        return True
    if any(ch.isspace() for ch in stripped):
        return False
    if (
        _URL_SCHEME_RE.match(stripped)
        or stripped.lower().startswith("www.")
        or _DOTTED_HOST_PATH_RE.match(stripped)
    ):
        return True
    return stripped.rsplit("/", 1)[-1].lower().endswith(_FILE_SUFFIXES)


def sanitize_property_value(text: str) -> str:
    """Strip control/bidi/tag codepoints from a property value (AC#16/SF2)."""
    if not isinstance(text, str):
        return text
    return strip_control_chars(text)


def filter_extraction_output(raw: dict) -> dict:
    """Strip any LLM-provided ``is_central`` flag (AC#12).

    Centrality is decided by the ingest pipeline, not by attacker-controlled
    source text, so any is_central in the raw output is removed.
    """
    if not isinstance(raw, dict):
        return {"entities": [], "concepts": []}
    out = dict(raw)
    for key in ("entities", "concepts"):
        items = out.get(key)
        if isinstance(items, list):
            cleaned = []
            for item in items:
                if isinstance(item, dict):
                    item = {k: v for k, v in item.items() if k != "is_central"}
                cleaned.append(item)
            out[key] = cleaned
    out.setdefault("entities", [])
    out.setdefault("concepts", [])
    return out


def log_extraction_endpoint() -> None:
    """Emit the active WIKI_EXTRACT_ENDPOINT with credentials scrubbed (AC-S1)."""
    endpoint = os.environ.get("WIKI_EXTRACT_ENDPOINT")
    if not endpoint:
        return
    scrubbed = scrub_credentials(endpoint)
    # Emit on the root logger so a test's root handler captures it. The root
    # logger defaults to WARNING, which would gate an INFO record before it
    # reaches an attached handler — dispatch the record straight to the root
    # handlers so capture does not depend on the ambient root level.
    root = logging.getLogger()
    record = root.makeRecord(
        root.name, logging.INFO, __file__, 0,
        "wiki extraction endpoint: %s", (scrubbed,), None,
    )
    if root.handlers:
        for handler in root.handlers:
            handler.handle(record)
    else:
        root.info("wiki extraction endpoint: %s", scrubbed)


def _default_emit_banner(endpoint: str, ack_path: str) -> None:
    """Print a one-time consent warning and self-ack by writing the ack file."""
    host = httpx.URL(endpoint).host if endpoint else endpoint
    logging.getLogger().warning(
        "wiki extraction will transmit source and previously-stored wiki content "
        "off-machine to %s. As of v0.6.0 this includes the wiki_facts of "
        "already-linked peer entities (distilled from earlier ingests), not only "
        "the current source. Set WIKI_EXTRACT_ENDPOINT to a local endpoint to keep "
        "data on-device.",
        host,
    )
    try:
        Path(ack_path).parent.mkdir(parents=True, exist_ok=True)
        Path(ack_path).touch()
    except OSError:
        pass


def _is_local_endpoint(endpoint: str) -> bool:
    try:
        host = httpx.URL(endpoint).host
    except (httpx.InvalidURL, ValueError, TypeError):
        return False
    return host in _LOCAL_HOSTS


def check_remote_endpoint_consent(
    endpoint: str,
    ack_dir: str | None = None,
    emit_banner=_default_emit_banner,
) -> None:
    """Fire a one-time consent banner for a non-local extraction endpoint (AC-S2.2).

    Local endpoints (127.0.0.1/localhost) are a no-op. For a remote endpoint,
    the ack file is keyed by sha256(endpoint)[:8]; when absent, ``emit_banner``
    is called (the banner writes the ack file).
    """
    if not endpoint or _is_local_endpoint(endpoint):
        return
    ack_dir = ack_dir or _DEFAULT_ACK_DIR
    ep_hash = hashlib.sha256(endpoint.encode("utf-8")).hexdigest()[:8]
    ack_path = os.path.join(ack_dir, f"extraction-endpoint-acknowledged-{ep_hash}")
    if Path(ack_path).exists():
        return
    emit_banner(endpoint, ack_path)
