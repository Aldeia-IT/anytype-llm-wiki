"""Tests for wiki/util.py — normalize_title (dash-fold table) + space_ingest_lock.

Covers the full 14-row dash-fold parametrize table from spec line 1232,
and the space_ingest_lock contextmanager contract.
Uses \\uXXXX escape form (not literal invisible characters) per CSO R3-CSO-1.
"""

import os
import json
import multiprocessing
import time
import pytest


# ---------------------------------------------------------------------------
# normalize_title tests
# ---------------------------------------------------------------------------

class TestNormalizeTitleImport:
    def test_normalize_title_importable(self):
        """normalize_title must be importable from wiki.util."""
        from anytype_llm_wiki.wiki.util import normalize_title  # noqa: F401

    def test_normalize_title_is_callable(self):
        from anytype_llm_wiki.wiki.util import normalize_title
        assert callable(normalize_title)


class TestNormalizeTitleDashFold:
    """Parametrized 14-row dash-fold table from spec §Entity Resolution Semantics.

    All rows that 'match' are expected to produce the same normalized string
    as the ASCII-hyphen baseline "bge-m3" (after casefolding and stripping).

    Row 14 (BGE  -  M3 with spaces around dash) is the deliberate NON-match.
    """

    @pytest.mark.parametrize("raw,should_match_baseline", [
        # Row 1: ASCII HYPHEN-MINUS (baseline) — U+002D, visible in all editors
        ("BGE-M3", True),
        # Row 2: SOFT HYPHEN U+00AD — invisible conditional hyphen, classic PDF-copy-paste vector
        ("BGE\u00adM3", True),
        # Row 3: HYPHEN U+2010
        ("BGE\u2010M3", True),
        # Row 4: NON-BREAKING HYPHEN U+2011
        ("BGE\u2011M3", True),
        # Row 5: FIGURE DASH U+2012
        ("BGE\u2012M3", True),
        # Row 6: EN DASH U+2013
        ("BGE\u2013M3", True),
        # Row 7: EM DASH U+2014
        ("BGE\u2014M3", True),
        # Row 8: HORIZONTAL BAR U+2015 — em-dash cousin, Korean/Japanese typography
        ("BGE\u2015M3", True),
        # Row 9: MINUS SIGN U+2212
        ("BGE\u2212M3", True),
        # Row 10: SMALL HYPHEN-MINUS U+FE63
        ("BGE\ufe63M3", True),
        # Row 11: FULLWIDTH HYPHEN-MINUS U+FF0D
        ("BGE\uff0dM3", True),
        # Row 12: casefold — lower-case should match baseline
        ("bge-m3", True),
        # Row 13: whitespace trim — leading/trailing spaces collapse
        ("  BGE-M3  ", True),
        # Row 14: DELIBERATE NON-MATCH — whitespace around dash is preserved as distinct token
        ("BGE  -  M3", False),
    ])
    def test_normalize_title_dash_fold(self, raw, should_match_baseline):
        """normalize_title({raw!r}) == baseline 'bge-m3' should be {should_match_baseline}."""
        from anytype_llm_wiki.wiki.util import normalize_title
        baseline = normalize_title("BGE-M3")
        normalized = normalize_title(raw)
        if should_match_baseline:
            assert normalized == baseline, (
                f"normalize_title({raw!r}) = {normalized!r}, "
                f"expected to match baseline {baseline!r}"
            )
        else:
            assert normalized != baseline, (
                f"normalize_title({raw!r}) = {normalized!r}, "
                f"expected to NOT match baseline {baseline!r} (whitespace-padded dash is distinct)"
            )


class TestNormalizeTitleEdgeCases:
    def test_empty_string(self):
        """normalize_title('') must return empty string without error."""
        from anytype_llm_wiki.wiki.util import normalize_title
        assert normalize_title("") == ""

    def test_whitespace_only(self):
        """normalize_title('   ') must return empty string after strip."""
        from anytype_llm_wiki.wiki.util import normalize_title
        assert normalize_title("   ") == ""

    def test_multiple_whitespace_runs_collapsed(self):
        """Internal whitespace runs are collapsed to single space."""
        from anytype_llm_wiki.wiki.util import normalize_title
        result = normalize_title("hello   world")
        assert result == "hello world"

    def test_nfc_normalization_applied(self):
        """NFC normalization must be applied (precomposed forms resolve to same string)."""
        import unicodedata
        from anytype_llm_wiki.wiki.util import normalize_title
        # NFD form of 'é' (e + combining acute) vs NFC form
        nfd = "é"   # 'e' + combining acute accent
        nfc = "é"     # precomposed 'é'
        assert normalize_title(nfd) == normalize_title(nfc)

    def test_non_dash_punctuation_preserved(self):
        """Periods, commas, slashes, and quotes are NOT normalized."""
        from anytype_llm_wiki.wiki.util import normalize_title
        assert normalize_title("GPT-4") != normalize_title("GPT 4"), (
            "GPT-4 and 'GPT 4' must remain distinct entities"
        )

    def test_returns_string(self):
        from anytype_llm_wiki.wiki.util import normalize_title
        result = normalize_title("BGE-M3")
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# space_ingest_lock tests
# ---------------------------------------------------------------------------

