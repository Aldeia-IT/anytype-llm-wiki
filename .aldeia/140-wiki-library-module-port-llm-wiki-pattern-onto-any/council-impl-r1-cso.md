# Post-Implementation Council — CSO Assessment (R1)

**Ticket:** Aldeia-IT/aldeia-box#140 — Wiki Library Module (v0.2.0 tranche)
**Branch:** `aldeia/wiki-library-module-port-llm-wiki-pattern-onto-any`
**Reviewer:** Chief Security Officer (strategic security posture — not line-by-line)
**Date:** 2026-05-22
**HEAD reviewed:** `02b6470`

---

## Verdict: **SIGN OFF WITH ADVISORIES**

Advance to `done` (open PR → merge to `main`). The deferred OSS-hygiene/security
items (SECURITY.md, `.bandit`, supply-chain README section, CI security gates,
`patch-decision.md`) are **tag-gating, not merge-gating**, and are correctly
filed by the spec under the v0.2.0 pre-release checklist. No finding rises to
BLOCKING for the merge.

---

## Summary

This is a governance gate, not a code re-review. The impl-phase technical review
(`impl-review-r1.md`) already ran an independent security/correctness pass that
caught one MAJOR (doctor URL credential leak) and three SHOULD-FIX items, all
fixed in commits `3ebfd16` / `f95a11f` / `02b6470`. My job is to decide whether
the **strategic security posture** of the deliverable is sound enough to land on
`main`, and to spot-check that the credential-scrubbing fix is genuinely resolved.

The central distinction the brief asks me to reason about — **merge-to-main ≠
`git tag v0.2.0` ≠ PyPI publish** — is dispositive. The spec itself draws this
line: every missing security artifact (SECURITY.md, `.bandit`, supply-chain
posture prose, `pip-audit`/`bandit`/`gitleaks`/license-scan CI gates,
`patch-decision.md`) is enumerated under **"Pre-release checklist (v0.2.0)"** at
`spec.md:760-793`, each as an unchecked `[ ]` box. These are release-cut
artifacts by the spec's own design, not preconditions for code existing on the
default branch. The repo is **already public**; merging this code changes the
default-branch tree but does not cut a release, publish a package, or make any
new security claim to the world.

The v0.2.0 attack surface is minimal and argues for low merge risk: **no network
ingest, no LLM call-path, no URL fetching** (all v0.3.0+). The only runtime I/O
is (a) HTTP to a localhost Anytype API and (b) a local advisory file lock under
`WIKI_LOCK_DIR`. There is no new internet-facing trust boundary in this tranche.

The one genuinely security-relevant defect that *was* merge-relevant — the
doctor leaking raw credential-bearing URLs to operator stdout / `--json` — was
the impl review's MAJOR-1 and is fixed. I independently confirmed it (below).

---

## Spot-checks performed (what I actually verified)

**1. MAJOR-1 — doctor URL credential leak — RESOLVED.**
`src/anytype_llm_wiki/wiki/doctor.py`: every URL interpolated into a check
`message` now passes through `util.scrub_credentials(url)`:
- `doctor.py:61,72,76` (anytype_reachable) — `safe_url` used in all three branches.
- `doctor.py:108,118,122` (qdrant_reachable) — `safe_url` in all branches.
- `doctor.py:157,161,163,168` (`_ollama_tags`) — `safe_url` in reachable/error/HTTP branches.
The raw `url` is used **only** as the actual HTTP target (`_http_get(f"{url}/...")`,
e.g. `:63,:110,:159`), never in an emitted string. The `qdrant_collection` check
(`:126-151`) interpolates the collection **name** (`{collection!r}`), not a URL —
not a credential. `run_doctor()` (`:352-385`) builds the `--json` report from the
same scrubbed check dicts, so the JSON path inherits the scrub. **Confirmed: no
residual raw-URL leak in stdout or `--json`.**

**2. SHOULD-FIX-1 — scheme-less userinfo scrubbing — RESOLVED.**
`src/anytype_llm_wiki/wiki/util.py:64-107`. `scrub_credentials` now handles the
scheme-less / authority-in-path case explicitly (`:84-91`): when `"://"` is
absent and an `@` appears before the first `/`, it strips the leading
`userinfo@` and re-scrubs with a `//` placeholder so the schemed/netloc path
also drops the query/fragment. The schemed path (`:93-107`) strips userinfo via
`netloc.rsplit("@", 1)[1]` and drops `query`/`fragment` via `urlunparse`. This is
the actual credential-scrubbing **primitive** behind AC #15, and it is now robust
to the `user:pass@host/path` shape that previously survived. Non-string input
falls back to `str(url)` (`:70-71`); parse failure falls back to the raw input
(`:74-75`) — acceptable for a best-effort log-scrubber.

