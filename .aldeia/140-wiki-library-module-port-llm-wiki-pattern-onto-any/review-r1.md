# Specification Review: Wiki Library Module — Round 1 (Consolidated)

**Reviewed:** 2026-04-22
**Spec:** `.aldeia/140-wiki-library-module-port-llm-wiki-pattern-onto-any/spec.md` (SPEC status, 1465 lines)
**Lead:** dev-lead
**Domain:** product + agent-operations (OSS Python MCP server, LLM extraction pipeline, Anytype typed-object write path)
**Specialists invoked:** completeness-reviewer, spec-architecture-reviewer, security-reviewer, infra-reviewer

## Executive Summary

The spec is unusually thorough for a first SPEC promotion: per-version MoSCoW / acceptance criteria / deliverables / risks / pre-release checklists are consistent across v0.2.0 → v0.5.0; three Mermaid diagrams cover the non-trivial flows; a committed verification script collapses dual API code paths into a single canonical choice; the security posture (SSRF, hosted-LLM disclosure, pip-audit, bearer-token hygiene) is named rather than ignored; and the codebase claims (`type_key` zero-code-change integration, `fastmcp>=2.0.0`, `WikiClient` as a genuine connection-reuse improvement over per-call `anytype_client.py`) are codebase-verified.

However, the review surfaces **six BLOCKING findings** that the spec must resolve before implementation can proceed:

1. `wiki_bootstrap` has no return-shape schema (`BootstrapResult` is referenced but never defined).
2. Post-ingest `reindex_anytype` failure behaviour is undefined — impacts the "compounding query" guarantee in v0.4.0.
3. Two acceptance criteria ("under 5 minutes quick-start", "Karpathy parity") are not independently testable as written.
4. `wiki_contradictions` property is defined and lint-checked but the ingest pipeline never populates it.
5. `normalize_title` pseudocode (NFC + casefold) empirically does NOT fold U+2011 non-breaking hyphen to U+002D, yet an acceptance criterion requires that match. Correctness bug — verified by running Python.
6. `scripts/verify-anytype-writes.sh` mutates the operator's real user-owned Anytype object (name and body) without any cleanup / restore. Foot-gun for any contributor running the pre-release checklist against their main space.

