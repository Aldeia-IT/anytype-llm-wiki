"""run_doctor — preflight checks for the wiki module (spec §Doctor command).

Emits a report dict ``{"exit_code": 0|1|2, "checks": [...]}``. Each check is a
dict with at minimum ``name`` and ``status`` ("OK" | "WARN" | "FAIL") plus a
``message``/``detail``. Exit code: 0 if every check is OK, 1 if any FAIL, 2 if
any WARN without a FAIL.

All HTTP probes use httpx so they are interceptable by respx in tests. The check
sequence and names are the test contract (tests/wiki/test_doctor.py::
EXPECTED_CHECK_NAMES) — do NOT rename without amending the spec first.
"""

import os
import re

import httpx
import psutil

from .. import config as base_config
from . import config as wiki_config
from . import util

_PROBE_TIMEOUT = 5.0
_NETWORK_FS_TYPES = {"nfs", "nfs4", "smbfs", "cifs", "fuse.sshfs", "afpfs"}

# Filesystems doctor recognizes as local-and-safe for fcntl.flock.
_LOCAL_FS_TYPES = {"apfs", "ext4", "ext3", "ext2", "xfs", "btrfs", "tmpfs", "hfs"}


def _check(name: str, status: str, message: str) -> dict:
    return {"name": name, "status": status, "message": message, "detail": message}


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _http_get(url: str) -> httpx.Response:
    """GET a URL with a short timeout. Raises httpx errors on failure."""
    return httpx.get(url, timeout=_PROBE_TIMEOUT)


# ---------------------------------------------------------------------------
# Individual checks. Each returns a check dict and never raises.
# ---------------------------------------------------------------------------


def _check_anytype_api_key() -> dict:
    key = _env("ANYTYPE_API_KEY")
    if key:
        return _check("anytype_api_key", "OK", "ANYTYPE_API_KEY is set.")
    return _check(
        "anytype_api_key",
        "FAIL",
        "ANYTYPE_API_KEY is not set. Generate one via Anytype Settings → API.",
    )


def _check_anytype_reachable() -> dict:
    url = _env("ANYTYPE_API_URL", base_config.ANYTYPE_API_URL)
    safe_url = util.scrub_credentials(url)
    try:
        resp = _http_get(f"{url}/v1/spaces")
    except httpx.HTTPError as exc:
        return _check(
            "anytype_reachable",
            "FAIL",
            f"Anytype not reachable at {safe_url} ({type(exc).__name__}). "
            "Start the Anytype desktop app.",
        )
    if 200 <= resp.status_code < 300:
        return _check("anytype_reachable", "OK", f"Anytype reachable at {safe_url}.")
    return _check(
        "anytype_reachable",
        "FAIL",
        f"Anytype at {safe_url} returned HTTP {resp.status_code}.",
    )


def _check_anytype_version_drift() -> dict:
    configured = _env("ANYTYPE_API_VERSION", base_config.ANYTYPE_API_VERSION)
    decision = util.read_patch_decision()
    recorded = None
    if isinstance(decision, dict):
        recorded = decision.get("anytype_version") or decision.get("ANYTYPE_API_VERSION")
    if not recorded:
        return _check(
            "anytype_version_drift",
            "OK",
            "skipped (v0.2.0) — no patch-decision.md version recorded yet.",
        )
    if recorded == configured:
        return _check(
            "anytype_version_drift",
            "OK",
            f"Anytype API version matches patch-decision.md ({configured}).",
        )
    return _check(
        "anytype_version_drift",
        "WARN",
        f"Anytype API version drift: configured {configured} but "
        f"patch-decision.md recorded {recorded}. Re-run verify-anytype-writes.sh.",
    )


def _check_qdrant_reachable() -> dict:
    url = _env("QDRANT_URL", base_config.QDRANT_URL)
    safe_url = util.scrub_credentials(url)
    try:
        resp = _http_get(f"{url}/readyz")
    except httpx.HTTPError as exc:
        return _check(
            "qdrant_reachable",
            "FAIL",
            f"Qdrant not reachable at {safe_url} ({type(exc).__name__}).",
        )
    if 200 <= resp.status_code < 300:
        return _check("qdrant_reachable", "OK", f"Qdrant reachable at {safe_url}.")
    return _check(
        "qdrant_reachable",
        "FAIL",
        f"Qdrant at {safe_url} returned HTTP {resp.status_code}.",
    )


