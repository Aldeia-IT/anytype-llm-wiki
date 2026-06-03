# Impl Review — #234 v0.2.0 real-API rework (Round 2)

**Date:** 2026-06-03
**Reviewer:** impl lead (adversarial single-commit review — post-council, never previously reviewed)
**Branch:** aldeia/234-v0-2-0-tag-prep-checklist-anytype-llm-wiki-post-im
**Commit under review:** `a715c1c` — "fix(wiki): make bootstrap + doctor work against the real Anytype API"
**Files:** `src/anytype_llm_wiki/wiki/{bootstrap,wiki_client,types_schema,doctor}.py`, `tests/wiki/{test_bootstrap,test_wiki_client}.py`
**Scope:** the only `src/` change ever made after council sign-off. All prior council rounds asserted "zero `src/` changes"; this commit reworks the bootstrap write-plane + doctor against live Anytype.

## Verdict: SIGN OFF WITH ADVISORIES

The real-API contract corrections are sound and I verified them against the live Anytype
instance (version 2025-11-08, space `wiki-e2e-1`): `GET /objects` returns the per-object
`properties` array carrying `wiki_schema_version: "0.2.0"` on the WikiLog; the root "Wiki"
collection has `type.key == "collection"` / `layout == "collection"`; tags live under
`/properties/{id}/tags`. The suite is green (256 passed, 22 skipped, 3 xfailed). No BLOCKING
defect: nothing here can corrupt operator data or crash bootstrap, and the spec's only *active*
consumer of the schema marker (other `wiki_*` tools) does not exist until v0.3.0+. The advisories
below must be carried into the v0.2.0 tag punch-list, and SHOULD-FIX-1 (WikiLog accrual) and
SHOULD-FIX-2 (dropped `wiki_action`) should be fixed before v0.3.0 builds on this surface.

## Objective gates (run by the lead)

| Gate | Result |
|------|--------|
| `uv run pytest -q` | **256 passed, 22 skipped, 3 xfailed** |
| Live `GET /v1/spaces/{wiki-e2e-1}/objects` | per-object `properties[]` array present; WikiLog carries `wiki_schema_version=0.2.0`; root "Wiki" collection has NO `wiki_schema_version` property |
| Live: WikiLog count in `wiki-e2e-1` | **2** WikiLog objects (`…09:06:14Z` created=0, `…09:05:56Z` created=43) — two bootstrap runs ⇒ two markers (see SHOULD-FIX-1) |

---

## BLOCKING

None.

---

## SHOULD-FIX

### SHOULD-FIX-1 — Re-bootstrap accumulates a new WikiLog marker every run (idempotency leak)
**Evidence:** `bootstrap.py:403-428` always creates a fresh `wiki_log` object on every run; there is
no skip/dedup for the WikiLog itself. **Confirmed live:** space `wiki-e2e-1` contains two WikiLog
objects from two runs (`wiki_objects_created: 43` then `0`). The commit message claims "idempotent
on re-run (all skipped, zero duplicates)" — true for types/properties/tags, **false for the WikiLog
marker**, which is now also the schema-version marker.
**Why it matters:** (a) spec §Observability frames WikiLog as append-only operational records, so
one-per-run is arguably intended for *operations* — but this commit overloaded the same object as the
**schema-version marker** (`bootstrap.py:416`). Every re-bootstrap therefore leaves an ever-growing
pile of marker objects, and `_run_bootstrap` reads **all** of them via `_max_version` over
`list_objects` (`bootstrap.py:248-249`). It is correct today (all carry the same version) but it is
O(n) marker scanning that grows without bound and muddies the "what is the current schema version"
question after a real upgrade (old + new markers coexist; `_max_version` papers over it).
**Recommendation:** either (a) keep WikiLog append-only but stamp the *authoritative* schema version
on the single long-lived root Collection (see Spec-conformance note + ADVISORY-1), or (b) make the
bootstrap WikiLog idempotent (skip if a `wiki_log` named/marked for the current run already exists).
Option (a) is preferred and also resolves the spec deviation.

### SHOULD-FIX-2 — `wiki_action` is no longer written on the WikiLog
**Evidence:** the new `_build_props_list` call (`bootstrap.py:410-418`) writes `wiki_subject`,
`wiki_objects_created`, `wiki_timestamp`, `wiki_notes`, `wiki_schema_version` — but **not**
`wiki_action`. The pre-commit code wrote `"wiki_action": "bootstrap"`. **Confirmed live:** the two
WikiLog objects in `wiki-e2e-1` have no `wiki_action` value (the property exists on the type but is
unset). Spec §WikiLog (spec.md:287) defines `wiki_action (select): ingest | query | lint | bootstrap
| archive` as the primary discriminator of log entries, and the lint suite (v0.5.0) groups by it.
**Why it likely happened:** `wiki_action` is a `select` and `_build_props_list` maps `select` →
`{"key":…, "select": value}`. A select option must pre-exist as a tag; writing a bare value may have
404'd live, so it was dropped silently. That is a real-API constraint worth documenting, but dropping
the field leaves every bootstrap log unattributable.
**Recommendation:** either create the `bootstrap` select option during bootstrap and write
`wiki_action`, or (cheaper) record the action in `wiki_notes`/name and add a one-line comment in
`_build_props_list` explaining why `select` values are omitted at bootstrap. At minimum, document the
omission so v0.5.0 lint does not assume `wiki_action` is populated.