**3. AC #15 (the load-bearing scrubbing AC) primitive is sound.**
`spec.md:745` requires that a forced `[API ERROR]` with
`QDRANT_URL=...?api_key=SEKRET123` contains neither the secret nor the raw query,
and that `WIKI_EXTRACT_ENDPOINT` userinfo (`api-user:api-secret@`) is absent. The
v0.2.0 surface has no Qdrant/extraction call-path yet (v0.3.0), so this is
unit-tested at the primitive level (`TestCredentialScrubbing`, per the test
council) and the end-to-end assertion is correctly carried to v0.3.0 (addendum
item #10). The primitive I verified above satisfies both shapes. **Adequate for
v0.2.0 scope.**

**4. Lock-path traversal hardening (SHOULD-FIX-2) — RESOLVED, defense-in-depth.**
`util.py:138-141`: `space_id` is sanitized to `[A-Za-z0-9._-]` (others → `_`)
before being joined into the lock filename, with a sha256 fallback for an
all-separator id. This closes the `../` / `a/b` traversal-write vector flagged in
the impl review. Lock dir is `0o700`, lock file `0o600`, both set via explicit
`os.chmod` to defeat umask (`:128-130,:142-143`).

**5. Bootstrap error paths do not leak credentials.**
`bootstrap.py`: `_api_error` (`:105-118`) interpolates only `type(exc).__name__`,
never the URL or token; `_config_error_*` (`:121-147`) interpolate only
`space_id` and static guidance. Other-HTTP-status path (`:178-187`) interpolates
only the status code. No bearer token or URL reaches an error string.

**6. No hardcoded secrets in source.**
Grep across `src/` for `api_key|password|secret|token|Bearer`: every match is an
env-var read (`os.environ.get("ANYTYPE_API_KEY", "")`, `config.QDRANT_API_KEY`,
etc.) or a literal-empty default (`_DEFAULT_API_KEY = ""`). Bearer header is
constructed from the resolved env key (`_base_client.py:56`). A tree-wide
secret-pattern scan surfaced only test placeholders (`"test-doctor-key"`,
`"test-bearer-token"`, etc.) — **a `gitleaks` gate would pass clean today.**

**7. Deferred verify-script bearer-token-via-`-H` — agree with the deferral.**
`scripts/verify-anytype-writes.sh:65` builds
`auth_header="Authorization: Bearer $ANYTYPE_API_KEY"` for `curl -H`, briefly
visible in `ps`. The impl review deferred this with sound rationale: the script
is maintainer-local by design (single-user Mac Mini, never CI/shared host),
matches the spec-authored script verbatim, and stdin/`--config` hardening adds
bug surface to a one-shot probe. **Concur — not merge-blocking; tracked for
v0.3.0+.**

**8. Confirmed-absent tag-time artifacts.**
Glob confirms `SECURITY.md`, `.bandit`, `NOTICE`, `CHANGELOG.md`, and
`.github/workflows/` are **all absent** (only `CONTRIBUTING.md` exists). The
supply-chain-posture README section and `patch-decision.md` are likewise not yet
present. This matches the impl lead's honest pre-release-checklist state in the
phase summary.

---

## Findings

### BLOCKING

_None._

The doctor credential-leak (the only merge-relevant security defect surfaced in
this work) is resolved and independently confirmed. The v0.2.0 attack surface
introduces no new internet-facing trust boundary.

### ADVISORY

**A-CSO-1 — SECURITY.md is TAG-gating, but the CRA Art. 14 clock is short.**
*Risk: low (merge) / moderate (tag-timing).* SECURITY.md is missing. It is a
release artifact (`spec.md:776`, pre-release checklist), so it does **not** block
merge. However, EU Regulation 2024/2847 (CRA) Art. 14 takes effect **2026-06-11**
— ~3 weeks out — and the spec names it as the reason to begin posture work now.
**Recommended action:** Jan must land SECURITY.md (vuln-reporting channel +
72h/14-day response expectation + CRA paragraph) **before `git tag v0.2.0`**, and
should not let the tag slip past the CRA effective date without it. Cross-checked
with Legal (SECURITY.md/CRA is Legal's domain — message sent).

**A-CSO-2 — `.bandit` baseline + `bandit -r src/` CI gate are TAG-gating.**
*Risk: low at v0.2.0.* The `.bandit` baseline (`spec.md:779`) is, by the spec's
own note, "most meaningful once the v0.3.0 SSRF layer exists" — v0.2.0 has no
fetch layer, no `getaddrinfo`, no manual-redirect handling to baseline. **Not
merge-gating and arguably not even v0.2.0-tag-critical**; the substantive value
arrives with v0.3.0. **Recommended action:** add a minimal `bandit -r src/` CI
gate at v0.2.0 tag for drive-by-PR protection; defer the rationale-annotated
SSRF baseline to v0.3.0. Cross-checked with Infra (CI gates are Infra's domain).

**A-CSO-3 — Supply-chain posture (README/SECURITY.md section + pinning + CI
license-scan) is TAG-gating.** *Risk: low.* The two-layer pinning explanation
(`spec.md:780`) and the `pip-audit`/license-scan CI gates (`:774,:785`) are
absent. None block merge. The runtime dependency set is small and well-known
(httpx, fastmcp, qdrant-client, psutil); I see no acute CVE/supply-chain
exposure that would force a pre-merge gate. **Recommended action:** land the
supply-chain README section + `pip-audit` + license-scan CI before tag.

**A-CSO-4 — `patch-decision.md` absent; doctor version-drift / patch-decision
checks degrade to OK-skipped.** *Risk: low, by design.* `util.read_patch_decision`
(`util.py:195-234`) returns `None` when the file is missing, and both
`_check_anytype_version_drift` (`doctor.py:80-103`) and `_check_patch_decision_md`
(`:254-267`) treat absence as a benign `OK — skipped (v0.2.0)`. This is the
intended v0.2.0 posture (the file is produced by the live verify-script run at
tag time, `spec.md:763`). **Not merge-gating.** Worth noting only so the council
records that two doctor checks are intentionally inert until the maintainer runs
the live verification at tag time — the security signal they will eventually
carry (API-version pinning continuity) is **deferred, not lost.**

**A-CSO-5 — Pattern note: a cluster of deferred security artifacts is acceptable
*here* only because the surface is inert.** *Risk: informational.* Normally a
pile of missing SECURITY.md / CI-gate / baseline items would read as a systemic
posture gap worth blocking on. It does **not** here because (a) the spec
pre-authored every one of them as tag-time items with explicit rationale, (b) the
v0.2.0 runtime surface is localhost-only with no ingest/LLM/fetch, and (c) the
impl lead's phase summary enumerates each deferred item honestly with its gating
state (addendum item #9 satisfied). **The deferral is disciplined, not
neglectful.** I am flagging it so the council does not let the *same* list slip
silently past `git tag v0.2.0` — at tag time this advisory cluster converts to a
hard gate.

---

## Merge-gating vs. tag-gating — explicit ledger

| Deferred item | Merge-gating? | Tag-gating? | Notes |
|---|---|---|---|
| Doctor URL scrub (MAJOR-1) | **was the only merge concern** | n/a | **FIXED + confirmed** |
| `SECURITY.md` | No | **Yes** | Legal domain; CRA 2026-06-11 clock (A-CSO-1) |
| `.bandit` baseline | No | Soft (v0.3.0 is real value) | A-CSO-2 |
| Supply-chain README section | No | **Yes** | A-CSO-3 |
| `pip-audit` CI gate | No | **Yes** | Infra domain |
| `bandit -r src/` CI gate | No | **Yes** | Infra domain |
| `gitleaks` CI gate | No | **Yes** | Tree is clean today (verified) |
| license-scan CI gate | No | **Yes** | Legal + Infra |
| `patch-decision.md` | No | **Yes** (live verify) | A-CSO-4; doctor degrades gracefully |
| verify-script `-H` bearer token | No | No | Maintainer-local; v0.3.0+ hardening |

Every currently-missing security artifact lands in the right-hand column. **None
is in the merge column.**

---

## Recommendation

**Target phase: `done`** (approve PR → merge to `main`).

**Rationale:** The only merge-relevant security defect (doctor credential leak)
is fixed and I confirmed it at file:line. The credential-scrubbing primitive is
robust to both the query-string and the scheme-less-userinfo shapes. There are no
hardcoded secrets and a gitleaks gate would pass today. The v0.2.0 attack surface
is localhost-only with no ingest/LLM/fetch trust boundary. Every deferred
security artifact is, by the spec's own structure, a **v0.2.0 pre-release /
tag-time** item — appropriate to land between merge and `git tag v0.2.0`, not
before code reaches `main` on an already-public repo.

**Hard condition on the v0.2.0 tag (not the merge):** the advisory cluster
(A-CSO-1 through A-CSO-3) MUST be cleared before `git tag v0.2.0`, and SECURITY.md
in particular should not slip past the CRA Art. 14 effective date (2026-06-11).
The council chair should record this as a tag-gate, and the maintainer should
walk the `spec.md:760-793` checklist at tag time.

**Cross-thread:** SECURITY.md / NOTICE / CRA / license-scan compatibility →
flagged to **legal**. `pip-audit` / `bandit` / `gitleaks` / license-scan CI gates
and doctor-scrub confirmation → flagged to **infra**. Verdicts to be reconciled
on the merge-vs-tag distinction; this assessment will be updated if either
domain owner identifies a merge-gating concern I have not.

---

## Sign-off

**As Chief Security Officer, I SIGN OFF (with advisories) on merging this v0.2.0
code to `main`.** The strategic security posture of the deliverable is sound for
the merge: the one merge-relevant defect is resolved, the attack surface is
inert, and the deferred security artifacts are legitimately tag-gating. I do
**not** sign off on cutting the `git tag v0.2.0` release until the A-CSO-1/2/3
advisory cluster (SECURITY.md, supply-chain posture, CI security gates) is
landed, with SECURITY.md prioritized against the 2026-06-11 CRA deadline.
