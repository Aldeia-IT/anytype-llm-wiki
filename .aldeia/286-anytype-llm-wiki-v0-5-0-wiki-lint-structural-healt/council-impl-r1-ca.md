# Council Review — Implementation Phase (#286 wiki_lint v0.5.0)
## Client Advocate

**Date:** 2026-06-05
**Reviewer:** Client Advocate (representing Jan Scheufen / Aldeia IT interests)
**Artifact:** `git diff main...HEAD` — `wiki/lint.py`, `server.py`, `wiki/cli.py`, `README.md`, `CHANGELOG.md`, `.env.example`
**Lens:** Did the client actually receive what was promised at spec — chiefly the CA-B1 default-safety fix and the honesty-of-claims carry-forwards (CA-9) — and is anything here a reputation hazard at the OSS release?

---

## Verdict: **SIGN OFF**

The client got exactly what was promised. CA-B1 — the central battle of this ticket — is delivered structurally, not just in prose: the expensive, box-saturating duplicate sweep is gated behind `include_duplicates=True`, which defaults to `False` on all three entry surfaces (MCP tool, CLI, internal function). The bge-m3 embedding call is physically unreachable on the default path. The performance claim is stated honestly and scoped to the sweep-off path. The CA-9 docs carry-forwards (compact knobs, "you don't need to set any of these", honest `pipeline_orphan` heuristic, passive-contradiction caveat) are all present and in brand voice. Nothing here embarrasses the client at release. Zero blocking findings.

---

## CA-B1 delivery verification (the gate + the README claim)

**The gate is real and structural.** `wiki_lint`'s signature (`src/anytype_llm_wiki/wiki/lint.py:186-190`) defaults the sweep off:

```python
def wiki_lint(
    space_id: str,
    severity_threshold: str = "all",
    include_duplicates: bool = False,
) -> dict:
```

The only embedding-touching call in the entire module — `indexer.semantic_search_core(...)` at `lint.py:496`, the bge-m3 load — sits entirely inside the opt-in branch (`lint.py:479-526`):

```python
# --- Step 7: opt-in duplicate sweep ---
potential_duplicates: list[dict] = []
if include_duplicates:
    if len(wiki_objects) > config.lint_max_objects():
        report["warnings"].append("lint_sweep_skipped_object_cap: ...")
    else:
        ...
        cands = indexer.semantic_search_core(q, space_id, list(_CONTENT_TYPES), 5)
```

I grep-confirmed `semantic_search_core` / `embed` appear nowhere else in `lint.py`. The bare `wiki_lint(space)` call — the one Jan and every OSS user types first, the one a scheduled job runs — therefore loads zero bge-m3 work onto the shared Ollama. This is precisely the resolution Jan chose. The self-inflicted DoS against the shared Ollama that I blocked at spec is gone.

**Consistency across all surfaces (no back-door default-on):**
- MCP tool (`server.py:175-181`): `include_duplicates: bool = False`, and it forwards the param unchanged.
- CLI (`wiki/cli.py:336`): `--include-duplicates` is `action="store_true"` → off unless the flag is passed; forwarded at `cli.py:205`.
- CHANGELOG: "`include_duplicates?` (default `False`)" and "The `potential_duplicate` Qdrant sweep runs only with `--include-duplicates` / `include_duplicates=True`".

There is no path on which the default invocation runs the sweep. CA-B1 delivered.

**The honest perf claim (my reputation concern).** README "The duplicate sweep is opt-in" section states verbatim:

> The `potential_duplicate` sweep embeds the wiki and runs a Qdrant similarity search per Object, so it is **disabled by default**. Pass `--include-duplicates` (MCP: `include_duplicates=True`) to enable it. The advertised performance budget (≤60s for a wiki of ≤500 Objects) describes the **default, sweep-off path only** — the opt-in sweep can exceed that budget and is hard-skipped entirely above `WIKI_LINT_MAX_OBJECTS` (with a warning).

The ≤60s/≤500 number is explicitly scoped to the default sweep-off path and explicitly says the opt-in sweep "can exceed that budget." This is the truthful claim my fallback condition demanded, and the same scoping is repeated in the tool docstring (`server.py`) and CHANGELOG. No oversell under the OSS name. The reputation hazard I raised at spec is fully closed.

---

## CA-9 docs verification