def _check_qdrant_collection() -> dict:
    url = _env("QDRANT_URL", base_config.QDRANT_URL)
    collection = _env("QDRANT_COLLECTION", base_config.QDRANT_COLLECTION)
    try:
        resp = _http_get(f"{url}/collections/{collection}")
    except httpx.HTTPError as exc:
        return _check(
            "qdrant_collection",
            "WARN",
            f"Could not probe Qdrant collection {collection!r} "
            f"({type(exc).__name__}). It is created by reindex_anytype "
            "(v0.1.0) or the first wiki_ingest (v0.3.0+).",
        )
    if 200 <= resp.status_code < 300:
        return _check(
            "qdrant_collection",
            "OK",
            f"Qdrant collection {collection!r} present.",
        )
    return _check(
        "qdrant_collection",
        "WARN",
        f"Qdrant collection {collection!r} missing (HTTP {resp.status_code}). "
        "Run reindex_anytype (v0.1.0) or the first wiki_ingest (v0.3.0+) to "
        "create it.",
    )


def _ollama_tags() -> tuple[bool, list[dict], str]:
    """Fetch the Ollama /api/tags model list. Returns (reachable, models, detail)."""
    url = _env("OLLAMA_URL", base_config.OLLAMA_URL)
    safe_url = util.scrub_credentials(url)
    try:
        resp = _http_get(f"{url}/api/tags")
    except httpx.HTTPError as exc:
        return False, [], f"Ollama not reachable at {safe_url} ({type(exc).__name__})."
    if not (200 <= resp.status_code < 300):
        return False, [], f"Ollama at {safe_url} returned HTTP {resp.status_code}."
    try:
        models = resp.json().get("models", []) or []
    except ValueError:
        models = []
    return True, models, f"Ollama reachable at {safe_url}."


def _check_ollama_reachable(reachable: bool, detail: str) -> dict:
    if reachable:
        return _check("ollama_reachable", "OK", detail)
    return _check("ollama_reachable", "FAIL", detail)


def _check_ollama_models_pulled(reachable: bool, models: list[dict]) -> dict:
    if not reachable:
        return _check(
            "ollama_models_pulled",
            "FAIL",
            "Cannot verify pulled models — Ollama unreachable.",
        )
    embed_model = _env("EMBED_MODEL", base_config.EMBED_MODEL)
    names = {m.get("name", "") for m in models}
    if embed_model in names:
        return _check(
            "ollama_models_pulled",
            "OK",
            f"Embedding model {embed_model!r} pulled. "
            "(WIKI_EXTRACT_MODEL check is v0.3.0+; skipped in v0.2.0.)",
        )
    return _check(
        "ollama_models_pulled",
        "FAIL",
        f"Embedding model {embed_model!r} not pulled. Run: ollama pull {embed_model}",
    )


def _check_ollama_extraction_model_ram_fit() -> dict:
    extract_model = wiki_config.extract_model()
    try:
        total_ram = psutil.virtual_memory().total
    except Exception:  # pragma: no cover - defensive
        return _check(
            "ollama_extraction_model_ram_fit",
            "OK",
            "RAM probe unavailable; skipping fit check.",
        )
    match = re.search(r":(\d+)b$", extract_model)
    model_billions = int(match.group(1)) if match else 0
    if total_ram < 20 * 1024 ** 3 and model_billions >= 7:
        ram_gb = round(total_ram / (1024 ** 3))
        return _check(
            "ollama_extraction_model_ram_fit",
            "WARN",
            f"{ram_gb} GB RAM + {model_billions}B extraction model "
            f"({extract_model}) will likely thrash swap during the bge-m3 + "
            "extraction model back-to-back swap. Consider a smaller model "
            "(e.g. qwen2.5:3b) — see the README 'Recommended extraction "
            "defaults' table.",
        )
    return _check(
        "ollama_extraction_model_ram_fit",
        "OK",
        f"RAM headroom sufficient for extraction model {extract_model!r}.",
    )


def _check_wiki_lock_dir() -> dict:
    path = wiki_config.lock_dir()
    if not os.path.exists(path):
        return _check(
            "wiki_lock_dir",
            "FAIL",
            f"WIKI_LOCK_DIR {path!r} does not exist. It is created on first "
            "ingest; create it now with mode 0o700 if you want to pre-stage.",
        )
    if not os.path.isdir(path):
        return _check("wiki_lock_dir", "FAIL", f"WIKI_LOCK_DIR {path!r} is not a directory.")
    mode = os.stat(path).st_mode & 0o777
    if mode != 0o700:
        return _check(
            "wiki_lock_dir",
            "FAIL",
            f"WIKI_LOCK_DIR {path!r} has mode {oct(mode)}; expected 0o700. "
            f"Run: chmod 700 {path}",
        )
    if not os.access(path, os.W_OK):
        return _check("wiki_lock_dir", "FAIL", f"WIKI_LOCK_DIR {path!r} is not writable.")
    return _check("wiki_lock_dir", "OK", f"WIKI_LOCK_DIR {path!r} exists, mode 0o700, writable.")