### SHOULD-FIX-3 — The real-API array-shape read path of `_found_schema_version` has zero test coverage
**Evidence:** the upgrade test `TestBootstrapSchemaOutdated` (`tests/wiki/test_bootstrap.py:648-655`)
seeds the old version as a **top-level** `wiki_schema_version` key on a collection dict
(`{"id":"coll-001","name":"Wiki","wiki_schema_version":"0.1.0"}`). `_found_schema_version`
(`bootstrap.py:106-108`) satisfies this via the legacy top-level branch — the new `isinstance(props,
list)` branch (`bootstrap.py:114-119`), which is the *only* path that fires against the real API
(verified: live objects carry `properties` as a list of `{"key":…, "text":…}`), is never exercised.
The test is now effectively testing a shape the real API never returns.
**Recommendation:** add a test that seeds a WikiLog object with `"properties": [{"key":
"wiki_schema_version", "text": "0.1.0"}]` (the real shape, which I captured from
`GET /objects`) and asserts `schema_upgrade.from == "0.1.0"`. Without it, a regression in the
array branch ships green.

---

## NIT

- **NIT-1 — `_find_root_collection` now matches name-only.** `bootstrap.py:480-485` dropped the
  schema-version fallback and matches purely on `name == "Wiki"`. A user with any unrelated object
  literally named "Wiki" will have it adopted as the root collection (and bootstrap will then *not*
  create the real collection). The old code had the same name match but at least also recognized the
  marker. Low likelihood; worth a comment or a `type_key == "collection"` guard (the live data carries
  `type.key`, so this is cheaply checkable).
- **NIT-2 — `_FORMAT_VALUE_FIELD` "objects"/"files" map to themselves but `_build_props_list` is only
  ever called with text/number/date.** `bootstrap.py:50-62` is forward-looking dead breadth for
  v0.2.0; fine, but note the `objects` typed field for a PropertyLinkWithValue may not be `objects` on
  the real write contract (untested here). Flag for v0.3.0 when objects/relations are actually written.
- **NIT-3 — `create_property` still takes a `type_key` arg it ignores** (`wiki_client.py:25-34`).
  Harmless (documented as caller convenience), but dead now that bootstrap creates properties inline
  via `create_type` and never calls `create_property` in the happy path. Bootstrap no longer calls
  `create_property` at all — the method is only reached by `test_wiki_client.py`. Consider dropping the
  parameter when the v0.3.0 surface settles.
- **NIT-4 — doctor 401/403 message says "rejected ANYTYPE_API_KEY … Regenerate a write-scoped key"**
  (`doctor.py:91-98`). A 401 on `GET /v1/spaces` is an auth/identity failure, not necessarily a
  *scope* failure (read scope is enough to list spaces). The "write-scoped" wording may mislead. Minor.

---

## ADVISORY

### ADVISORY-1 — Spec-conformance: the schema-version marker moved from root Collection → WikiLog
This is the headline deviation and it is called out explicitly in the commit body and module
docstring (`bootstrap.py:6-7, 19-25`), so it is a *deliberate, documented* choice — acceptable for
v0.2.0, but it contradicts the written spec and must be reconciled before a downstream tool depends
on it. Specifics:

- Spec §Schema Compatibility (spec.md:1590) and the bootstrap-specific upgrade clause (spec.md:1603)
  state the **root Collection** carries the `wiki_schema_version` text property and that step 3 of the
  upgrade flow "updates `wiki_schema_version` on the root Collection." AC #13 (spec.md:743) and the
  future-tool AC for ingest/query (spec.md:904) say those tools read the marker "from the root
  Collection" / seed it "on the root Collection."
- The commit instead stamps the version on the (per-run) WikiLog and reads it back from any object's
  array-shaped properties (`bootstrap.py:416`, `_found_schema_version` `bootstrap.py:114-119`). The
  root Collection is created with `properties=None` (`bootstrap.py:383`) and carries **no** marker —
  I verified this live (the "Wiki" collection in `wiki-e2e-1` has no `wiki_schema_version` property).