Beyond the BLOCKING set, there are **~30 SHOULD-FIX items** (SSRF snippet has several concrete bugs; prompt injection in extraction is not addressed at all; lock file stale-detection has PID-reuse race; two divergent httpx clients set up drift; entity-resolution pseudocode filter shape doesn't match the real Anytype FilterExpression; v0.2.0 module layout is over-structured relative to what it ships; multiple operator-plumbing gaps: no `doctor` command, no memory budgets, no schema-compatibility check, no CHANGELOG story, extraction token budget undefined) and **~37 SUGGESTIONs** (polish, additional defensive hardening, DX improvements).

**Verdict:** **NEEDS REVISION.** The BLOCKING set must be fixed. The SHOULD-FIX set must also be addressed — the spec is the implementer's source of truth and OSS-community scrutiny will surface any unresolved ambiguity or correctness bug within weeks of tagging v0.2.0.

**Raw reviewer reports:** Individual per-specialist reviews are preserved alongside this file (`review-r1-completeness.md`, `review-r1-architecture.md`, `review-r1-security.md`, `review-r1-infra.md`) for traceability.

---

## Specialist Coverage

| Specialist | Blocking | Should-Fix | Suggestion | Verdict |
|------------|----------|------------|------------|---------|
| completeness-reviewer | 4 | 12 | 10 | NEEDS REVISION |
| spec-architecture-reviewer | 1 | 8 | 5 | NEEDS REVISION |
| security-reviewer | 0 (none blocks v0.2.0) | 10 | 15 | APPROVED WITH CONDITIONS (blocks v0.3.0) |
| infra-reviewer | 1 | 11 | 7 | NEEDS REVISION |

Lead spot-checked: verified `normalize_title` issue empirically matches architecture reviewer's claim; verified `anytype_client.py:16` creates fresh `httpx.Client` per call (architecture integration claim holds); verified `type_key` payload flow through `server.py:42` → `indexer.py:95` → `chunker.py:21` (integration claim holds). No findings were downgraded.

---

## BLOCKING Findings (must resolve before advancing)

### B1. Missing `BootstrapResult` return-shape schema
**Section:** Proposed Solution > MCP Tool Interface / Delivery Phases > v0.2.0
**Source:** completeness #1
**Issue:** `wiki_ingest`, `wiki_query`, `wiki_lint` all have concrete JSON return schemas; `wiki_bootstrap` does not. Spec says bootstrap returns a "structured summary listing every object created" but never enumerates the shape. Acceptance criterion v0.2.0#2 requires reporting each element as "already exists, skipped" — the structure of that report is unspecified. This is the v0.2.0 primary deliverable; implementers cannot write the tool or tests without it.
**Recommendation:** Add a `BootstrapResult` JSON schema parallel to `IngestResult`, minimally: `space_id`, `types_created[]`, `types_skipped[]`, `properties_created[]`, `properties_skipped[]`, `tags_created[]`, `tags_skipped[]`, `root_collection_deeplink`, `wiki_log_id`, `warnings[]`, `status`.

### B2. Undefined behaviour on post-ingest `reindex_anytype` failure
**Section:** v0.3.0 ingest step 8 + Configuration > `WIKI_AUTO_REINDEX`
**Source:** completeness #2
**Issue:** Step 8 calls `reindex_anytype(space_id=...)` post-ingest by default. The Failure-modes table covers Anytype 500 and Qdrant-down for `wiki_ingest` but not the case where `reindex_anytype` fails after successful object creation. Is `status: "ok"` or `"partial"`? Retry? WikiLog amended? Without this, newly-created Source objects are not searchable via `semantic_search`, breaking the v0.4.0 "query compounding" guarantee.
**Recommendation:** Choose one behaviour and document it in both the ingest step and the Failure-modes table. Recommended: ingest returns `status: "ok"` with a `reindex_failed` warning carrying the reindex error detail; WikiLog records the reindex failure; README says "rerun `reindex_anytype` manually if you see this warning". Alternative: downgrade `status` to `"partial"` on reindex failure.

### B3. Acceptance criteria not independently testable
**Section:** Success Criteria + Acceptance Criteria (v0.2.0, v0.3.0)
**Source:** completeness #3
**Issue:** Two ACs use prose success statements that cannot be mechanically evaluated:
- v0.2.0 "a contributor following README-only instructions can run `wiki.bootstrap(...)` in under 5 minutes from a fresh clone" — who measures, on which hardware, how many trials, what's the pass rule?
- v0.3.0 "Karpathy parity: a Wikipedia article URL produces a committed set of Entity/Concept/Source objects with ≥ 2 relations each" — which URL? "Parity" with what?

**Recommendation:** Specify the exact fixture URL (e.g., `https://en.wikipedia.org/wiki/Mamba_(deep_learning_architecture)`), the minimum counts (≥1 Source, ≥3 Entity, ≥2 Concept; every object ≥ 2 relations), the evaluator (v0.3.0 pre-release checklist owner), and the pass rule (single clean run). For the quick-start, either drop the "5 minutes" number from ACs (keep as aspirational prose) or define the measurement protocol (reference hardware: Mac Mini M4, prerequisites met, measured from first `wiki-bootstrap` command to tool return).

### B4. `wiki_contradictions` property lint-checked but never populated
**Section:** Proposed Solution > Type Schema + v0.3.0 Ingest Pipeline + v0.5.0 Lint
**Source:** completeness #4
**Issue:** `wiki_contradictions` is defined on Entity/Concept (lines 238, 248) and referenced by the v0.5.0 "Unresolved contradiction" lint check (line 504). But the v0.3.0 ingest pipeline never describes when or how `wiki_contradictions` is populated, and the extraction prompt schema (lines 980–987) does not emit contradiction claims. The Lint check cannot fire against real wikis.
**Recommendation:** Either (a) extend the extraction prompt schema and IngestResult to detect contradictions (new output field `contradictions: [{from: str, to: str, basis: str}]` + a pipeline step that writes them to `wiki_contradictions`); or (b) explicitly defer contradiction population to a later version and remove the "Unresolved contradiction" check from v0.5.0's Must list.

### B5. `normalize_title` contract contradicts its own acceptance criterion (correctness bug)
**Section:** Entity Resolution Semantics + v0.3.0 Acceptance Criteria + Test Plan
**Sources:** architecture BLOCKING #1 + completeness SHOULD-FIX #9 (lead upgrades to BLOCKING because it is a verified correctness bug in the pseudocode, not a wording issue)
**Issue:** v0.3.0 AC#6 (line 667) and the test plan (line 1267) assert that `"BGE-M3"` and `"BGE‑M3"` (U+2011 non-breaking hyphen) resolve to the same entity via `normalize_title`. The pseudocode at lines 915–931 uses `unicodedata.normalize("NFC", raw).casefold()` + whitespace collapse. Empirically verified: `NFC("BGE‑M3").casefold() == "bge‑m3"` (U+2011) and `NFC("BGE-M3").casefold() == "bge-m3"` (U+002D) are NOT equal. NFKC maps U+2011 → U+2010 "HYPHEN", still not U+002D. As specified, the function fails the AC it is written against.
**Recommendation:** Extend `normalize_title` to map common hyphen/dash codepoints — U+2010 (hyphen), U+2011 (non-breaking hyphen), U+2012 (figure dash), U+2013 (en dash), U+2014 (em dash), U+2212 (minus sign), and their fullwidth variants — to U+002D before the casefold+whitespace steps. Add a unit test enumerating all six codepoints. Update the docstring to state punctuation other than dash-like glyphs is NOT normalized ("GPT-4" vs "GPT 4" remain distinct).

### B6. `scripts/verify-anytype-writes.sh` mutates the operator's real Anytype object with no cleanup
**Section:** Appendix A + v0.2.0 pre-release checklist
**Sources:** infra B1 + security SHOULD-FIX #17 (lead upgrades to BLOCKING — this is a data-loss foot-gun for OSS contributors running the pre-release checklist, per Jan's explicit OSS-scrutiny concern)
**Issue:** The script requires `$ANYTYPE_OBJECT_ID` and mutates the object's body and name with marker strings. An operator running the pre-release checklist against their main space will have one of their real objects permanently renamed and overwritten. No cleanup, no trap, no warning loud enough to prevent the foot-gun. The v0.2.0 pre-release checklist says "`scripts/verify-anytype-writes.sh` run" without naming which space/object — implicitly the operator's real one.
**Recommendation:** Rewrite the script to (a) create its own throwaway test object at start (`POST /v1/spaces/{space}/objects` with a clearly-marked name like `__verify-anytype-writes-probe__`), (b) perform all probes on that object, (c) delete it on exit via a `trap EXIT` handler that fires on success, error, and interrupt. Document the self-contained behaviour in the script header and in Appendix A. Update the pre-release checklist to name the expected ephemeral artifact lifecycle. Apply the same cleanup discipline to the verification test type (`wiki_verify_probe` or similar) — create it for the run, drop it at the end.

---

## SHOULD-FIX Findings (must be addressed)

### Schema and API consistency
**S1.** Unused `WIKI_UPSERT_THRESHOLD_TITLE` in entity-resolution pseudocode. Either add a title-fuzzy step between exact-match and embedding-similarity, or remove the env var from the config table. (completeness #1)

**S2.** `potential_duplicates` example `similarity_score: 0.87` is outside its declared 0.70–0.85 range (would trigger auto-upsert, not duplicate surfacing). Adjust to ~0.78. (completeness #2)

**S3.** "WikiLog receipt in all responses" promise not honoured — `QueryResult` and `LintReport` lack `wiki_log_id` and `wiki_log_deeplink`. `BootstrapResult` (B1 above) must also include it. Either add them or soften the convention wording. (completeness #3)

**S4.** Workflow 2 step 7 implies auto-reindex is opt-in; Configuration table shows `WIKI_AUTO_REINDEX=true` (opt-out). Align — update workflow wording. (completeness #4)

**S5.** Extraction input is described as "truncated to N tokens" but `N` is undefined. Define `WIKI_EXTRACT_MAX_INPUT_TOKENS` with a reasoned default (e.g., 8K leaving headroom for 32K context models like qwen2.5:7b) and specify truncation strategy (head-and-tail, or head-only with a warning). (completeness #5, infra S5)

**S6.** Empty-source extraction handling unspecified. Define: Source object created, 0 entities/concepts, WikiLog entry with `reason=empty_source`, `status: "ok"`. (completeness #5)

**S7.** Write-token-scope-insufficient error path missing from v0.2.0 ACs. Add AC: "`wiki_bootstrap` called with a read-only token returns `[CONFIG ERROR] insufficient_token_scope` pointing to Anytype Settings → API for regeneration." (completeness #7)

**S8.** Query flowchart missing Qdrant-failure branch from Tier-2 node. Prose says "falls back to Tier 1 if threshold allows, else `[API ERROR]`"; diagram does not show it. Add the branch. (completeness #8)

**S9.** `domain_tags` re-bootstrap semantics ambiguous ("replaces" on first call vs "adds without removing" on re-run). State explicitly: "Re-bootstrap with `domain_tags` is union-only; existing tags are never removed, even if absent from the new list." Add a corresponding test. (architecture #2)

**S10.** Entity-resolution pseudocode uses filter shape `{"type_key": type_key}` but the real Anytype FilterExpression shape (per Appendix A line 1425) is `{"condition":"and","filters":[{"key":"type_key","condition":"eq","value":...}]}`. Either use the canonical shape or add a comment pointing at WikiClient.search for translation. (architecture #4)

**S11.** `wiki_ingest.domain_hint` validation semantics unspecified. Add: "If `domain_hint` is not a member of the space's `wiki_domain_tags` taxonomy, return `[CONFIG ERROR]` naming the valid tag set." (architecture #5)

**S12.** `type_key` identifiers not spelled out literally. Add an explicit `type_key:` line per type in the schema section. Align `object_counts` keys in LintReport to the canonical `wiki_source`/`wiki_entity`/`wiki_concept`/`wiki_comparison`/`wiki_query`/`wiki_log` values (currently inconsistent — some have `wiki_` prefix, some don't). (architecture #7)

**S13.** FilterExpression-fallback "list-objects + client-side filter" is hand-waved. Add: "If the fallback path is active, `wiki_query` warns via `warnings` when the returned set exceeds 500 and recommends verifying upstream filter support via the verification script." (architecture #8)

### Architecture and module structure
**S14.** Two divergent Anytype HTTP clients in the same package. `wiki_client.py` gets module-scoped session; `anytype_client.py` stays per-call. Deferred Items notes a follow-up ticket but no deadline. Either extract a shared `_BaseAnytypeClient` in v0.2.0 (~30 LOC, both clients inherit headers/timeout/base URL) OR commit to a concrete consolidation version (e.g., "unify by v0.4.0"). The current open-ended defer will silently rot. (architecture #1)

**S15.** `ipaddress._BaseAddress` is private. Change the type annotation to `ipaddress.IPv4Address | ipaddress.IPv6Address`. (architecture #3)

**S16.** `wiki/` subpackage over-structured for v0.2.0. Eight new files ship in v0.2.0 for a single MCP tool; `locks.py` and `normalize.py` have no callers until v0.3.0. Either merge them into `wiki/util.py` for v0.2.0 and split when called, or explicitly mark them in v0.2.0 Scope (in) as "API stability seeding — tested but not yet invoked by a tool." (architecture #6)

### Security (SSRF, extraction, concurrency, secrets)

**S17.** SSRF: `socket.gethostbyname` is IPv4-only; IPv6 AAAA records bypass the blocklist entirely. Replace with `socket.getaddrinfo(host, None)`, iterate every returned address, reject if *any* lands in a blocked net. This also catches multi-A-record attacks. (security #1)

**S18.** SSRF: IPv4-mapped-IPv6 bypass. `ipaddress.ip_address("::ffff:127.0.0.1")` does not match `127.0.0.0/8`. Normalize with `addr.ipv4_mapped` before the check, or add `::ffff:0:0/96` to `_BLOCKED_NETS` explicitly. (security #2)

**S19.** SSRF: Additional ranges missing — `::/128`, `::ffff:0:0/96`, `64:ff9b::/96`, `100::/64` (IPv6); `0.0.0.0/8`, `100.64.0.0/10` (CGNAT), `198.18.0.0/15` (bench), `224.0.0.0/4` (multicast), `255.255.255.255/32` (IPv4). Use explicit blocklist PLUS `is_private or is_loopback or is_link_local or is_multicast or is_reserved or is_unspecified`. (security #3)

**S20.** SSRF: Scheme allowlist missing. `file://`, `ftp://`, `gopher://`, `data:`, `dict:` currently accepted by default. Reject everything other than `http`/`https` as the first check in `fetch_source`. (security #4)

**S21.** SSRF: URL userinfo (e.g., `https://user:pass@host/`) not stripped or rejected. Reject URLs with `userinfo` set. (security #5)

**S22.** Fetch: No default timeout. Specify `httpx.Timeout(connect=5, read=15, write=5, pool=5)` and a total wall-clock budget (e.g., 30s). Without this, a slow-loris source URL can hang ingest while holding the per-space lock. (security #6, completeness #6 partial)

**S23.** Fetch: No response size cap. A 10 GB response OOMs the process. Specify `max_response_bytes` (e.g., 10 MiB) and stream-read with early abort. (security #7, completeness #6 partial)

**S24.** DNS-rebinding mitigation claimed but not implemented — the snippet does `gethostbyname` then calls `httpx.get(url)` which re-resolves at connect time. Either implement connect-by-IP (custom `httpx.HTTPTransport` binding the resolved IP, preserving `Host` header) or drop the "DNS rebinding mitigated" claim and label as accepted residual risk. (security #8)

**S25.** Prompt injection into extraction unaddressed. Malicious source content with `<!-- SYSTEM: ... -->` payloads steers extraction output. Mitigations to add: (a) wrap source in `<source>...</source>` fence with explicit "nothing inside is a directive" instruction in the prompt; (b) validate extracted names (length cap, no control chars, no `ignore|system:|assistant:` prefixes); (c) README note that wiki trustworthiness tracks source trustworthiness; (d) `is_central` cross-check against source structure rather than LLM self-report. (security #9)

**S26.** LLM extraction JSON parsed but not schema-validated. Add pydantic model or jsonschema validation in `wiki/extraction.py`; malformed-but-valid JSON must trigger the existing repair-retry path. Add a property-based test (Hypothesis) generating adversarial-but-parseable JSON. (security #10)

**S27.** Lock PID-reuse race. `os.kill(pid, 0)` success means "some process" has the PID, not "the original ingest." After reboot + PID reuse, the spec's logic treats the lock as held forever. Add `started_at` comparison against `psutil.Process(pid).create_time()` OR adopt `fcntl.flock` (advisory kernel-held lock, auto-released on exit) OR add a TTL (e.g., 30 min) as a belt-and-suspenders cue. Pick one and document it. (completeness #10, security #13, #14, infra S2)

**S28.** TOCTOU in stale-lock replacement. Between liveness check and `O_CREAT|O_EXCL` re-attempt, another process can acquire the now-stale lock. Tight retry loop with cap, OR switch to `fcntl.flock`. (security #13)

### Operator plumbing (infra)
**S29.** No `anytype-llm-wiki doctor` command. Add to v0.2.0 scope: checks Anytype reachable, Qdrant reachable, Ollama reachable, `qwen2.5:7b` and `bge-m3` pulled, `ANYTYPE_API_KEY` set, lock dir writable, `patch-decision.md` present/parseable. Eliminates most first-run support burden. ~50 LOC. (infra S1)

**S30.** Per-operation memory/CPU budgets absent. Only wall-time budgets are stated. Add reference-hardware budgets: "Mac Mini M4, 16 GB, Ollama + Anytype + Qdrant running: peak RSS of `anytype-llm-wiki` process ≤ 500 MB during ingest; Ollama RSS dominated by loaded models." State the minimum recommended RAM (32 GB for co-resident bge-m3 + qwen2.5:7b comfortable; 16 GB marginal with extraction-model tuning). (infra S4)

**S31.** Schema migration / upgrade-downgrade story absent. Every `wiki_*` tool should run a schema-compatibility check on entry; emit `[CONFIG ERROR]` "re-run `wiki_bootstrap` to add missing v{X}.{Y} properties" when schema is older than the code. Add a MIGRATIONS.md or README "Upgrading" section. (infra S6)

**S32.** Qdrant collection growth model absent. README paragraph: "per 100 sources, expect ~50 MB Qdrant growth; rebuild via `reindex_anytype --full` if the collection drifts." (infra S7)

**S33.** No file-logging / rotation guidance. README "Logging" paragraph with a recipe (`anytype-llm-wiki serve 2>> ~/.local/share/anytype-llm-wiki/run.log`) and note on rotation-friendly format. (infra S8)

**S34.** CHANGELOG schema and MIGRATIONS story not spec'd. Define CHANGELOG format (user-visible vs internal) and a per-version "Upgrading" section requirement. (infra S9)

**S35.** `scripts/verify-anytype-writes.sh` CI runnability. State explicitly: "runs on the maintainer's machine during pre-release, not in CI" to prevent wasted contributor effort on GH Actions wiring. (infra S10)

**S36.** Reconsider the `wiki.status` deferral. A 10-LOC "count objects by type + last ingest timestamp" tool would materially improve daily operator experience without blocking anything. Spec should either land it in v0.2.0 / v0.5.0 or document a concrete reconsideration trigger (e.g., "when ≥3 community issues request it"). (infra S11)

### Test plan hardening
**S37.** Hand-seeded v0.4.0 test fixture mechanism unnamed. Specify: `tests/wiki/test_query.py` uses `WikiClient.create_object` directly (via respx mocks) to construct the synthetic 199/200/201-object fixture. (completeness #11)

**S38.** OQ#3 (Extraction model default) tension. Config table commits to `qwen2.5:7b` as provisional; OQ#3 should either close (default is picked, validation is the follow-up) or remain open with the config marked `*(provisional — see OQ#3)*` consistently. (completeness #12)

---

## SUGGESTION Findings (should be addressed)

### Naming and documentation polish
**G1.** Entity uses `wiki_relations`; Concept uses `wiki_related`. Unify, OR add a schema comment "deliberately distinct property keys to disambiguate graph queries." (completeness #1)

**G2.** `wiki/__init__.py` "public exports" wording blurs MCP tool names with Python function names. Clarify the comment. (completeness #2)

**G3.** `extraction_endpoint` at ingest startup — add rule "URL query strings and userinfo stripped before logging" to prevent accidental key leaks. (completeness #3)

**G4.** v0.5.0 dependency phrasing inconsistent with opening Delivery Phases phrasing. Tighten to the single canonical form. (completeness #4)

**G5.** Appendix A write-test cleanup — superseded by B6 (cleanup is now required, not suggested).

**G6.** Anytype type-level deeplink format undefined. Either define `anytype://type/{space}/{type_key}` or state fallback "opens space root until format confirmed." (completeness #6)

**G7.** v0.3.0 performance budget absent (ingest wall-time). Soft target: "< 2 min p95 for a 10k-word source on reference hardware" OR explicit "no wall-clock SLO in v0.3.0; latency is a v0.6+ tuning task." (completeness #7)

**G8.** "First Anytype-native LLM wiki" claim — in addition to the verification step, have a fallback positioning line ready so a README swap is a one-liner if prior art is found. (completeness #8)

**G9.** `WIKI_LOG_LEVEL` env var (info | debug) for opt-in verbosity. (completeness #9)

**G10.** Deferred Items: note concrete follow-up ticket numbers once filed for traceability. (completeness #10)

### Schema and architecture polish
**G11.** WikiLog "append-only" is a convention, not enforced. Add a one-sentence note: "Append-only is a convention. The lint suite does not check for retroactive WikiLog edits." (architecture #1)

**G12.** Add a `wiki_status: stub` lint check in v0.5.0 ("stub older than 30 days" Medium severity). Matches existing 7 checks' shape. (architecture #2)

**G13.** Rationale for `markdownify` over `html2text` in one sentence. (architecture #3)

**G14.** Delivery-phase dependency graph: one-line Mermaid or ASCII at the top of Delivery Phases. (architecture #4)

**G15.** "First Anytype-native" claim verification belongs on the v0.2.0 pre-release checklist (currently only code artifacts). (architecture #5)

### Security hardening
**G16.** Privacy notice must also flag `QDRANT_URL` / `OLLAMA_URL` off-localhost risk and embedding-inversion attacks on vectors. (security #11, #18)

**G17.** Lock file permission mode unspecified. `os.open(..., mode=0o600)`, lock dir `0o700`, explicit `os.chmod` pass to fix pre-existing dir modes. (security #12)

**G18.** Error message hygiene: strip bearer token / full `Authorization` header from user-visible `[API ERROR]` strings; use relative paths or placeholders rather than absolute home directory paths in `[DATA ERROR]` messages (e.g., `$WIKI_LOCK_DIR/ingest-{space_id}.lock`). Add tests. (security #15, #16)

**G19.** Block unusual ports in SSRF check. Allowlist 80, 443, 8080, 8443 OR at minimum reject 31012, 6333, 11434. (security #19)

**G20.** Markdown / control-char / bidi-override injection into entity names and bodies. Reject names matching `re.compile(r"[\x00-\x1f​-‏‪-‮⁦-⁩]")`. Add a test. (security #20)

**G21.** Log-injection resistance test — adversarial source title with embedded newlines / `[CRITICAL]`-like text. Confirm single-line JSON logging handles it. (security #21)

**G22.** Add Bandit (OSS code insecure-defaults scan) alongside `pip-audit`. Optional but cheap. (security #22)

**G23.** Lock CI job that verifies `uv.lock` is up to date with `pyproject.toml`. OSSF Scorecard optional. (security #23)

**G24.** `gitleaks` / `trufflehog` pre-commit or CI step for accidental token commits. (security #24)

**G25.** First-run hosted-LLM banner ack file — include endpoint hash so a later config change re-prompts. `extraction-endpoint-acknowledged-{sha256(endpoint)[:8]}` or JSON recording all acknowledged endpoints. (security #25)

### Operator DX
**G26.** `wiki_lint --json` vs `--human` output modes. (infra G1)

**G27.** Consider `fcntl.flock` instead of `O_CREAT|O_EXCL` — eliminates stale-lock class entirely. Trade-off: not portable to NFS, but spec already disclaims network-mounted-home support. Overlaps with S27. (infra G2)

**G28.** Log `extraction_endpoint` on every ingest, not just server boot. (infra G3)

**G29.** Document Anytype's data-dir location (`~/Library/Application Support/Anytype2` on macOS) so backup advice points there. (infra G4)

**G30.** `wiki_bootstrap --dry-run` for community developers evaluating before committing. (infra G5)

**G31.** `WIKI_MIN_EXTRACT_RAM_GB` advisory preflight check via `psutil.virtual_memory().available`. (infra G6)

**G32.** README troubleshooting section seeded from the failure-modes table (each row → one H3). (infra G7)

---

## What's Done Well (preserve on fix)

- Per-version Scope/MoSCoW/Acceptance/Deliverables/Dependencies/Risks/Pre-release/Tests structure consistently applied across v0.2.0–v0.5.0.
- Single-canonical-path discipline for PATCH body and FilterExpression with committed verification script and decision record (`patch-decision.md`).
- Three Mermaid diagrams cover non-trivial flows (ingest, query, lint).
- Boundary test at 199/200/201 for the tiered retrieval mode switch.
- Security posture named explicitly (SSRF architectural shape, bearer token env-only, pip-audit, hosted-LLM triple-layer disclosure).
- Entity Resolution Semantics section with `normalize_title` contract + pseudocode + thresholds (modulo B5 correctness fix).
- Contributor's Map at the top with ordered reading path and "v0.1.0 untouched" additivity claim.
- Deferred Items section explains *why* each item is deferred, not merely that it is.
- Open Questions tagged with owning version ("Must resolve by").
- Failure-modes table per tool.
- Error-category taxonomy (`api_error` / `data_error` / `config_error`).
- Codebase-verified integration claims: `type_key` zero-code-change extension, `fastmcp>=2.0.0`, `WikiClient` as a genuine improvement over per-call `anytype_client.py`.

---

## Verdict

**NEEDS REVISION** — 6 BLOCKING findings must be resolved; the SHOULD-FIX set must also be addressed. Dispatch a fresh spec-fixer to produce a revised spec.md addressing every finding. Re-review after the fix.
