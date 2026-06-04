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


def _parse_json_response(payload: dict) -> dict | None:
    """Pull the model's text out of an Ollama generate/chat response and parse it."""
    text = None
    if isinstance(payload, dict):
        if "response" in payload:
            text = payload.get("response")
        elif "message" in payload and isinstance(payload["message"], dict):
            text = payload["message"].get("content")
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


def _is_model_not_pulled(resp: httpx.Response) -> bool:
    if resp.status_code != 404:
        return False
    body = resp.text.lower()
    return "not found" in body or "pull it first" in body or "model" in body


def _call_ollama_prompt(
    base: str, prompt: str
) -> tuple[dict | None, httpx.Response | None]:
    """POST a pre-built ``prompt`` to {base}/api/generate then /api/chat.

    Identical generate→chat→model-not-pulled wire behavior as ``_call_ollama``,
    but takes a ready prompt string (no ``{source}`` substitution). Returns
    ``(parsed_or_None, last_resp)``.
    """
    model = config.extract_model()
    think = config.extract_think()
    timeout = httpx.Timeout(connect=5, read=config.extract_timeout(), write=10, pool=5)
    last_resp: httpx.Response | None = None

    with httpx.Client(timeout=timeout) as client:
        gen_resp = client.post(
            f"{base}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "think": think,
                "options": _DETERMINISTIC_OPTS,
            },
        )
        last_resp = gen_resp
        if _is_model_not_pulled(gen_resp):
            return None, gen_resp
        if gen_resp.status_code == 200:
            parsed = _parse_json_response(gen_resp.json())
            if parsed is not None:
                return parsed, gen_resp

        chat_resp = client.post(
            f"{base}/api/chat",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "format": "json",
                "think": think,
                "options": _DETERMINISTIC_OPTS,
            },
        )
        last_resp = chat_resp
        if _is_model_not_pulled(chat_resp):
            return None, chat_resp
        if chat_resp.status_code == 200:
            parsed = _parse_json_response(chat_resp.json())
            if parsed is not None:
                return parsed, chat_resp

    return None, last_resp


def _call_ollama(base: str, markdown: str) -> tuple[dict | None, httpx.Response | None]:
    """POST to {base}/api/generate then /api/chat. Returns (parsed_or_None, last_resp).

    Delegates to ``_call_ollama_prompt`` after the ``{source}`` substitution so
    the extraction wire behavior is byte-identical to the pre-refactor path.
    """
    prompt = _load_prompt().replace("{source}", markdown)
    return _call_ollama_prompt(base, prompt)


def extract(markdown: str, space_id: str, **kw) -> dict:
    """Run LLM extraction. Best-effort; degrades to empty entities/concepts.

    Returns a dict with at least ``entities`` and ``concepts`` keys. On a
    not-pulled Ollama model returns a dict whose str() contains
    ``[CONFIG ERROR] ollama_model_not_pulled``.
    """
    base = os.environ.get("WIKI_EXTRACT_ENDPOINT") or _ollama_url()
    base = base.rstrip("/")

    try:
        parsed, resp = _call_ollama(base, markdown)
    except httpx.HTTPError as exc:
        return {"entities": [], "concepts": [], "error": f"extraction_degraded: {exc}"}

    if resp is not None and _is_model_not_pulled(resp):
        return {
            "entities": [],
            "concepts": [],
            "error": "[CONFIG ERROR] ollama_model_not_pulled: the extraction model "
            f"'{config.extract_model()}' is not available — pull it first",
        }

    if parsed is not None:
        return filter_extraction_output(parsed)

    # Malformed JSON on the first round-trip → one repair attempt (second call).
    try:
        parsed2, resp2 = _call_ollama(base, markdown)
    except httpx.HTTPError as exc:
        return {"entities": [], "concepts": [], "error": f"extraction_degraded: {exc}"}

    if resp2 is not None and _is_model_not_pulled(resp2):
        return {
            "entities": [],
            "concepts": [],
            "error": "[CONFIG ERROR] ollama_model_not_pulled",
        }
    if parsed2 is not None:
        return filter_extraction_output(parsed2)

    # Still malformed after repair → graceful empty result.
    return {"entities": [], "concepts": [], "error": "extraction_degraded: malformed_json"}


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
        "wiki extraction will transmit source content off-machine to %s. "
        "Set WIKI_EXTRACT_ENDPOINT to a local endpoint to keep data on-device.",
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