class TestSpaceIngestLockImport:
    def test_space_ingest_lock_importable(self):
        """space_ingest_lock must be importable from wiki.util."""
        from anytype_llm_wiki.wiki.util import space_ingest_lock  # noqa: F401

    def test_space_ingest_lock_is_callable(self):
        from anytype_llm_wiki.wiki.util import space_ingest_lock
        assert callable(space_ingest_lock)


class TestSpaceIngestLockIsContextManager:
    def test_space_ingest_lock_is_context_manager(self, tmp_path, monkeypatch):
        """space_ingest_lock must work as a context manager (no error on acquire + release)."""
        monkeypatch.setenv("WIKI_LOCK_DIR", str(tmp_path / "locks"))
        from anytype_llm_wiki.wiki.util import space_ingest_lock
        with space_ingest_lock("test-space-001"):
            pass  # should not raise


class TestSpaceIngestLockDirectoryCreation:
    def test_creates_lock_dir_if_missing(self, tmp_path, monkeypatch):
        """space_ingest_lock must create WIKI_LOCK_DIR with mode 0o700 if absent."""
        lock_dir = tmp_path / "new-locks"
        monkeypatch.setenv("WIKI_LOCK_DIR", str(lock_dir))
        from anytype_llm_wiki.wiki.util import space_ingest_lock
        with space_ingest_lock("space-mkdir-test"):
            pass
        assert lock_dir.exists(), "WIKI_LOCK_DIR was not created"
        mode = oct(lock_dir.stat().st_mode)[-3:]
        assert mode == "700", f"WIKI_LOCK_DIR mode is {mode}, expected 700"

    def test_lock_file_mode_600(self, tmp_path, monkeypatch):
        """Lock files must be created with mode 0o600."""
        lock_dir = tmp_path / "locks"
        monkeypatch.setenv("WIKI_LOCK_DIR", str(lock_dir))
        from anytype_llm_wiki.wiki.util import space_ingest_lock
        with space_ingest_lock("space-mode-test"):
            lock_file = lock_dir / "ingest-space-mode-test.lock"
            assert lock_file.exists(), "Lock file not created during context"
            mode = oct(lock_file.stat().st_mode)[-3:]
            assert mode == "600", f"Lock file mode is {mode}, expected 600"


class TestSpaceIngestLockPayload:
    def test_lock_payload_has_required_keys(self, tmp_path, monkeypatch):
        """Lock file payload must be JSON with pid, started_at, source_ref keys."""
        lock_dir = tmp_path / "locks"
        monkeypatch.setenv("WIKI_LOCK_DIR", str(lock_dir))
        from anytype_llm_wiki.wiki.util import space_ingest_lock
        with space_ingest_lock("space-payload-test"):
            lock_file = lock_dir / "ingest-space-payload-test.lock"
            content = lock_file.read_text()
            payload = json.loads(content)
            assert "pid" in payload, "Lock payload missing 'pid'"
            assert "started_at" in payload, "Lock payload missing 'started_at'"
            assert "source_ref" in payload, "Lock payload missing 'source_ref'"

    def test_lock_payload_pid_is_current_process(self, tmp_path, monkeypatch):
        """Lock file payload 'pid' must be the current process PID."""
        lock_dir = tmp_path / "locks"
        monkeypatch.setenv("WIKI_LOCK_DIR", str(lock_dir))
        from anytype_llm_wiki.wiki.util import space_ingest_lock
        with space_ingest_lock("space-pid-test"):
            lock_file = lock_dir / "ingest-space-pid-test.lock"
            payload = json.loads(lock_file.read_text())
            assert payload["pid"] == os.getpid()


