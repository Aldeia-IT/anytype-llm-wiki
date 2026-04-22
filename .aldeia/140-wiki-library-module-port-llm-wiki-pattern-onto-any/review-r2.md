# Specification Review: Wiki Library Module — Round 2 (Verification)

**Reviewed:** 2026-04-22
**Spec Version:** commit `bcb452a` (spec.md, 1912 lines, `status: SPEC`, `review_rounds: 1`)
**Scope:** verification of round-1 fixes — delta review only, not a re-run of the full review.

## Verdict

**APPROVED**

**Rationale:** Every BLOCKING finding from round 1 is resolved with the correct design choice (not merely acknowledged). Every SHOULD-FIX is addressed with concrete spec language — schemas now carry `wiki_log_id` uniformly, the SSRF code uses `getaddrinfo` with IPv4-mapped IPv6 normalization and a defense-in-depth blocklist, `normalize_title` pseudocode correctly dash-folds U+2010/U+2011/U+2012/U+2013/U+2014/U+2212 (plus U+FE63 and U+FF0D as bonuses) BEFORE casefold, the lock uses `fcntl.flock` (eliminating the PID-reuse and TOCTOU classes entirely), and the verification script creates and deletes its own probe artifacts via `trap EXIT INT TERM`. SUGGESTIONs that I spot-checked all landed. No regressions introduced: Mermaid diagrams remain four valid graphs, the per-version Scope/MoSCoW/AC/Deliverables discipline is intact, the single-canonical-path rule for PATCH body and FilterExpression is preserved. One minor coherence nit in the failure-modes table (line 1480 still conditionally references the superseded `O_CREAT|O_EXCL` path) is flagged as SUGGESTION only — the primary lock policy (fcntl.flock) is coherent throughout.

## Round-1 Finding Resolution Table

### BLOCKING
| ID | Finding | Resolution | Notes |
|----|---------|------------|-------|
| B1 | Missing `BootstrapResult` return-shape schema | **RESOLVED** | Full schema at lines 304–334 with every recommended field: `space_id`, `types_created[]`, `types_skipped[]`, `properties_created[]`, `properties_skipped[]`, `tags_created[]`, `tags_skipped[]`, `root_collection_id`, `root_collection_deeplink`, `wiki_log_id`, `wiki_log_deeplink`, `warnings[]`, `status`. Schema notes on `null` for `wiki_log_id` when Anytype unreachable are a nice touch. |
| B2 | Undefined `reindex_anytype` failure behaviour | **RESOLVED** | Chosen variant: `status: "ok"` + `reindex_failed: {error}` warning. Documented in workflow (line 96), step 8 narrative (lines 426–433), `IngestResult` warnings paragraph (line 409), Failure-modes table row (line 1470), AC v0.3.0 #9 (line 771). Explicit test case named. Coherent across all four touchpoints. |
| B3 | Unevaluable acceptance criteria | **RESOLVED** | (a) Wikipedia fixture AC at `https://en.wikipedia.org/wiki/Mamba_(deep_learning_architecture)` (lines 1662–1669) with counts (≥1 Source, ≥3 Entity, ≥2 Concept, ≥2 outbound relations each), evaluator (Jan on Mac Mini M4 + `anytype-llm-wiki-test` space), pass rule (single clean run). (b) 5-minute quick-start explicitly dropped from ACs and kept as aspirational prose (lines 1652–1654). |
| B4 | `wiki_contradictions` lint-checked but never populated | **RESOLVED (option b)** | Property marked "Schema-only in v0.3.0" on both Entity (line 253) and Concept (line 263). Lint check documented as **passive in v0.5.0** (line 591). New OQ #8 tracks v0.6.0 re-activation (line 1752). Consistent across four locations. |
| B5 | `normalize_title` correctness bug | **RESOLVED** | `_DASH_FOLDS` table (lines 1061–1070) includes U+2010, U+2011, U+2012, U+2013, U+2014, U+2212, U+FE63, U+FF0D. Pseudocode translates BEFORE casefold (line 1092 `dash_folded = nfc.translate(_DASH_FOLDS)` precedes line 1093 `casefolded = dash_folded.casefold()`). Docstring explicitly states "Folding happens BEFORE casefold." Parametrized dash-fold test table (lines 1100–1114) enumerates each codepoint. AC #6 (line 768) and Test Plan row (line 1708) reference the full table. Non-match case ("BGE - M3" vs "BGE-M3") explicit at line 1115 and asserted in tests. |
| B6 | `verify-anytype-writes.sh` data-loss foot-gun | **RESOLVED** | Script creates throwaway `__wiki_verify_probe__` type + `__verify-anytype-writes-probe-<timestamp>__` object, uses `trap cleanup EXIT INT TERM` (lines 1252–1267). `$ANYTYPE_OBJECT_ID` replaced by `$PROBE_OBJECT_ID` throughout; the two remaining mentions (lines 1272, 1293) are deliberate prose stating the variable is NOT consumed. v0.2.0 pre-release checklist (line 727) explicitly confirms probe artifacts are cleaned up. Appendix A preamble (line 1786) also states the self-cleaning lifecycle. |