**Six WIKI_LINT_* knobs documented compactly with the explicit "you don't need to set any" note.** All six appear as one-line rows in the existing config table style (README env table), and the section carries verbatim:

> **You do not need to set any of the `WIKI_LINT_*` knobs** — the defaults are sensible for a typical wiki. They are exposed only for operators tuning a large or unusual space.

This satisfies CA-A1/CA-9 exactly: terse, developer-facing, leads with "you don't need these," zero-config-for-Aldeia posture preserved.

**`pipeline_orphan` is NOT oversold — the honest ±300s heuristic with by-design false negatives is stated.** README, immediately after the knob note:

> Note `pipeline_orphan` is an honest ±300s timestamp heuristic: it correlates a zero-relation Object against a recorded ingest `relation_rollback` failure and has false negatives by design (it cannot prove an Object is *not* a pipeline orphan).

The "What it checks" table also labels it "(±300s heuristic)". This is the honesty I asked for at CA-A2 — Jan can treat its findings as advisory and no reader will mistake it for deterministic. Good.

**Operator over-trust caveat (passive contradiction, green ≠ guarantee) is visible where operators will look.** It appears in three places an operator actually reads — the README has a dedicated subsection:

> The `contradiction_unresolved` check is **passive** in v0.5.0 ... A green contradiction result is therefore **not a guarantee** that no contradictions exist ... Do not over-trust a clean contradiction column.

— plus the same caveat in the `wiki_lint` tool docstring (surfaced to any agent inspecting the tool) and the CHANGELOG. The table row is annotated "**passive (see below)**". This satisfies CPO-6/addendum-item-5. An operator cannot reasonably miss it.

---

## Findings

### BLOCKING
None.

### ADVISORY

**CA-A1 (impl) — `pipeline_orphan` and `orphan` definitions diverge slightly from the master spec; harmless to the client, worth a one-line note for the v0.6.0 backlog.**
The impl-review SUGGESTION notes `orphan` requires `not has_inbound AND not _outbound(o)`, stricter than the master spec's "no inbound." Client impact: negligible — an outbound-only object also fires `asymmetric_relation` (Critical), a louder signal, so nothing is silently lost. No action this release; carry to #287 only if pure-inbound orphan detection is later wanted. Recorded so it is not lost, not a gate.

**CA-A2 (engagement health) — the deliverable is demo-ready and over-delivers slightly on documentation honesty, which is the right direction for a public repo.**
Three honesty caveats redundantly placed (README + docstring + CHANGELOG) is not gold-plating the client won't pay for — it is exactly the credibility insurance an OSS repo under the Aldeia-IT name needs, and it cost a few sentences. I would happily present this at a sprint demo: `wiki_lint(space)` returns a structural report in ~51s with no box impact, and `--include-duplicates` is there for when Jan knowingly wants the deeper scan. Positive, no action.

---

## Rationale (client's voice)

I raised exactly one hard objection at spec: that the obvious command — `wiki_lint(space)`, the one I'd type and the one a cron job would run — fired the heaviest, lowest-value scan against the same Ollama my ingest, query, and IronClaw assistant all share, at ~3× the 60-second number I was about to publish under my own company's name. That objection is now fully answered, and not by a promise in a doc — by the code shape. The embedding call only exists inside `if include_duplicates:`, and that flag is off by default everywhere I could invoke it. My default lint is light, fast, and safe on my single box. My published perf number is true for that default path and says so plainly. The duplicate sweep is mine to opt into when I choose.

The carry-forwards I cared about as the public maintainer are all honored: the knobs are documented terse and lead with "you don't need these," the `pipeline_orphan` heuristic is described as the honest ±300s correlation it is rather than dressed up as deterministic, and the "green contradiction is not a guarantee" caveat is impossible to miss. This finishes the maintain loop I asked for (ingest → remember → query → lint), it stays entirely on my box, it mutates nothing but its own receipt, and there is nothing in it that would embarrass me at the OSS release. The client got what was promised.

---

## Sign-off

**SIGN OFF — no conditions.** CA-B1 delivered as designed and verified in code, not just prose. The performance claim is honest and correctly scoped. The CA-9 docs honesty deliverables are all present and in brand voice. Zero blocking findings from the client's seat. The two ADVISORY items need no gate. Ship it.
