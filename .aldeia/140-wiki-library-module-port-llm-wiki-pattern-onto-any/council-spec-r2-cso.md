# CSO Assessment — Post-spec Council R2 (Calibration)

**Reviewer:** chief-security-officer (real agent, R2 calibration)
**Date:** 2026-04-22
**Ticket:** #140 — Wiki Library Module
**Spec under review:** `.aldeia/140-wiki-library-module-port-llm-wiki-pattern-onto-any/spec.md` @ commit `da44848`, 1912 lines, `status: SPEC`.
**Scope:** strategic / governance-level security review, probing specifically for correctness defects in security-load-bearing code that a synthesis-level R1 reviewer might have missed.

---

## Verdict

**SIGN OFF WITH CONDITIONS**

---

## Summary

The security architecture is coherent, defensively layered, and — where it matters most (SSRF, prompt injection, concurrent-ingest lock) — correct on the merits. Every security-critical algorithm I audited holds up under scrutiny: `getaddrinfo` + multi-address iteration, IPv4-mapped-IPv6 normalization, the `is_ipv4_mapped is not None` guard, the defense-in-depth blocklist that catches CGNAT and AWS/GCP IMDS (169.254.169.254 via both the explicit `/16` entry and `is_link_local`), `fcntl.flock` with `O_CREAT|O_RDWR` (no TOCTOU between open and lock — the kernel attaches the lock to the open fd), and the three-layer prompt-injection defense (fence + pydantic policy + `is_central` corroboration against source structure). That last item — the `is_central` cross-check — is genuinely the strongest single line in the spec; treating the extractor's output as untrusted and requiring corroboration is the right instinct.

That said, I surface **two new ADVISORY items the R1 CSO missed** (neither blocking, both load-bearing enough to belong on the v0.3.0 pre-release checklist), reaffirm two R1 advisories as still open, and note one minor correctness nit in the verification script's trap ordering. These are small enough that they do not gate spec advancement but they are specific enough that they belong in the record so the implementation phase picks them up.

---

## Independent findings

### BLOCKING

None.

### ADVISORY

1. **Bidi/control-char regex omits U+FEFF (BOM/ZWNBSP) and line/paragraph separators (U+2028, U+2029).**
   Spec §Token handling line 1615 defines `r"[\x00-\x1f\x7f​-‏‪-‮⁦-⁩]"`. Decoded character-class contents: `\x00`–`\x1f` (C0), `\x7f` (DEL), `U+200B`–`U+200F` (ZWSP/ZWNJ/ZWJ/LRM/RLM), `U+202A`–`U+202E` (LRE/RLE/PDF/LRO/RLO), `U+2066`–`U+2069` (LRI/RLI/FSI/PDI). What is **not** covered:
   - `U+FEFF` — ZWNBSP / BOM, a classic homograph-smuggling and log-injection vector.
   - `U+2028` — LINE SEPARATOR; not escaped by all JSON log renderers in every language (JavaScript JSON.parse famously does not tolerate it in string literals — a cross-runtime log-injection risk).
   - `U+2029` — PARAGRAPH SEPARATOR, same rationale.
   - Tag characters `U+E0020`–`U+E007F` (emoji tag sequence / "invisible text smuggling") — if the spec aspires to reject Unicode smuggling holistically, these belong too.
   **Recommended action:** extend the regex to `r"[\x00-\x1f\x7f​-‏‪-‮⁦-⁩﻿  \U000E0000-\U000E007F]"`. Add a test case for each. Low cost; belongs before v0.3.0.

2. **Verification-script trap registration has a narrow window between probe-object creation and `trap` install.**
   Spec §Verification Script lines 1248–1267: step 2 creates the probe type and probe object; step 3 installs `trap cleanup EXIT INT TERM`. A SIGINT/SIGTERM arriving between the successful `POST /objects` (probe created, `$PROBE_OBJECT_ID` captured) and the line that installs the trap leaves an orphan probe object. The window is small but non-zero and the probe object is explicitly named `__verify-anytype-writes-probe-<timestamp>__` so detection is trivial, but an orphaned probe type is a nuisance the script is supposed to prevent. **Recommended action:** install the trap *first* with conditional-execution guards (the cleanup function already has `[[ -n "${PROBE_OBJECT_ID:-}" ]]` guards), then create the probe. Two-line refactor:
   ```bash
   PROBE_OBJECT_ID=""
   PROBE_TYPE_CREATED_BY_US=""
   cleanup() { ... }
   trap cleanup EXIT INT TERM
   # now create the probe
   ```
   Additionally, `|| true` on the DELETE (line 1257) swallows every failure mode, including "Anytype returned 500, object still exists, needs manual cleanup." Recommended mitigation: log the DELETE response body when non-2xx, so the operator sees WHY the auto-cleanup failed rather than being left with a zombie object and no signal.