### SHOULD-FIX
| ID | Finding | Resolution | Notes |
|----|---------|------------|-------|
| S1 | Unused `WIKI_UPSERT_THRESHOLD_TITLE` | **RESOLVED** | SequenceMatcher step 2 added at lines 1140–1149; env var now has a caller. |
| S2 | `similarity_score: 0.87` out of range | **RESOLVED** | Line 571: `similarity_score: 0.78`. |
| S3 | Missing `wiki_log_id` in QueryResult / LintReport | **RESOLVED** | Present in IngestResult (402–403), QueryResult (491–492), LintReport (577–578), BootstrapResult (329–330). |
| S4 | Workflow 2 step 7 opt-in vs opt-out wording | **RESOLVED** | Line 96: "default `WIKI_AUTO_REINDEX=true`; opt-out by exporting `WIKI_AUTO_REINDEX=false`". |
| S5 | Undefined extraction token budget | **RESOLVED** | `WIKI_EXTRACT_MAX_INPUT_TOKENS=8192` default (config table line 1396), head-only truncation with warning appended outside the source fence (lines 1174). |
| S6 | Empty-source extraction unspecified | **RESOLVED** | Dedicated behaviour in AC #8 (line 770), Failure-modes row (line 1478), plus `summary: "empty_source"` contract in the prompt (line 1221). |
| S7 | Read-only token scope error path missing | **RESOLVED** | AC v0.2.0 #9 (line 709) names `[CONFIG ERROR] insufficient_token_scope` with Settings → API pointer. |
| S8 | Query flowchart missing Qdrant-down branch | **RESOLVED** | Mermaid lines 457–458 show two edges: "Qdrant down + count below threshold" → Tier 1; "Qdrant down + count at/above threshold" → `[API ERROR] qdrant_unavailable`. |
| S9 | `domain_tags` re-bootstrap semantics | **RESOLVED** | Lines 302 (union-only stated, test in `test_bootstrap.py`), AC v0.2.0 #5 (line 705) names the `["a","b"]` → `["c"]` → `["a","b","c"]` fixture. |
| S10 | FilterExpression shape mismatch in pseudocode | **RESOLVED** | Comment block at lines 1128–1132 explicitly translates `{"type_key": type_key}` into the canonical `{"condition":"and","filters":[{"key":"type_key","condition":"eq","value":type_key}]}` shape via WikiClient.search. |
| S11 | `domain_hint` validation unspecified | **RESOLVED** | Lines 385: `[CONFIG ERROR] invalid_domain_hint` with the valid tag set and the remediation. |
| S12 | Canonical type_key keys + LintReport consistency | **RESOLVED** | Dedicated canonical type_key table at lines 228–237; `LintReport.object_counts` keys at lines 549–556 use `wiki_source`/`wiki_entity`/`wiki_concept`/`wiki_comparison`/`wiki_query`/`wiki_log` exactly. |
| S13 | FilterExpression fallback handwaved | **RESOLVED** | Line 513: warning emitted via `warnings` when pre-filter set >500 rows. |
| S14 | Two divergent Anytype HTTP clients | **RESOLVED** | `_BaseAnytypeClient` introduced in v0.2.0 scope (line 680), documented separately at lines 1022–1026 ("Divergent clients — base class (S14)"), both clients inherit, full merge consideration pushed to v0.4.0+ (no longer open-ended). |
| S15 | `ipaddress._BaseAddress` private type | **RESOLVED** | Line 1539: `AddressLike = ipaddress.IPv4Address \| ipaddress.IPv6Address`. |
| S16 | `wiki/` over-structured for v0.2.0 | **RESOLVED** | `locks.py` + `normalize.py` merged into `wiki/util.py` (line 683); `test_util.py` covers both. 7 v0.2.0 files instead of 8. |
| S17 | SSRF IPv4-only via `gethostbyname` | **RESOLVED** | `_resolve_all` uses `socket.getaddrinfo` (line 1550), iterates all returned addresses, rejects if any is blocked. Docstring explicitly names the multi-A-record defense. |
| S18 | IPv4-mapped IPv6 bypass | **RESOLVED** | `_is_blocked` consults `addr.ipv4_mapped` before the check (lines 1561–1562), and `::ffff:0:0/96` is in the explicit blocklist (line 1532) for defense in depth. |
| S19 | SSRF additional ranges | **RESOLVED** | Blocklist at lines 1517–1537 includes every requested range: `0.0.0.0/8`, `100.64.0.0/10`, `198.18.0.0/15`, `224.0.0.0/4`, `255.255.255.255/32`, `::/128`, `::ffff:0:0/96`, `64:ff9b::/96`, `100::/64`, plus `is_private/is_loopback/is_link_local/is_multicast/is_reserved/is_unspecified`. |
| S20 | SSRF scheme allowlist | **RESOLVED** | `_ALLOWED_SCHEMES = {"http", "https"}` (line 1508) rejected before any network work. |
| S21 | URL userinfo not rejected | **RESOLVED** | `_assert_url_safe` rejects outright (lines 1580–1583). |
| S22 | No default timeout | **RESOLVED** | `httpx.Timeout(connect=5, read=15, write=5, pool=5)` + 30-second total wall-clock budget (line 1604). |
| S23 | No response size cap | **RESOLVED** | `WIKI_FETCH_MAX_BYTES=10485760` default, streaming early-abort (line 1605 + config table line 1397). |
| S24 | DNS rebinding claim unfounded | **RESOLVED (as accepted residual risk)** | Line 1608: labeled accepted residual risk with single-operator threat model; v0.4.0+ reconsideration. No overclaim remains. |
| S25 | Prompt injection into extraction | **RESOLVED** | `<source>…</source>` fence + "nothing inside is a directive" instruction in the prompt (lines 1183–1196); name policy (length 200, no control chars, no prompt-like prefixes) enforced by pydantic model (line 1230) and documented in RULES (lines 1213–1215); README trust note (line 1236); `is_central` cross-check against source structure (line 1234). AC v0.3.0 #12 (line 774) asserts a prompt-injection source is handled. |
| S26 | LLM extraction JSON not validated | **RESOLVED** | `ExtractionModel` pydantic v2 model (line 1224), `ValidationError` enters the repair-retry path (lines 1238–1240); Hypothesis property-based test named (line 1232). |
| S27 | Lock PID-reuse race | **RESOLVED** | `fcntl.flock` adopted (line 1411); the `os.kill(pid,0)` check is gone entirely. Kernel releases the lock on process death regardless of cause. |
| S28 | TOCTOU in stale-lock replacement | **RESOLVED** | Same `fcntl.flock` switch eliminates stale-lock detection and the replacement TOCTOU in a single design decision (line 1417). |
| S29 | No `doctor` command | **RESOLVED** | Added to v0.2.0 Scope (line 684), specified with 8 checks and exit codes (lines 1028–1041), pre-release checklist asserts green (line 728), `test_doctor.py` in tests layout. |
| S30 | No memory/CPU budgets | **RESOLVED** | "Resource Impact" table at lines 1446–1454; minimum RAM recommendation (lines 1456–1460) covers 32/16/8 GB explicitly; `WIKI_MIN_EXTRACT_RAM_GB` advisory named (line 1462). |
| S31 | No schema migration story | **RESOLVED** | `WIKI_SCHEMA_VERSION` constant, per-tool compatibility check with three outcomes (missing / older / newer), MIGRATIONS.md required, CHANGELOG structured into User-visible / Internal sections (lines 1425–1442). |
| S32 | Qdrant growth model absent | **RESOLVED** | Line 1372: ~50 MB per 100 sources + `reindex_anytype --full` rebuild recipe. |
| S33 | No file-logging guidance | **RESOLVED** | Line 1364: file-logging recipe + `WIKI_LOG_LEVEL` env var + logrotate note. |
| S34 | CHANGELOG / MIGRATIONS story | **RESOLVED** | Covered by S31 block (lines 1436–1442). |
| S35 | Verification script CI runnability | **RESOLVED** | Line 1295: "maintainer-local ... do not wire it into `.github/workflows/`". |
| S36 | `wiki.status` deferral | **RESOLVED** | Concrete reconsideration trigger (≥3 community issues OR v0.4.0 pre-release user reports) documented at line 1774. |
| S37 | Test fixture mechanism unnamed | **RESOLVED** | Test plan line 1716: fixture constructed by `tests/wiki/test_query.py` calling `WikiClient.create_object` with respx mocks. |
| S38 | OQ#3 tension | **RESOLVED** | OQ #3 closed at line 1742 ("CLOSED at v0.3.0 specification"); config table marker aligned. |

