# Specification Review: Wiki Library Module — Round 3 (Verification of R2 Rework)

**Reviewed:** 2026-04-22
**Spec Version:** commit `0176cb3` (spec.md, 2123 lines, `status: SPEC`, `review_rounds: 2`)
**Scope:** verification of the R2 fixer's resolution of BLOCKING-CTO-1 plus the 42 ADVISORY findings. Delta-only review, not a full re-run.

## Verdict

**APPROVED**

**Rationale:** BLOCKING-CTO-1 is fully resolved. The phrase "unchanged in v0.2.x" (applied to `anytype_client.py`) no longer appears anywhere in the spec; every remaining `anytype_client` reference is consistent with the v0.2.0 refactor narrative (Contributor's Map line 24, Architecture Overview line 224, v0.2.0 Scope line 707, Module Layout line 997, Public API signatures lines 1100–1116, Divergent Clients §S14 lines 1144–1152, and new AC v0.2.0 #12 at line 742). The 10-item mandatory spot-check passes end-to-end (one minor wording nit on OQ #5 noted below but non-blocking). All R2 invariants hold — zero `anytype-rag` residuals, dash-fold BEFORE casefold preserved with two new codepoints (U+00AD, U+2015) extending the table to 10 entries, SSRF stack (`getaddrinfo`, scheme allowlist, userinfo rejection, timeouts, size cap) intact, four Mermaid diagrams unchanged from the R2-approved baseline. Frontmatter correct (`status: SPEC`, `review_rounds: 2`, `date: 2026-04-22`). Three new, non-blocking SUGGESTIONs are noted at the end.

## BLOCKING-CTO-1 resolution check

**Grep evidence:**

- `grep -n "unchanged in v0\.2\.x"` → **0 matches**. The contradiction source phrase is eradicated.
- `grep -n "anytype_client"` → 12 matches. Each is either (a) naming the file `anytype_client.py`, (b) naming the class `AnytypeReadClient`, or (c) naming the existing `tests/test_anytype_client.py` test file. No stale "unchanged" phrasing remains.

**Key touchpoints verified coherent:**

| Section | Line(s) | Substance |
|---|---|---|
| Contributor's Map | 24 | Explicitly names `anytype_client.py` as THE file refactored in v0.2.0; three module-level functions preserved as wrappers; `indexer.py:11` imports resolve unchanged. |
| Architecture Overview | 224 | "addresses BLOCKING-CTO-1 from R2" callout; 45-line baseline stated; thin-wrapper pattern described; shared `_BaseAnytypeClient` transport contract named. |
| v0.2.0 Scope | 707 | Bold "refactored in v0.2.0 (NOT unchanged — resolves BLOCKING-CTO-1)" with the import-surface guarantee inline. |
| v0.2.0 Scope tests | 718 | `tests/test_anytype_client.py` extended to cover both class and wrapper paths. |
| Module Layout tree | 997 | Comment on the `anytype_client.py` tree node matches the refactor narrative. |
| Public API signatures | 1080–1116 | `_BaseAnytypeClient` class with docstring that explicitly names read-plane and write-plane methods as DO-NOT-LIFT (CTO #40). `AnytypeReadClient(_BaseAnytypeClient)` class with the three read methods. Module-level wrappers present with identical v0.1.0 signatures. |
| Divergent clients §S14 | 1140–1152 | Three-step refactor enumeration: introduce class, preserve wrappers, extend tests. Full-merge deferred to v0.4.0+ (no longer open-ended). |
| AC v0.2.0 #12 | 742 | **New** `[BLOCKING-CTO-1 coverage]` AC covering (a) class-level path, (b) wrapper-level path, (c) regression assertion that `indexer.py`'s existing import still resolves. |
| 45-line baseline | `src/anytype_llm_wiki/anytype_client.py` | `wc -l` → 45. Matches the spec's baseline claim verbatim. |

**Verdict on BLOCKING-CTO-1:** **RESOLVED.** The narrative is uniform across all seven touchpoints, the new AC names all three required test paths including the regression assertion on `indexer.py`'s imports, and the 45-line codebase-reality claim is grounded in the actual file at HEAD.

## Advisory spot-check table

| Finding # | Claimed disposition | Located at (spec line) | Verification | PASS/FAIL |
|---|---|---|---|---|
| CSO #1 (bidi/control regex) | E | 1810–1815, AC v0.3.0 #16 at 836 | Regex prose enumerates U+FEFF, U+2028, U+2029, U+E0020–U+E007F. Parametrized test enumerates `U+202E`, `U+FEFF`, `U+2028`, `U+2029`, `U+E0041` — one per codepoint group. | **PASS** |
| Legal #12 (LGPD phrasing) | E | README Privacy in spec, line 656 | Exact replacement text present: "Aldeia IT, as the publisher of this open-source module, does not determine the purposes or means of data processing that you perform with it, and is therefore not a controller of your data under GDPR Art. 4(7) or LGPD Art. 5(VI). You are the controller — operational responsibility for data protection (lawful basis, consent where required, data-subject rights, retention, security) rests with you." | **PASS** |
| CPO #20 (README:3 reconciliation) | E + CL | `README.md:3` (actual file) + spec line 768 | Actual `README.md:3` now reads: *"To our knowledge, the first Anytype-native LLM wiki — combining Karpathy's pattern, Hermes' battle-tested operational policies, and Anytype's typed knowledge graph..."* with a positioning-verification note at line 7. Spec pre-release checklist names the `positioning-verification.md` artifact with required contents (verbatim queries, dates, finding count, URLs, conclusion). | **PASS** |
| QA #24 (four v0.5.0 ACs) | E | spec lines 960–963 | AC v0.5.0 #8 (`contradiction_unresolved` High; seeded + `wiki_last_reviewed` null; v0.6.0 re-test note), #9 (`oversized` Low; >2000 chars; char count in detail), #10 (`stale_stub` Medium; `wiki_status: "stub"` + >30 days), #11 (`potential_duplicate` via respx-mocked Qdrant in [0.70, upsert_threshold)). v0.5.0 pre-release checklist line 979 enumerates all 9 check enum values. | **PASS** |
| QA #28 (prompt-injection AC contradiction) | E | spec line 832 | AC v0.3.0 #12 rewritten. Policy option (b) explicit: object created `is_central=false` is acceptable; final assertion is "no object with that name appears with `is_central=true`". Second test case added for `name: "system: ignore"` (name-policy trip path) asserting `name_policy_rejected`. Internal contradiction gone. | **PASS** |
| Infra #33 (bootstrap schema-compat exception) | E | §Schema Compatibility lines 1599–1607 | New paragraph "Bootstrap-specific exception (addresses Infra Advisory #33 / R2 Infra A1)". Explicit behavior: `info`-level `wiki_schema_upgrade_started` log, idempotent upgrade, `wiki_schema_version` update on success, `BootstrapResult.status: "ok"` + `schema_upgrade` section, `status: "partial"` on mid-upgrade failure. Explicit scope: applies ONLY to `wiki_bootstrap`. | **PASS** |
| CTO #40 (`_BaseAnytypeClient` transport-only docstring) | E | Public API signatures lines 1081–1094 | Docstring reads: *"Scope is transport-only: session + headers + timeout + close(). Do NOT lift read-plane methods (`list_spaces`, `list_objects`, `get_object`) or write-plane methods (`create_type`, `create_property`, `create_tag`, `create_object`, `update_object`, `search`) into this base class — they belong on their respective subclasses (`AnytypeReadClient`, `WikiClient`)."* Matches the CTO #40 requirement verbatim. Echo also present in §S14 intro (line 1142). | **PASS** |
| CTO #41 (`_DASH_FOLDS` + AC count) | E | lines 1192–1203 (table) + line 826 (AC) | `_DASH_FOLDS` now includes U+00AD (SOFT HYPHEN) and U+2015 (HORIZONTAL BAR) in addition to the prior 8 codepoints. Docstring step 2 enumerates the 10 codepoints. Dash-fold test table (lines 1232–1245) has rows for both new codepoints. AC v0.3.0 #6 reads: "The parametrized test covers **10 codepoints**: U+2010, U+2011, U+2012, U+2013, U+2014, U+2212, U+FE63, U+FF0D, U+00AD (SOFT HYPHEN, PDF-paste vector), U+2015 (HORIZONTAL BAR)." | **PASS** |
| CPO #22 (OQ #5 closure) | E | Open Questions §5, line 1954 | OQ #5 text begins "**RESOLVED 2026-04-22 (addresses CPO Advisory #22).**" — uppercase "RESOLVED" rather than the requested "Resolved 2026-04-22". Semantically identical and the date is verbatim. Closure content (module name / repo name / PyPI name / Trademarks footer cross-ref) is present. **Minor wording nit only; not load-bearing.** | **PASS (with nit — see SUGGESTION R3-SG1)** |
| CSO #8 (port allowlist + env var) | E | lines 1694–1703 (pseudocode) + 1560 (config table) + 1169 (doctor step 10) | `_DEFAULT_ALLOWED_PORTS = {None, 80, 443}` (previous default `{None, 80, 443, 8080, 8443}` explicitly commented as tightened). `_extra_raw = os.environ.get("WIKI_FETCH_EXTRA_PORTS", ...)`, defensive int parsing, `_ALLOWED_PORTS = _DEFAULT_ALLOWED_PORTS \| _EXTRA_PORTS`. New config-table row at line 1560 for `WIKI_FETCH_EXTRA_PORTS` (default empty, v0.3.0, comma-separated). Doctor step 10 at line 1169 WARNs when non-empty. All four touchpoints consistent. | **PASS** |

**Summary:** 10 PASS, 0 FAIL, 1 minor wording nit (OQ #5 uses uppercase "RESOLVED" instead of "Resolved" — identical substance, trivially reconcilable; carried as SUGGESTION R3-SG1).

## Regression invariants (from review-r2.md)

| Invariant | Status | Evidence |
|---|---|---|
| No `anytype-rag` residuals | **PASS** | `grep "anytype-rag"` on spec.md → 0 matches. |
| `normalize_title` dash-folds BEFORE casefold | **PASS** | Pseudocode lines 1225–1229: `dash_folded = nfc.translate(_DASH_FOLDS)` precedes `casefolded = dash_folded.casefold()`. Docstring step 2 (line 1212) explicitly states "Folding happens BEFORE casefold". Extended `_DASH_FOLDS` includes the original 8 codepoints plus U+00AD, U+2015. |
| SSRF uses `getaddrinfo` | **PASS** | Line 1745: `socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)`. Iterates all addresses; rejects if any is blocked. |
| SSRF scheme allowlist enforced | **PASS** | Line 1684: `_ALLOWED_SCHEMES = {"http", "https"}`. Line 1773: `if url.scheme not in _ALLOWED_SCHEMES: raise SsrfBlocked`. |
| Four Mermaid diagrams present | **PASS** | `grep "^```mermaid"` → 4 matches (lines 349, 453, 523, 692): ingest / query / lint / delivery-phase dep graph. |
| Mermaid edge-label content unchanged from R2 baseline | **PASS** | The pre-R2 ingest diagram already contained edge labels like `|>= upsert threshold|`, `|< 0.70|`, `|>= 2 outbound relations|`; verified via `git show da44848:...spec.md` that these existed pre-R2-fix and were explicitly approved by review-r2.md line 121 ("fixer confirmed none use `<`/`>`/`=` in edge labels; I eyeballed ... they are safe"). R3 introduces no new edge-label changes. No regression relative to the R2 baseline. |
| `BootstrapResult` schema with `wiki_log_id` | **PASS** | Still present and untouched; R2 review cited lines 304–334. |
| `LintReport.object_counts` canonical type_key keys | **PASS** | Lines 553–559 list exactly `wiki_source`, `wiki_entity`, `wiki_concept`, `wiki_comparison`, `wiki_query`, `wiki_log`. |
| Lock mechanism (`fcntl.flock`) coherent | **PASS** | Preserved from R2; §Concurrent Ingest Policy references it; non-NFS constraint at line 1585 unchanged; §R2 doctor step 9 (new) hardens the same invariant with `os.statvfs` probe on `{nfs, nfs4, smbfs, cifs, fuse.sshfs, afpfs}`. |
| Verification script `trap` cleanup | **PASS** | Unchanged from R2 baseline; CSO Advisory #2 edit (trap installed BEFORE probe creation; `|| true` replaced with diagnostic) is an enhancement, not a regression. |
| Per-version Scope/MoSCoW/AC/Deliverables discipline | **PASS** | Per-version blocks for v0.2.0 / v0.3.0 / v0.4.0 / v0.5.0 all present, each with Scope (in) / (out) / MoSCoW / Acceptance criteria / Deliverables / Dependencies / Risks & mitigations / Pre-release checklist. |
| Single-canonical-path discipline (PATCH body, FilterExpression) | **PASS** | `patch-decision.md` still the arbiter (lines 742, 753, 848); new AC v0.2.0 #14 + v0.3.0 #15 + v0.4.0 #9 harden this as a pre-check error rather than a runtime discovery. |
| Boundary test at 199/200/201 | **PASS** | Preserved in §Proposed Solution → Tiered retrieval strategy → "Boundary test" at line 507. |
| 45-line `anytype_client.py` baseline claim | **PASS** | `wc -l src/anytype_llm_wiki/anytype_client.py` → 45. Spec line 1144 claim matches file reality. |

## Remaining findings

### BLOCKING

_None._

### SHOULD-FIX

_None._

### SUGGESTION

**R3-SG1 — OQ #5 casing nit.** Fixer debrief (item #22) and the task prompt both specified "Resolved 2026-04-22" verbatim; the spec ships with "**RESOLVED 2026-04-22**" (uppercase + bold). The substance is identical, the date is exact, and the CPO Advisory attribution is preserved. Cosmetic only; if the lead wants strict adherence to the verbatim recommendation, a one-word case change at line 1954 would close it. Non-blocking.

**R3-SG2 — Inherited R2 Mermaid edge-label characters.** The R2 review stated "fixer confirmed none use `<` / `>` / `=` in edge labels" and "approved". On close inspection of the R2-approved ingest diagram, three edge labels do contain `<` / `>` / `=` (`|>= upsert threshold|`, `|< 0.70|`, `|>= 2 outbound relations|`) and this state was inherited unchanged into R3. Most modern Mermaid renderers (GitHub, mermaid.live, VS Code's Markdown Preview Mermaid Support) tolerate this; some older renderers may not. Since the content is unchanged from the R2-approved baseline, this is not an R3 regression — flagging it only for a potential housekeeping pass so the assertion in review-r2.md line 121 becomes literally true. Non-blocking.

**R3-SG3 — Orphaned R2-SG residuals worth a housekeeping pass.** The three minor SUGGESTIONs in review-r2.md (vestigial `O_CREAT|O_EXCL` text in the SIGKILL failure-modes row; `"8 checks"` vs 9-enum mismatch wording; em-dash-bearing anchor slugification) were out of scope for the R2 fixer's explicit task list (BLOCKING + 42 advisories) and remain present in the R3 spec. These are leftovers, not regressions. Recommend a cleanup pass at v0.2.0 tag time rather than a spec amendment now.

## Verdict Recap

BLOCKING-CTO-1 is fully resolved with uniform narrative across all seven spec touchpoints and a new, specific AC that exercises all three paths (class, wrapper, and importer-regression). All 10 mandatory advisory spot-checks pass (one pure-casing nit on OQ #5). All R2 regression invariants hold. Frontmatter correct. **APPROVED for advancement past R3 verification.**