**Is the deviation acceptable?** For v0.2.0 in isolation: **yes** — no shipped code consumer of the
marker exists yet (ingest/query/lint are v0.3.0+; the v0.3.0+ ACs are still `xfail` scaffolding,
`test_bootstrap.py:744-759`). The read-back works against the real API because list-objects returns
per-object `properties`. **But** it interacts badly with SHOULD-FIX-1: because the marker now lives on
a per-run object, "the space's schema version" is no longer a single authoritative value — it is the
`_max_version` over an unbounded set of WikiLogs. The cleaner reconciliation is to *also* stamp the
version on the long-lived root Collection (a single PATCH on the upgrade path, as the spec already
prescribes) and treat the WikiLog stamp as informational. Recommended action: either (a) implement the
spec as written (marker on root Collection, the `update_object` PATCH the commit *removed* at the old
`bootstrap.py` collection branch), or (b) amend §Schema Compatibility + AC #13 / the v0.3.0–v0.4.0
ACs to name the WikiLog marker, with a Spec-writer sign-off, before v0.3.0 reads it.

### ADVISORY-2 — `update_object` PATCH upgrade path was deleted; upgrades now no-op the version stamp
The pre-commit code, on `is_upgrade`, PATCHed the root Collection to bring `wiki_schema_version`
forward. That branch is gone (`bootstrap.py:374-387` has no PATCH). The new design relies on the
*fresh* WikiLog stamping the new version. This is internally consistent with the WikiLog-marker
choice, but combined with SHOULD-FIX-1 it means: after a real 0.2.0→0.3.0 upgrade the space will hold
both an old-version WikiLog and a new-version WikiLog, and `_max_version` is what keeps the answer
correct. Functional, but fragile; folds into ADVISORY-1's recommendation.

### ADVISORY-3 — Test router is broadly permissive (acceptable, noted)
`_install_success_routes` (`test_bootstrap.py:73-125`) mocks `respx.get()`/`respx.post()` with
catch-all side-effects keyed on URL suffix. This is the right shape for the URL-aware contract, and
the dedicated `test_wiki_client.py::test_create_tag_posts_to_tags_endpoint_and_returns_dict`
(`test_wiki_client.py:128-141`) asserts the exact `/properties/{id}/tags` path + `tag` envelope, so
the endpoint correction is genuinely pinned. No tautology there. The residual gap is SHOULD-FIX-3.

### ADVISORY-4 — Carry-forward of all R1 maintainer/live gates still applies
B3/B4/B5/A5 from impl-review-r1 remain Jan-owned. This commit *does* advance B5's "validate guessed
`wiki_client.py` REST endpoints" — they are now live-verified, not guessed — and "doctor strict
exit-0 / wiki-bootstrap demo against real Anytype" are now demonstrable (the `wiki-e2e-1` space is the
artifact). Recommend recording that in the pre-release notes.

---

## Things checked and found GOOD

- **Error-category mapping intact.** `wiki_bootstrap` wrapper still maps `ConnectError/ConnectTimeout/
  TransportError → [API ERROR]`, 404 → `[CONFIG ERROR] wiki_space_missing`, 403 → `[CONFIG ERROR]
  insufficient_token_scope` (`bootstrap.py:215-232`). AC #3/#4/#9 preserved.
- **Credential scrubbing intact.** `util.py` untouched by this commit; doctor still routes every probe
  URL through `util.scrub_credentials` for its messages (`doctor.py:79,135,153,183`). The new auth
  headers carry the key in a header, not the URL, so no new leak surface in error strings. AC #15 /
  CSO #5 unaffected.
- **`tags_skipped` / `properties_skipped` semantics correct.** Re-bootstrap union-only tag logic
  preserved (`bootstrap.py:337-348`); property skip now keyed off a pre-fetched `pre_existing_prop_keys`
  snapshot + per-run `seen_prop_keys` dedup (`bootstrap.py:305-329`) so a shared key
  (`wiki_domain_tags`) is reported once. AC #2/#5 covered by green tests `test_second_call_*` and
  `test_rebootstrap_with_new_tags_is_union_only`.
- **Real-API contract corrections verified live:** `plural_name`+`layout` on create-type; `name` on
  create-property; `/properties/{id}/tags` + required `color` + `tag` envelope; typed
  PropertyLinkWithValue array on create-object; `type_key "collection"`. All confirmed against the
  `wiki-e2e-1` space.
- **doctor improvements sound:** tag-insensitive ollama match (`doctor.py:214-215`), auth-headered
  probes (`doctor.py:43-58`), missing lock-dir → WARN not FAIL (`doctor.py:261-270`). The 401/403 →
  FAIL branch correctly stops a running-but-unauthorized Anytype from being misreported as down.

---

## Test result (verbatim)

```
$ uv run pytest -q
256 passed, 22 skipped, 3 xfailed in 2.07s
```
