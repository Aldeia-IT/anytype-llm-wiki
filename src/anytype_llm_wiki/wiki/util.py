"""Shared wiki utilities: title normalization, credential scrubbing, ingest locking.

- ``normalize_title``: deterministic entity-resolution key (NFC + dash-fold +
  casefold + whitespace-collapse). See spec §Entity Resolution Semantics.
- ``scrub_credentials``: strip query string and userinfo from a URL before it
  is logged or written to a lock payload (AC #15).
- ``space_ingest_lock``: per-space advisory file lock (fcntl.flock) enforcing the
  one-ingest-at-a-time-per-space policy (spec §Concurrent Ingest Policy).
- ``read_patch_decision``: v0.2.0 scaffold; reads the patch-decision file if
  present. No caller in v0.2.0.
"""

import fcntl
import json
import os
import re
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from . import config

# ---------------------------------------------------------------------------
# normalize_title — exact implementation from the spec
# ---------------------------------------------------------------------------

_WS_RE = re.compile(r"\s+")
_DASH_FOLDS = {
    0x00AD: "-",  # SOFT HYPHEN
    0x2010: "-",  # HYPHEN
    0x2011: "-",  # NON-BREAKING HYPHEN
    0x2012: "-",  # FIGURE DASH
    0x2013: "-",  # EN DASH
    0x2014: "-",  # EM DASH
    0x2015: "-",  # HORIZONTAL BAR
    0x2212: "-",  # MINUS SIGN
    0xFE63: "-",  # SMALL HYPHEN-MINUS
    0xFF0D: "-",  # FULLWIDTH HYPHEN-MINUS
}


def normalize_title(raw: str) -> str:
    """Normalize a title to a stable entity-resolution key.

    Applies NFC normalization, folds Unicode dash variants to ASCII hyphen,
    casefolds, collapses internal whitespace runs to a single space, and strips
    leading/trailing whitespace.
    """
    nfc = unicodedata.normalize("NFC", raw)
    dash_folded = nfc.translate(_DASH_FOLDS)
    casefolded = dash_folded.casefold()
    collapsed = _WS_RE.sub(" ", casefolded)
    return collapsed.strip()


# ---------------------------------------------------------------------------
# scrub_credentials — strip secrets from URLs before logging (AC #15)
# ---------------------------------------------------------------------------


def scrub_credentials(url: str) -> str:
    """Return ``url`` with query string AND userinfo (user:pass@) removed.

    Scheme, host, port, and path are preserved. Always returns a string, even
    when parsing fails (falls back to the raw input).
    """
    if not isinstance(url, str):
        return str(url)
    try:
        parsed = urlparse(url)
    except (ValueError, TypeError):
        return url

    # Rebuild netloc without userinfo (drop everything up to and including '@').
    netloc = parsed.netloc
    if "@" in netloc:
        netloc = netloc.rsplit("@", 1)[1]

    # Drop the query string and any fragment; keep scheme/host/port/path.
    scrubbed = urlunparse((
        parsed.scheme,
        netloc,
        parsed.path,
        "",   # params
        "",   # query
        "",   # fragment
    ))
    return scrubbed


# ---------------------------------------------------------------------------
# space_ingest_lock — per-space advisory file lock
# ---------------------------------------------------------------------------


@contextmanager
def space_ingest_lock(space_id: str, source_ref: str | None = None):
    """Acquire an exclusive per-space ingest lock for the duration of the context.

    Uses ``fcntl.flock`` with ``LOCK_EX | LOCK_NB``. If another process already
    holds the lock for the same space, raises a RuntimeError whose message
    contains ``[DATA ERROR] ingest_in_progress`` (with a best-effort holder hint).

    On acquisition, writes a JSON payload (pid, started_at, scrubbed source_ref)
    to the lock file. On exit, closes the fd (the kernel releases the flock); the
    lock file is left on disk so it can be re-acquired.
    """
    lock_dir = config.lock_dir()
    os.makedirs(lock_dir, mode=0o700, exist_ok=True)
    # makedirs honors umask, so set the mode explicitly afterwards.
    os.chmod(lock_dir, 0o700)

    lock_path = os.path.join(lock_dir, f"ingest-{space_id}.lock")
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    os.chmod(lock_path, 0o600)

    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            # Best-effort: read the existing holder payload for a hint.
            holder_hint = ""
            try:
                existing = os.read(fd, 4096).decode("utf-8", errors="replace")
                if existing.strip():
                    payload = json.loads(existing)
                    holder_pid = payload.get("pid", "?")
                    holder_started = payload.get("started_at", "?")
                    holder_hint = f" (held by pid {holder_pid} since {holder_started})"
            except (OSError, ValueError):
                holder_hint = ""
            os.close(fd)
            raise RuntimeError(
                f"[DATA ERROR] ingest_in_progress: another ingest is already "
                f"running for space {space_id}{holder_hint}"
            ) from exc

        # Acquired — write the holder payload.
        payload = {
            "pid": os.getpid(),
            "started_at": datetime.now(timezone.utc).isoformat(),
            "source_ref": scrub_credentials(source_ref) if source_ref else "",
        }
        os.ftruncate(fd, 0)
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, json.dumps(payload).encode("utf-8"))
        os.fsync(fd)

        yield
    finally:
        # Closing the fd releases the flock (kernel-level). Leave the file on disk.
        try:
            os.close(fd)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# read_patch_decision — v0.2.0 scaffold (no caller yet)
# ---------------------------------------------------------------------------

_PATCH_DECISION_REL_PATH = (
    ".aldeia/140-wiki-library-module-port-llm-wiki-pattern-onto-any/patch-decision.md"
)


def read_patch_decision() -> dict | None:
    """v0.2.0 scaffold: read and parse the patch-decision file if present.

    The base directory may be overridden via the ``ALDEIA_DIR`` env var for
    testability. Returns a parsed dict, or ``None`` if the file is missing or
    cannot be parsed. v0.2.0 has no caller; this exists so the next worker can
    wire it up.
    """
    base = os.environ.get("ALDEIA_DIR")
    if base:
        path = Path(base) / "patch-decision.md"
    else:
        path = Path(_PATCH_DECISION_REL_PATH)

    if not path.exists():
        return None

    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None

    # Best-effort parse: try JSON first, then fall back to simple key: value lines.
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        pass

    decision: dict = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if key:
            decision[key] = value

    return decision or None