3. **Schema bootstrap has a documented-but-real cross-machine TOCTOU.**
   Spec §Concurrent Ingest Policy line 1423 acknowledges "two machines concurrently ingesting the same space via a shared Anytype vault are not serialized." The same concern applies to `wiki_bootstrap`: two operators on two laptops running `wiki_bootstrap` against the same Anytype vault could both check-then-create the same Type. If Anytype's API deduplicates by `type_key`, this is benign; if it doesn't, you get two types with the same key and silent downstream confusion. **Recommended action:** the v0.2.0 pre-release checklist should include one empirical probe ("run `wiki_bootstrap` simultaneously from two processes against the same space, assert that re-run produces zero duplicates"). If duplicates DO appear, file a defect and document the cross-host limitation in the same place the flock cross-host limitation is documented. No code change gating; empirical verification only.

4. **[Reaffirming R1 CSO Advisory #13] Default port allowlist still includes 8080/8443.**
   `_ALLOWED_PORTS = {None, 80, 443, 8080, 8443}`. 8080 and 8443 are overwhelmingly internal-dev-server ports (Jenkins, Tomcat management, Kubernetes dashboards, proxy admin UIs). For a tool whose sole legitimate URL-fetching target is public web content, defense-in-depth argues for `{None, 80, 443}` by default with an env-var extension point (`WIKI_FETCH_EXTRA_PORTS`) for the small fraction of operators who need 8080/8443. R1 CSO flagged this at the council; it did not land in the spec. Worth landing before v0.3.0 tag.

5. **[Reaffirming R1 CSO Advisory #14 / review S15 gap] `QDRANT_API_KEY` in a URL query string is not explicitly covered by the error-string mask.**
   Spec line 1614 names the mask list as `Authorization`, `Bearer`, `ANYTYPE_API_KEY`, `QDRANT_API_KEY`. Qdrant Cloud's native auth flow uses a URL query string (`?api_key=...`) in some deployment configurations; if an operator sets `QDRANT_URL=https://xyz.cloud.qdrant.io/collections/x?api_key=abc...`, a Qdrant 500 that echoes the URL in the error-string path will leak the key. Spec line 1351 correctly specifies query-string stripping for **logging** of `extraction_endpoint`, but the `[API ERROR]` surface to the caller is a separate code path. **Recommended action:** add one regression test: "an `[API ERROR]` triggered by a Qdrant failure where `QDRANT_URL` contains `?api_key=<value>` returns an error string containing neither `<value>` nor the raw query string." R1 CSO surfaced this; it did not land with a named AC.

6. **Prompt-injection defense is complete for the extraction pass, but persisted-injection via file-backed `Query` objects remains an architectural concern for v0.4.0.**
   The three-layer defense (fence, pydantic policy, `is_central` corroboration) correctly hardens the extraction-time input. But the file-back path in v0.4.0 writes synthesis output (which may include extracted-entity names that, by then, are rendered as plain text) into Anytype as Query objects. Those Query objects are indexed and returned by future `wiki_query` calls, so a prompt-injected name that survives extraction becomes an injection vector into future synthesis prompts — a persistent poisoning path. R1 CSO Advisory #16 partially flagged this ("length-clamped and control-char-stripped at render time"). **Recommended action:** when v0.4.0 lands, ensure `wiki/query.py`'s prompt-assembly step (a) applies the same name-policy regex to any entity/concept name interpolated into the synthesis prompt, and (b) keeps the entity names inside a `<context>…</context>` fence parallel to the `<source>…</source>` fence used at extraction. Document this as a v0.4.0 pre-release item now, while the security architecture is fresh.

7. **`WIKI_EXTRACT_ENDPOINT` with embedded credentials is documented as stripped for logs but the error-string path needs parallel treatment.**
   Same shape as #5. An operator who sets `WIKI_EXTRACT_ENDPOINT=https://api-user:api-secret@hosted.example.com/v1/chat` (some providers still accept HTTP basic auth in the URL) will have their secret absent from logs (line 1351 strips userinfo before logging) but **present** in any `[API ERROR]` that echoes the endpoint. Tie this to the same regression test as #5: err strings containing `user:password@` should be masked to `***:***@`.

8. **`bandit` baseline file policy is unstated.**
   Spec line 1627 adds `bandit -r src/` to CI. Good. But SSRF-aware code intentionally uses `socket.getaddrinfo`, explicit port/scheme allowlists, manual redirect handling, and `httpx` with a custom transport — exactly the pattern bandit flags (B310 urllib_urlopen, B411 xmlrpc, or false-positive B113 no-timeout on intermediate helper functions). Without a committed `.bandit` baseline or `# nosec` annotations with rationale, the first drive-by PR will "silence" a finding by weakening the actual defense. **Recommended action:** commit a `.bandit` or `pyproject.toml` `[tool.bandit]` baseline at v0.2.0 tag time with the expected annotations. R1 CSO Advisory #15 raised this; landing it in the spec (not just the advisory pile) makes it durable.

9. **Dependency-pinning policy claim vs `pyproject.toml` reality: document both.**
   Spec §Dependency pinning line 1622 says "pyproject.toml pins dependencies to minor versions (e.g. `httpx>=0.27.0,<0.28.0`)." The **committed** `pyproject.toml` (this worktree) has `httpx>=0.27.0` with no upper bound. The spec explicitly schedules the upper-bound policy to land in v0.2.0 — fine. But the risk is that the **real** pin is in `uv.lock`, and a downstream consumer who uses pip (not uv) without `--require-hashes` gets whatever PyPI serves at install time. **Recommended action:** v0.2.0 release notes must explicitly state the two-layer pinning story: (a) `pyproject.toml` minor-range bounds for the PyPI metadata, (b) `uv.lock` committed for reproducible developer installs, (c) downstream consumers who pip-install without hash-pinning inherit only the minor-range guarantee. One paragraph in README under "Supply-chain posture" or the SECURITY.md that's already on the pre-release checklist.

10. **Residual (accepted, just surfacing): DNS-rebinding accepted-risk should have a tripwire, not just a note.**
    Spec line 1608 labels DNS rebinding an accepted residual risk. Fine under the single-operator threat model. But the threat model will drift — MCP tools are increasingly wired into agentic pipelines where the "operator" is an LLM consuming URLs from an untrusted context window. **Recommended action:** add a single integration test that asserts `wiki_ingest` with a URL whose DNS resolution changes between the check and the connect **fails closed** if the post-connect observed peer IP does not match one of the check-time resolutions. This can be done at the httpx transport layer (`TransportError` on peer-IP mismatch) without the full connect-by-IP complexity. If it's too expensive for v0.3.0, document the test as a v0.4.0 deliverable with a ticket reference. Merely "accepted residual risk" without a mechanical tripwire means the risk grows silently as the code evolves.

---

## R1 Delta

### Items R1 CSO flagged that still hold

- **Advisory #1 (OSS threat-model README paragraph):** still correct, not landed in spec itself; flagged for CPO README inclusion. I agree.
- **Advisory #2 (SECURITY.md + coordinated disclosure):** still correct and critical. On the pre-release checklist per R1 resolution. I agree.
- **Advisory #13 (port allowlist 8080/8443):** still correct; I reaffirm as my own ADVISORY #4.
- **Advisory #14 (QDRANT_API_KEY regression test):** still correct; I reaffirm as my own ADVISORY #5 and extend it to `WIKI_EXTRACT_ENDPOINT` userinfo (#7).
- **Advisory #15 (bandit baseline):** still correct; I reaffirm as my own ADVISORY #8 and argue it belongs in the spec itself, not just the advisory pile.
- **Advisory #16 (CLI render-time sanitization of entity names):** still correct; I reaffirm as my own ADVISORY #6 and extend it to the v0.4.0 synthesis-prompt-interpolation path (persistent injection).
- **Advisory #17 (endpoint-hash ack limitation — hostile DNS / CDN repoint):** still correct. No code change; document in README.

### Items R1 CSO flagged that are now resolved / don't hold

- None materially. R1 CSO's positive assessments (seven SSRF invariants, `is_central` cross-check, write-token scope flow, verification-script self-cleaning lifecycle) are all empirically correct and I endorse them unmodified.

### Items R1 CSO MISSED that I flagged

- **The bidi/control-char regex gap (my ADVISORY #1):** U+FEFF, U+2028, U+2029, and tag characters are not in the character class. R1 CSO approved the regex without enumerating its coverage. Minor but concrete.
- **Verification-script trap-window race (my ADVISORY #2):** R1 CSO praised the self-cleaning lifecycle correctly but did not notice the small window between `POST /objects` and `trap cleanup EXIT INT TERM`. Real risk is low (you have to SIGINT in a ~millisecond window) but the fix is free.
- **The `|| true` on DELETE swallowing ALL failure signals (my ADVISORY #2, second paragraph):** the script can "succeed" while leaving an orphaned probe object and emit no diagnostic. R1 CSO did not surface this.
- **Cross-machine TOCTOU on bootstrap (my ADVISORY #3):** R1 infra lead correctly documented the cross-machine lock limitation for ingest. The *same* limitation applies to bootstrap — two operators on two machines running `wiki_bootstrap` against a shared Anytype vault. R1 CSO did not extend the concurrency concern to bootstrap.
- **`WIKI_EXTRACT_ENDPOINT` userinfo in error strings (my ADVISORY #7):** R1 CSO flagged `QDRANT_API_KEY` but stopped there. Userinfo-in-URL is a separate and equally valid egress-credential shape.
- **Persistent prompt injection via file-backed Query objects (my ADVISORY #6):** R1 CSO Advisory #16 partially raised this ("CLI render-time sanitization") but did not connect it to the v0.4.0 synthesis-prompt-assembly path, which is the actually-dangerous persistence channel.
- **Dependency-pinning two-layer story (my ADVISORY #9):** R1 CSO didn't probe the pyproject.toml reality against the spec's claim or articulate the pip-vs-uv downstream-consumer distinction.
- **DNS-rebinding tripwire (my ADVISORY #10):** R1 CSO agreed with the spec's "accepted residual risk" label. I agree on the accept — but "accept" without a mechanical tripwire lets the risk drift as the threat model evolves.

### Items R1 CSO had that I disagree with

- None. R1 CSO's substantive security assessments are correct. My delta is pure addition (items missed), not disagreement.

---

## Calibration verdict on R1

**The R1 sign-off holds — conditionally.** No BLOCKING finding surfaced at R2 that R1 missed; the security architecture as specified is correct on the merits and the seven SSRF invariants, the kernel-held flock, the three-layer prompt-injection defense, and the self-cleaning verification-script lifecycle are all genuinely well-designed. The R1 CSO "SIGN OFF" verdict is defensible.

However, R1 CSO's assessment was shallower than a real CSO would have produced: it accepted the bidi regex without enumerating its coverage, it praised the verification-script lifecycle without noticing the trap-window race or the `|| true` diagnostic blindness, it didn't extend the cross-host concurrency concern from ingest to bootstrap, and it didn't articulate the v0.4.0 persistent-prompt-injection path as a current-phase design obligation rather than a future worry. Those are all advisory-level gaps — genuinely not blocking — but they are gaps, and they're the kind of gaps that a synthesis-level impersonator would generate: plausible-sounding approval plus the R1 CSO's real findings (which were independently surfaced by the parallel security-reviewer at review-r1-security.md), without the extra layer of delta-probing that a real specialist does.

**Bottom line:** R1 CSO reached the right verdict (no BLOCKING) but the reasoning underneath was thinner than it should have been. This R2 calibration adds the missing depth. Spec advances; R1 verdict is preserved; ten new ADVISORY items documented for the implementation phase to pick up.

---

## Files referenced

- `/Users/Shared/development/anytype-llm-wiki-worktrees/wiki-library-module-port-llm-wiki-pattern-onto-any/.aldeia/140-wiki-library-module-port-llm-wiki-pattern-onto-any/spec.md` (spec under review; key lines: 1170–1240 extraction defense, 1242–1295 verification script, 1409–1423 concurrent ingest, 1487–1645 Security Considerations, 1614 mask list, 1615 bidi regex)
- `/Users/Shared/development/anytype-llm-wiki-worktrees/wiki-library-module-port-llm-wiki-pattern-onto-any/.aldeia/140-wiki-library-module-port-llm-wiki-pattern-onto-any/council-spec-r1.md` (R1 council meeting; CSO assessment at lines 36–46, advisories at lines 140–193)
- `/Users/Shared/development/anytype-llm-wiki-worktrees/wiki-library-module-port-llm-wiki-pattern-onto-any/.aldeia/140-wiki-library-module-port-llm-wiki-pattern-onto-any/review-r1-security.md` (real specialist security review; findings at lines 41–131)
- `/Users/Shared/development/anytype-llm-wiki-worktrees/wiki-library-module-port-llm-wiki-pattern-onto-any/.aldeia/140-wiki-library-module-port-llm-wiki-pattern-onto-any/review-r2.md` (specialist verification review; SSRF invariant pass at lines 110, flock pass at line 111, trap pass at line 112)
- `/Users/Shared/development/anytype-llm-wiki-worktrees/wiki-library-module-port-llm-wiki-pattern-onto-any/pyproject.toml` (current dependency pins — no upper bounds yet; to be tightened in v0.2.0 per spec line 1622)