class TestSpaceIngestLockSourceRefRedaction:
    def test_source_ref_strips_query_string(self, tmp_path, monkeypatch):
        """source_ref in payload must not contain query-string parameters."""
        lock_dir = tmp_path / "locks"
        monkeypatch.setenv("WIKI_LOCK_DIR", str(lock_dir))
        from anytype_llm_wiki.wiki.util import space_ingest_lock
        sensitive_url = "https://example.com/article?api_key=SEKRET&token=abc123"
        with space_ingest_lock("space-redact-test", source_ref=sensitive_url):
            lock_file = lock_dir / "ingest-space-redact-test.lock"
            payload = json.loads(lock_file.read_text())
            assert "SEKRET" not in payload["source_ref"], (
                "Query-string secret leaked into lock payload source_ref"
            )
            assert "api_key" not in payload["source_ref"], (
                "Query-string key leaked into lock payload source_ref"
            )

    def test_source_ref_strips_userinfo(self, tmp_path, monkeypatch):
        """source_ref in payload must not contain userinfo (user:pass@host)."""
        lock_dir = tmp_path / "locks"
        monkeypatch.setenv("WIKI_LOCK_DIR", str(lock_dir))
        from anytype_llm_wiki.wiki.util import space_ingest_lock
        sensitive_url = "https://api-user:api-secret@hosted.example.com/v1/chat"
        with space_ingest_lock("space-userinfo-test", source_ref=sensitive_url):
            lock_file = lock_dir / "ingest-space-userinfo-test.lock"
            payload = json.loads(lock_file.read_text())
            assert "api-secret" not in payload["source_ref"], (
                "Userinfo password leaked into lock payload source_ref"
            )
            assert "api-user" not in payload["source_ref"], (
                "Userinfo username leaked into lock payload source_ref"
            )


def _try_acquire_lock(lock_dir: str, space_id: str, result_queue):
    """Helper run in a child process: try to acquire the lock, put result in queue."""
    os.environ["WIKI_LOCK_DIR"] = lock_dir
    # Import inside subprocess to get fresh module state
    from anytype_llm_wiki.wiki.util import space_ingest_lock
    try:
        with space_ingest_lock(space_id):
            result_queue.put("acquired")
            time.sleep(2)  # hold the lock briefly
    except Exception as exc:
        result_queue.put(f"error: {exc}")


class TestSpaceIngestLockConcurrency:
    """Two OS-level processes attempting to acquire the same space lock — the canonical test.

    Per spec Test Plan line 1913: multiprocessing.Process is required;
    threading.Thread against a mocked lock is insufficient.
    """

    def test_second_process_fails_with_ingest_in_progress(self, tmp_path, monkeypatch):
        """A second process acquiring the same space lock must get [DATA ERROR] ingest_in_progress."""
        lock_dir = str(tmp_path / "locks")
        monkeypatch.setenv("WIKI_LOCK_DIR", lock_dir)
        os.makedirs(lock_dir, mode=0o700, exist_ok=True)
        from anytype_llm_wiki.wiki.util import space_ingest_lock

        space_id = "concurrent-test-space"
        result_queue: multiprocessing.Queue = multiprocessing.Queue()

        # Start a child process that acquires the lock and holds it
        holder = multiprocessing.Process(
            target=_try_acquire_lock,
            args=(lock_dir, space_id, result_queue),
        )
        holder.start()

        # Deterministic handoff: block until the child confirms it holds the lock
        # (the child puts "acquired" on the queue inside its locked context).
        # This replaces a fixed sleep, removing a CI-flake race.
        handoff = result_queue.get(timeout=5)
        assert handoff == "acquired", (
            f"Child process failed to acquire the lock first; got: {handoff!r}"
        )

        # Attempt to acquire from the parent process — must fail
        try:
            with space_ingest_lock(space_id):
                pytest.fail("Second process should NOT have acquired the lock")
        except Exception as exc:
            error_str = str(exc)
            assert "ingest_in_progress" in error_str, (
                f"Expected 'ingest_in_progress' in error, got: {error_str!r}"
            )

        holder.terminate()
        holder.join(timeout=5)

    def test_different_spaces_can_lock_concurrently(self, tmp_path, monkeypatch):
        """Two different space_ids must be able to hold their locks simultaneously."""
        lock_dir = str(tmp_path / "locks")
        monkeypatch.setenv("WIKI_LOCK_DIR", lock_dir)
        from anytype_llm_wiki.wiki.util import space_ingest_lock
        # This should not raise — two different spaces, two different lock files
        with space_ingest_lock("space-alpha"):
            with space_ingest_lock("space-beta"):
                pass  # both held simultaneously

    def test_lock_releases_after_context_exit(self, tmp_path, monkeypatch):
        """After the context manager exits, the same space can be re-acquired."""
        lock_dir = str(tmp_path / "locks")
        monkeypatch.setenv("WIKI_LOCK_DIR", lock_dir)
        from anytype_llm_wiki.wiki.util import space_ingest_lock
        # First acquisition
        with space_ingest_lock("space-reacquire"):
            pass
        # Second acquisition -- must succeed because first was released
        with space_ingest_lock("space-reacquire"):
            pass