### SUGGESTION (spot-checked)
| ID | Finding | Resolution | Notes |
|----|---------|------------|-------|
| G1 | `wiki_relations` vs `wiki_related` | **RESOLVED** | Line 250 adds the disambiguation comment. |
| G2 | `wiki/__init__.py` wording | **RESOLVED** | Line 915: "implementation functions; the MCP tool NAMES ... are registered in server.py". |
| G3 | `extraction_endpoint` logging hygiene | **RESOLVED** | Line 1351: "Query-string and userinfo are stripped before logging." |
| G5 | Appendix A write-test cleanup | **SUPERSEDED BY B6** | As fixer noted. |
| G6 | Type-level deeplink format | **RESOLVED** | Line 339: `anytype://type/{space_id}/{type_key}` convention with space-root fallback. |
| G7 | v0.3.0 performance budget | **RESOLVED** | Line 791: soft target `<2 min p95 for 10k-word source`, no hard SLO, revisit in v0.6.0. |
| G8 | "First Anytype-native" fallback line | **RESOLVED** | Line 177: fallback positioning one-liner ready for README swap. |
| G9 | `WIKI_LOG_LEVEL` | **RESOLVED** | Config table line 1398. |
| G11 | WikiLog append-only convention | **RESOLVED** | Line 282: explicit note that "append-only" is a convention and lint does not check. |
| G12 | `stale_stub` lint check | **RESOLVED** | Line 595: added to lint table at Medium severity. |
| G13 | markdownify rationale | **RESOLVED** | Line 415: one-sentence rationale for `markdownify` over `html2text`. |
| G14 | Delivery-phase dependency graph | **RESOLVED** | Mermaid flowchart at lines 667–674. |
| G15 | "First Anytype-native" claim on checklist | **RESOLVED** | Pre-release checklist line 729. |
| G16 | Privacy notice extensions | **RESOLVED** | Line 648 adds the off-localhost + embedding-inversion paragraph. |
| G17 | Lock permission mode | **RESOLVED** | Line 1414 / 1419: dir 0o700, file 0o600, explicit `os.chmod` pass. |
| G18 | Error message hygiene | **RESOLVED** | Line 1614: token strip + env-var placeholders + regression test. |
| G19 | Port allowlist | **RESOLVED** | `_ALLOWED_PORTS = {None, 80, 443, 8080, 8443}` (line 1512). |
| G20 | Markdown / bidi / control-char rejection | **RESOLVED** | Line 1615: regex enforced, U+202E test named. |
| G21 | Log-injection resistance test | **RESOLVED** | Line 1616: single-line JSON test with adversarial `\n[CRITICAL]` title. |
| G22 | Bandit CI | **RESOLVED** | Line 1627: `bandit -r src/` non-zero fails. |
| G23 | Lock CI job | **RESOLVED** | Line 1628: `uv lock --locked`. |
| G24 | gitleaks | **RESOLVED** | Line 1629: gitleaks in pre-commit + CI. |
| G25 | Hosted-LLM ack keyed by endpoint hash | **RESOLVED** | Line 1637: `extraction-endpoint-acknowledged-{sha256(endpoint)[:8]}`; re-prompts on endpoint change. |
| G26 | `--json` / `--human` lint modes | **RESOLVED** | Line 866: Must list. |
| G27 | `fcntl.flock` alternative | **RESOLVED (adopted)** | Subsumed into S27. |
| G28 | Log `extraction_endpoint` per ingest | **RESOLVED** | Line 1351: emitted on server boot AND every wiki_ingest start. |
| G29 | Anytype data-dir locations | **RESOLVED** | Line 1371: macOS + Linux paths documented. |
| G30 | `wiki_bootstrap --dry-run` | **RESOLVED** | Line 697: Should list. |
| G31 | `WIKI_MIN_EXTRACT_RAM_GB` | **RESOLVED** | Line 1462: doctor advisory check. |
| G32 | README troubleshooting from failure modes | **RESOLVED** | Line 1375: each row becomes an H3. |

