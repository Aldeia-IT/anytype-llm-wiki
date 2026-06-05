# Council Impl R1 — Legal Counsel (General Counsel)

Ticket: Aldeia-IT/aldeia-box #286 — v0.5.0 `wiki_lint` structural health check
Gate: Post-implementation / final delivery gate (PR merge to feature branch)
Date: 2026-06-05

## Verdict

**SIGN OFF** — clean. Zero blocking findings. My prior NOT-PRESENT assessment holds against the shipped code: this is an MIT-licensed, local-first, report-only diagnostic with no new data, license, credential, or regulatory surface.

## Findings

### BLOCKING

None.

### ADVISORY

**A1. CRA / SECURITY.md is a tag-time concern, not a merge-time gate — and it is already satisfied.**
- Description: The #140 council flagged that any release *tag* cut on/after 2026-06-11 requires a SECURITY.md under the EU Cyber Resilience Act (Reg. (EU) 2024/2847). This PR is a merge to a feature branch, not a tag cut, so the 2026-06-11 trigger does not gate THIS merge. Independently, `SECURITY.md` already exists at repo root with a private vulnerability-reporting channel, defined response timelines, coordinated disclosure, and an explicit CRA "Regulatory Context" section (correctly noting Article 14 reporting obligations from 11 Sept 2026). The obligation is therefore non-gating here and substantively pre-met.
- Legal basis: EU Cyber Resilience Act, Reg. (EU) 2024/2847 (coordinated vulnerability handling; Art. 14 reporting).
- Recommended action: None required for this merge. At the next *tag cut*, confirm the SECURITY.md "Supported Versions" table is refreshed (currently lists 0.2.x as the current line; v0.5.0 will supersede it). Housekeeping only — owned by the release/tag process, not this PR.

**A2. Duplicate sweep stays on-box — no controller relationship created.**
- Description: The opt-in `include_duplicates=True` path calls `indexer.semantic_search_core`, reusing the pre-existing local Qdrant/Ollama embedding infrastructure that predates #286. No content is transmitted off-machine. The only off-box egress vector in the whole product remains the unrelated, off-by-default, consent-gated `WIKI_EXTRACT_ENDPOINT` (untouched by this PR). Operator's own local notes only; no third-party data subjects, so no GDPR/LGPD controller or processor role attaches to Aldeia.
- Legal basis: GDPR Art. 4(7)/(8); LGPD Arts. 5/37 — none triggered (no processing on behalf of, or about, third parties by Aldeia).
- Recommended action: None. Documented here for the record.

## Rationale

1. **Licensing — clean.** `git diff main...HEAD -- pyproject.toml` shows no dependency changes. Every import in `src/anytype_llm_wiki/wiki/lint.py` is either internal (`from . import` / `from ..`) or a stdlib/already-vendored module (`httpx`, `logging`, `time`, `datetime`). No NET-NEW third-party dependency, hence no new license to vet, no GPL/AGPL contamination risk introduced. The reused Qdrant client and Ollama-via-indexer were in the tree pre-#286 and are out of scope per the brief.

2. **Data handling / privacy — clean.** `wiki_lint` is read-and-report-only (mutates nothing but its own WikiLog receipt), enumerates the operator's own wiki via the local Anytype API, and writes a local receipt. No telemetry, no phone-home, no new external API, no new credential. `.env.example` adds only six optional local tuning knobs (thresholds/windows), none of which is a secret or an endpoint. `compliance.md` confirms the local-first, no-telemetry posture and that the only off-box path is the unrelated consent-gated extraction endpoint. No PII beyond what the operator places in their own notes; no Aldeia controller/processor relationship.

3. **CRA / SECURITY.md.** This is a feature-branch merge, not a release tag, so the 2026-06-11 CRA tag-time trigger does not apply to this gate. SECURITY.md already exists and addresses the CRA expectations. Non-gating; see A1.

4. **Nothing else legally material.** No ToS/EULA change, no new liability surface (report-only, no content mutation), no IP exposure, no accessibility/export-control/age-verification angle. The contractual deliverable (a report-only structural linter) matches what was specced.

No CSO crossover beyond the shared CRA/SECURITY.md item, which is already handled.

**SIGN-OFF: APPROVED from a legal/compliance perspective. No veto.**