# ---------------------------------------------------------------------------
# scrub_credentials tests — AC #15
# ---------------------------------------------------------------------------

class TestCredentialScrubbing:
    """AC #15: scrub_credentials must remove secrets from URLs before logging.

    Tests call anytype_llm_wiki.wiki.util.scrub_credentials directly — no
    bootstrap call path needed. This avoids the tautology of relying on
    wiki_bootstrap to read a credential that it never touches at runtime.

    Spec line 745: A forced [API ERROR] where QDRANT_URL=...?api_key=SEKRET123
    must return an error string containing neither SEKRET123 nor the raw
    ?api_key=... query string. Same assertion for WIKI_EXTRACT_ENDPOINT userinfo.
    """

    def test_scrub_credentials_importable(self):
        """scrub_credentials must be importable from wiki.util."""
        from anytype_llm_wiki.wiki.util import scrub_credentials  # noqa: F401

    def test_scrub_credentials_is_callable(self):
        from anytype_llm_wiki.wiki.util import scrub_credentials
        assert callable(scrub_credentials)

    def test_qdrant_url_api_key_value_scrubbed(self):
        """scrub_credentials on a QDRANT_URL with ?api_key=SEKRET123 must not return the secret value."""
        from anytype_llm_wiki.wiki.util import scrub_credentials
        url = "https://xyz.cloud.qdrant.io/collections/x?api_key=SEKRET123"
        result = scrub_credentials(url)
        assert "SEKRET123" not in result, (
            f"scrub_credentials must not return the raw api_key value; got: {result!r}"
        )

    def test_qdrant_url_api_key_query_param_scrubbed(self):
        """scrub_credentials on a QDRANT_URL must not return the raw ?api_key= substring."""
        from anytype_llm_wiki.wiki.util import scrub_credentials
        url = "https://xyz.cloud.qdrant.io/collections/x?api_key=SEKRET123"
        result = scrub_credentials(url)
        assert "?api_key=" not in result, (
            f"scrub_credentials must not return the raw ?api_key= query string; got: {result!r}"
        )

    def test_qdrant_url_host_preserved(self):
        """scrub_credentials must preserve the host portion of the URL."""
        from anytype_llm_wiki.wiki.util import scrub_credentials
        url = "https://xyz.cloud.qdrant.io/collections/x?api_key=SEKRET123"
        result = scrub_credentials(url)
        assert "xyz.cloud.qdrant.io" in result, (
            f"scrub_credentials must preserve the host; got: {result!r}"
        )

    def test_userinfo_password_scrubbed(self):
        """scrub_credentials on a URL with userinfo must not return the password."""
        from anytype_llm_wiki.wiki.util import scrub_credentials
        url = "https://api-user:api-secret@hosted.example.com/v1/chat"
        result = scrub_credentials(url)
        assert "api-secret" not in result, (
            f"scrub_credentials must not return the userinfo password; got: {result!r}"
        )

    def test_userinfo_colon_password_at_combo_scrubbed(self):
        """scrub_credentials must not return the raw 'user:pass@' userinfo component."""
        from anytype_llm_wiki.wiki.util import scrub_credentials
        url = "https://api-user:api-secret@hosted.example.com/v1/chat"
        result = scrub_credentials(url)
        assert "api-user:api-secret@" not in result, (
            f"scrub_credentials must not return the raw 'user:pass@' form; got: {result!r}"
        )

    def test_userinfo_host_preserved(self):
        """scrub_credentials must preserve the host when userinfo is stripped."""
        from anytype_llm_wiki.wiki.util import scrub_credentials
        url = "https://api-user:api-secret@hosted.example.com/v1/chat"
        result = scrub_credentials(url)
        assert "hosted.example.com" in result, (
            f"scrub_credentials must preserve the host; got: {result!r}"
        )

    def test_plain_url_unchanged(self):
        """scrub_credentials on a plain URL with no credentials must return a non-empty string."""
        from anytype_llm_wiki.wiki.util import scrub_credentials
        url = "https://localhost:6333/collections/anytype_semantic"
        result = scrub_credentials(url)
        assert result, "scrub_credentials must return a non-empty string for plain URLs"
        assert "localhost" in result, (
            f"scrub_credentials must preserve plain URL host; got: {result!r}"
        )

    def test_returns_string(self):
        """scrub_credentials must always return a string."""
        from anytype_llm_wiki.wiki.util import scrub_credentials
        result = scrub_credentials("https://example.com/path?key=value")
        assert isinstance(result, str), (
            f"scrub_credentials must return str, got {type(result)!r}"
        )
