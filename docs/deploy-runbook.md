# Operational deploy / upgrade runbook

This runbook covers the **operational** side of shipping a new wiki schema version
to running spaces — distinct from [`releasing.md`](releasing.md), which covers
publishing the package to PyPI. Follow this whenever a release bumps
`WIKI_SCHEMA_VERSION` (`src/anytype_llm_wiki/wiki/types_schema.py`).

## Golden rule: re-bootstrap every space before linting

After upgrading the wiki schema, **re-running `wiki_bootstrap` is REQUIRED (not
optional) for every existing space** — and it MUST run **before** `wiki_lint` on
that space.

```bash
uv run anytype-llm-wiki wiki-bootstrap --space-id <your-space-id>
```

`wiki_bootstrap` is idempotent and non-destructive. As of schema **0.4.2** it also
**reconciles** declared properties onto existing types: it reads each live type,
computes the declared-but-missing properties, and links them on with a single
union `update_type` PATCH (the union of the live user properties plus the missing
declared ones — never the bare delta, because Anytype's `update-type` REPLACES the
property set). Reconciled types are reported in the result's `types_reconciled`
section.

### Why the ordering is load-bearing

A `wiki_lint` run on a space that has **not** been re-bootstrapped strands that
space in an **un-clearable `critical`** state: concept contradictions fire
`critical`, but without `wiki_last_reviewed` on `wiki_concept` there is no field to
set to resolve them. The lint gate and the bootstrap reconcile ship together for
exactly this reason. Sequence every upgrade as:

1. Deploy the new package version.
2. Re-run `wiki_bootstrap` on **every** space.
3. Only then run `wiki_lint`.

See [`MIGRATIONS.md`](../MIGRATIONS.md) for the per-version schema notes.

## Durably capture the reconcile audit log

The reconcile path emits an **INFO-level audit log line immediately before each
destructive `update_type` PATCH** (the SG-e audit log):

```
wiki_reconcile type=<type_key> adding=<sorted missing keys> union_keys=<full union keys>
```

Under Anytype's replace-not-merge semantics a malformed `update_type` PATCH could
drop user properties across every Object of that type — a high blast-radius event.
The deployment **MUST capture this `wiki_reconcile ...` log line durably** (ship it
to the central log store / retain it with the bootstrap run output) so that, if a
corruption event ever occurs, the exact union sent for each type is reconstructable
post-hoc. Do not rely solely on ephemeral console output of the bootstrap command.