(G4, G10 spot-checked via the fixer debrief; no regression indicators observed.)

## Invariant Verification

- [x] **No `anytype-rag` residuals: PASS** — `grep -c "anytype-rag\|anytype_rag"` returns `0`.
- [x] **`normalize_title` dash-folds U+2010/U+2011/U+2012/U+2013/U+2014/U+2212 BEFORE casefold: PASS** — lines 1061–1070 define `_DASH_FOLDS` with every required codepoint (plus U+FE63 and U+FF0D as bonuses); line 1092 applies the translate BEFORE line 1093 applies `casefold()`. Docstring at line 1079 explicitly documents the ordering.
- [x] **`BootstrapResult` schema defined with `wiki_log_id`: PASS** — lines 304–334.
- [x] **All tool result schemas carry WikiLog receipt (`wiki_log_id` + `wiki_log_deeplink`): PASS** — BootstrapResult (329–330), IngestResult (402–403), QueryResult (491–492), LintReport (577–578).
- [x] **`LintReport.object_counts` keys use canonical `wiki_*` values: PASS** — lines 549–556 list exactly `wiki_source`, `wiki_entity`, `wiki_concept`, `wiki_comparison`, `wiki_query`, `wiki_log`.
- [x] **SSRF uses `getaddrinfo`, not `gethostbyname`: PASS** — line 1550. Iterates every returned address (line 1551–1554). Normalizes IPv4-mapped IPv6 (lines 1561–1562). Rejects non-http/https (line 1578). Rejects URL userinfo (line 1580). Default timeouts + 30s total budget (line 1604). 10 MiB streamed size cap (line 1605). **All seven SSRF invariants hold.**
- [x] **Lock mechanism coherent (`fcntl.flock`): PASS** — lines 1411–1423. Kernel-held advisory lock, auto-release on process death, no stale-lock detection code, no PID-reuse race, no TOCTOU in stale-lock replace. Non-NFS constraint documented with recommended override. (Minor nit: line 1480's failure-modes row still has a conditional reference to `O_CREAT|O_EXCL` which is no longer the chosen design; see "Remaining Findings" below.)
- [x] **Verify script uses throwaway object with `trap` cleanup: PASS** — lines 1252–1267 (`trap cleanup EXIT INT TERM`), probe type `__wiki_verify_probe__` + probe object `__verify-anytype-writes-probe-<timestamp>__`, two remaining `$ANYTYPE_OBJECT_ID` mentions are deliberate negation prose (lines 1272, 1293).
- [x] **Failure-modes table covers reindex failure, Ollama model missing, corrupted patch-decision, empty source, disk full, SIGKILL mid-lock-write: PASS** — reindex failure row at line 1470; Ollama model not pulled row at line 1482 and AC v0.3.0 #11 (line 773); corrupted `patch-decision.md` row at line 1481; empty source row at line 1478; disk full / ENOSPC row at line 1479; SIGKILL mid-lock row at line 1480.

## Regressions

**None.** Confirmed preserved from round 1's "What's Done Well":

- Per-version Scope/MoSCoW/AC/Deliverables structure intact across v0.2.0–v0.5.0.
- Single-canonical-path discipline for PATCH body and FilterExpression preserved; `patch-decision.md` still the arbiter.
- Four Mermaid diagrams (delivery-phase dep graph + ingest + query + lint) — fixer confirmed none use `<` / `>` / `=` in edge labels; I eyeballed the Qdrant-unavailable edges on lines 457–458 and they are safe.
- Boundary test at 199/200/201 preserved (AC v0.4.0 #3, Test Plan line 1716).
- Contributor's Map + Open Questions + Deferred Items all retained and extended (new OQ #8 for contradictions, new `(tracked: #NNN)` convention for follow-ups).
- Failure-modes table for all tools retained and extended.
- Error-category taxonomy (`api_error` / `data_error` / `config_error`) retained.
- Codebase-verified integration claims (`type_key`, `fastmcp`, WikiClient) retained and not contradicted.

## Remaining Findings

### BLOCKING

_None._

### SHOULD-FIX

_None._

### SUGGESTION

**R2-SG1 — Minor coherence nit in the SIGKILL failure-modes row.**
Line 1480 reads: "... If an `O_CREAT\|O_EXCL` file-existence lock is retained for an edge case, an empty or unparseable payload is treated as **stale** and the lock is re-acquired." But the lock design (line 1411) commits to `fcntl.flock` exclusively — there is no edge case where `O_CREAT|O_EXCL` is retained. The conditional is vestigial language from an earlier draft. Recommend striking the second sentence of that row or rewriting it to simply say "an empty or unparseable payload on next ingest is overwritten without special handling; the `fcntl.flock` release handled serialization." Non-blocking; the primary lock policy is coherent everywhere else.

**R2-SG2 — Lint check enum count footnote.**
v0.5.0 MoSCoW line 866 says "8 checks" but the `check` enum in `LintReport` (line 560) lists 9 values (orphan, stale, contradiction_unresolved, oversized, empty_type, asymmetric_relation, potential_duplicate, stale_stub, pipeline_orphan). The fixer debrief acknowledges this — `contradiction_unresolved` is counted as a check but is passive in v0.5.0. A one-line parenthetical in the MoSCoW ("8 active checks + 1 passive `contradiction_unresolved`") would remove the confusion. Non-blocking.

**R2-SG3 — Anchor slugification risk.**
Several cross-refs use em-dash-bearing anchors (e.g. `#divergent-clients--base-class-s14`) which renderers slugify inconsistently. Not load-bearing — prose context makes targets self-explaining — but a minor-pass normalization to simple hyphens would make the spec robust against any renderer change. The fixer flagged this as a known concern; I confirm it and recommend a follow-up housekeeping pass rather than blocking on it.

## Verdict Recap

Every round-1 BLOCKING and SHOULD-FIX finding is resolved; SUGGESTION findings are resolved to the extent spot-checked. Three minor new SUGGESTIONs arose from this review (a vestigial conditional in the failure-modes SIGKILL row, a check-count mismatch between MoSCoW wording and LintReport enum, and em-dash anchor slugification), none of which blocks implementation. Invariant checks all PASS. **APPROVED for advancement to implementation.**
