# Council Review — Spec Phase (#286 wiki_lint v0.5.0)
## Client Advocate

**Date:** 2026-06-05
**Reviewer:** Client Advocate (representing Jan Scheufen / Aldeia IT interests)
**Artifact:** spec.md (Status: SPEC, R2 APPROVED), spec-scope.md, review-r1/r2
**Lens:** Does this serve the client's actual goal, respect stated principles/constraints, and fit a public OSS repo maintained solo?

---

## Verdict: **ADVANCE WITH ONE BLOCKING FIX**

The spec is well-targeted to what Jan actually wants: it closes the maintain loop (ingest → remember → query → **lint**) and — crucially — produces *live, populated* High findings on a real pipeline wiki (D3 `unreviewed_needs_review`), not just passive checks. That directly answers the "value on day one" bar. Local-first is honored (no off-box calls; the one remote exception `WIKI_EXTRACT_ENDPOINT` is untouched). Zero-config-for-Aldeia holds (six knobs, all with sane defaults). Anti-bloat discipline is good for a sole maintainer.

There is **one client-experience defect the two technical reviews structurally could not catch**, because they validated correctness, not the default user's lived experience: the **default invocation can hang for minutes and saturate the local box**. That is a client-facing regression dressed as a feature default. It is BLOCKING from the client's chair — fix the default, then ship.

---

## BLOCKING

### CA-B1 — The default `wiki_lint(space_id)` call runs the expensive duplicate sweep; it can take ~3× the advertised budget and saturate the local Ollama on Jan's single box

**What the spec says:** the signature default is `severity_threshold="all"`. The spec gates the duplicate sweep to `severity_threshold == "all"` (B2 fix) and considers that resolved. But "all" *is the default*. So the bare, most-common call — the one Jan and every OSS user will type first, the one a launchd/cron schedule will run — triggers the full sweep.

**The cost the spec itself admits:** the non-sweep battery is ~51s @ 500 objects (get_object fan-out alone). The sweep then adds **N bge-m3 embeddings + N Qdrant queries, sequential, on top** (spec §186, §263: "the dominant, variable cost"). The infra reviewer's own estimate puts the default run near ~160s on a 500-object wiki — roughly 3× the prominently advertised "≤60s for ≤500 objects" budget. The README will carry that ≤60s claim (brand voice: "no marketing fluff" — an overstated perf number is exactly the kind of thing that erodes a public repo's credibility).

**Why R1/R2 marked this resolved and I do not:** R1-B2's accepted fix was "run the sweep only when `severity_threshold == "all"`." That bounds the sweep to *one* threshold value — but it's the *default* value, so it bounds nothing for the default user. The reviewers verified the ≤60s figure for the *non-sweep* battery and treated the sweep as a separate, opt-in cost. From a correctness lens that's coherent. From the client's lens it's backwards: the slow, resource-heavy path is the path of least resistance, and the fast path requires the user to know to pass `severity_threshold="high"`.

**Client impact (this is the part the pure-technical lenses undervalue):**
- Jan runs `wiki_lint(my_space)` in a Claude Code session, expects a structural report, and instead gets a multi-minute hang while bge-m3 is pinned — on the *same* Ollama instance that ingest/query/IronClaw depend on. On a single constrained box, a 500-embedding burst is a self-inflicted denial of service against his own knowledge-base tooling mid-session.
- A scheduled lint (the natural deployment, paralleling auto-reindex) silently saturates the box on every run.
- The published ≤60s number is wrong for the default invocation — a public-repo credibility cost under the Aldeia-IT name.

**Recommended action (any one; preference order):**
1. **Change the default so the sweep is opt-in.** Make the duplicate sweep (Informational-tier — the lowest-value findings) NOT run on the default call. Either default `severity_threshold` to `"high"`/`"medium"`, or keep `"all"` as the default *report* scope but put the sweep behind its own explicit opt-in knob/argument (e.g. `include_duplicates=False`). The default run should stay inside the advertised ≤60s budget.
2. If the council insists the default stays `"all"` and includes the sweep, then **the advertised budget and README must tell the truth**: state the default-run worst case (~160s @ 500) explicitly, and ship the `WIKI_LINT_DUPLICATE_SAMPLE` cap *now* rather than deferring it (spec §426), so the default can't run unbounded embeddings on a large wiki.