def _check_patch_decision_md() -> dict:
    decision = util.read_patch_decision()
    if decision is None:
        return _check(
            "patch_decision_md",
            "OK",
            "skipped (v0.2.0) — patch-decision.md is recorded at v0.2.0 tag "
            "time by verify-anytype-writes.sh.",
        )
    return _check(
        "patch_decision_md",
        "OK",
        "patch-decision.md present and parseable.",
    )


def _probe_fs_type(path: str) -> str | None:
    """Best-effort filesystem-type probe for ``path``. Never raises."""
    # Resolve to the nearest existing ancestor so an absent lock dir still probes.
    probe = path
    while probe and not os.path.exists(probe):
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent
    if not probe or not os.path.exists(probe):
        return None
    # Linux: read /proc/self/mounts and find the longest matching mount point.
    mounts_path = "/proc/self/mounts"
    if os.path.exists(mounts_path):
        try:
            best_mount = ""
            best_type = None
            real = os.path.realpath(probe)
            with open(mounts_path, encoding="utf-8") as fh:
                for line in fh:
                    parts = line.split()
                    if len(parts) < 3:
                        continue
                    mount_point, fs_type = parts[1], parts[2]
                    if real == mount_point or real.startswith(
                        mount_point.rstrip("/") + "/"
                    ):
                        if len(mount_point) >= len(best_mount):
                            best_mount = mount_point
                            best_type = fs_type
            return best_type
        except OSError:
            return None
    # Darwin / other: no portable cheap fs-type API in stdlib. statvfs exists
    # but does not carry the fs type name. Return None so the check is a benign OK.
    return None


def _check_wiki_lock_dir_fs_type() -> dict:
    path = wiki_config.lock_dir()
    try:
        fs_type = _probe_fs_type(path)
    except Exception:  # pragma: no cover - defensive; probe must never raise
        fs_type = None
    if fs_type is None:
        return _check(
            "wiki_lock_dir_fs_type",
            "OK",
            "Filesystem type could not be determined on this platform; "
            "assuming local. (fcntl.flock requires a local filesystem.)",
        )
    if fs_type in _NETWORK_FS_TYPES:
        return _check(
            "wiki_lock_dir_fs_type",
            "WARN",
            f"WIKI_LOCK_DIR is on a network filesystem ({fs_type}); fcntl.flock "
            "silently non-serializes on network filesystems. Override to a local "
            "path, e.g. WIKI_LOCK_DIR=/tmp/anytype-llm-wiki-locks.",
        )
    return _check(
        "wiki_lock_dir_fs_type",
        "OK",
        f"WIKI_LOCK_DIR filesystem type {fs_type} supports fcntl.flock.",
    )


def _check_wiki_fetch_extra_ports() -> dict:
    ports = wiki_config.fetch_extra_ports()
    if not ports:
        return _check(
            "wiki_fetch_extra_ports",
            "OK",
            "WIKI_FETCH_EXTRA_PORTS empty (default SSRF port allowlist in effect).",
        )
    return _check(
        "wiki_fetch_extra_ports",
        "WARN",
        "WIKI_FETCH_EXTRA_PORTS opens additional ports beyond the default "
        f"{{None, 80, 443}} allowlist: {ports}. Confirm this is intentional.",
    )


def run_doctor() -> dict:
    """Run all preflight checks and return the report dict.

    Returns:
        ``{"exit_code": 0|1|2, "checks": [check_dict, ...]}`` where exit_code is
        0 (all OK), 1 (any FAIL), or 2 (any WARN, no FAIL).
    """
    checks: list[dict] = []

    checks.append(_check_anytype_api_key())
    checks.append(_check_anytype_reachable())
    checks.append(_check_anytype_version_drift())
    checks.append(_check_qdrant_reachable())
    checks.append(_check_qdrant_collection())

    ollama_reachable, ollama_models, ollama_detail = _ollama_tags()
    checks.append(_check_ollama_reachable(ollama_reachable, ollama_detail))
    checks.append(_check_ollama_models_pulled(ollama_reachable, ollama_models))
    checks.append(_check_ollama_extraction_model_ram_fit())

    checks.append(_check_wiki_lock_dir())
    checks.append(_check_patch_decision_md())
    checks.append(_check_wiki_lock_dir_fs_type())
    checks.append(_check_wiki_fetch_extra_ports())

    statuses = {c["status"].upper() for c in checks}
    if "FAIL" in statuses:
        exit_code = 1
    elif "WARN" in statuses:
        exit_code = 2
    else:
        exit_code = 0

    return {"exit_code": exit_code, "checks": checks}