Option 1 is the client-right answer: the cheapest, most-typed call should be fast and safe on Jan's box; the expensive scan should be something he opts into knowingly. This is a small spec edit (flip a default / add one gate), not a redesign.

---

## ADVISORY

### CA-A1 — Six new `WIKI_LINT_*` knobs: defaults are sane, but confirm the README documents them in the project's terse style, not as a wall
Zero-config-for-Aldeia holds (everything has a default; it "just works" with no env set). For the OSS audience, the six knobs are reasonable and each maps to a real tuning need. Client ask: the README lint section should list them compactly (one line each, as the existing config table does) and lead with "you don't need to set any of these." Keep brand voice — practical, no fluff. Not blocking; just protect the docs surface.

### CA-A2 — Maintenance surface is acceptable for a sole maintainer, with one watch-item
New module + 6 knobs + 10 checks + 32 tests is *not* over-engineered for the value delivered — it's mostly ~80% reuse of shipped infra, and the test count is one-per-check plus pre-checks, which is what a public repo should have. Watch-item for Jan: `pipeline_orphan` is an explicit timestamp-proximity *heuristic* with documented false negatives (no run-id linkage). That's honestly specified, but it's the one check whose findings Jan should treat as advisory, and the README/CHANGELOG should not oversell it as deterministic. Sustainable as-is.

### CA-A3 — `backlinks` element shape is asserted from a live session, not verified in CI
The whole D1 "primary path" rests on `get_object` returning a `backlinks` array of a known shape, confirmed once in a live 2026-06-03 session, never in a fixture. The spec contains this risk well (`_parse_relation_elements` handles both shapes; malformed → fallback). Client note: this is fine to advance, but the implement phase should confirm the shape against a live `get_object` as task one (the phase summary already flags this). If it's wrong, the primary path silently degrades to the O(N) fallback — slower, but not incorrect. Acceptable risk; flagging so it isn't lost.

### CA-A4 — Report-only / no-auto-fix is the right call for the client
`wiki_lint` mutates nothing but its own WikiLog receipt. For a public tool that runs against people's personal Anytype vaults (and Jan's company knowledge base), report-only is the trustworthy default — no surprise edits. This matches the client's risk appetite. No action; recorded as a positive.

### CA-A5 — Local-first fully respected
Verified against the client's stated principle: the duplicate sweep uses local Ollama (bge-m3) + local Qdrant; no call leaves the box; `WIKI_EXTRACT_ENDPOINT` (the sole opt-in remote exception) is not touched by lint. No telemetry. This is exactly the posture Jan ships under the Aldeia-IT name. No action.

---

## Rationale (client's voice)

I want this tool — it finishes the maintain loop I asked for, and unlike a box of passive checks it actually lights up on my real wiki the day it ships (the needs-review High signal). The design respects the things I care about most: it stays on my box, it works with zero config for me, and it doesn't touch my data beyond writing its own log entry. As a public artifact under my company's name, it's the right shape: report-only, terse, no marketing fluff to grep out.

My one hard objection is the default behavior. I'm going to type `wiki_lint(space)` — that's the obvious call, and it's what a scheduled job will run. As specced, that default fires the heaviest, lowest-value scan: hundreds of embeddings against the *same* Ollama my ingest, query, and IronClaw assistant all depend on, taking roughly three times the 60-second budget I'm about to advertise in my own README. That's me knocking over my own tooling, on my own constrained box, with the most natural command — and publishing a perf number that isn't true for the default path. The fix is small: make the fast, safe path the default and let me opt *into* the expensive duplicate scan when I want it. Do that and I'm happy to ship.

---

## Sign-off

**CONDITIONAL APPROVAL — one BLOCKING fix (CA-B1) before Implement.** The spec is otherwise client-aligned and I endorse advancing it. Resolve CA-B1 (default invocation must stay within the advertised budget and must not saturate the local box) — preferably by making the duplicate sweep opt-in rather than default-on — and I sign off without further conditions. ADVISORY items need no gate; surface CA-A1 (docs) and CA-A2 (heuristic honesty) to whoever writes the README/CHANGELOG.

If the council overrides CA-B1, my fallback condition is non-negotiable: the README/perf claim must state the default-run worst case truthfully, and the sweep sample cap must ship in v0.5.0, not be deferred.
