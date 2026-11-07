"""Batched contradiction checks of one ingest (Aldeia-IT/aldeia-box#1485 D3).

All checks of a run go to the model in one call that returns a verdict per
check; a missing or garbled verdict falls back to that check's single-call
path (``detect_contradictions``).
"""

import json

import httpx
import pytest

from anytype_llm_wiki.wiki import ingest


def _check(n: int, peers: list[str], kind: str = "entity") -> dict:
    return {
        "check_id": f"check_{n}",
        "obj_id": f"obj-{n}",
        "name": f"Object {n}",
        "target": {"id": f"obj-{n}", "properties": []},
        "kind": kind,
        "new_facts": f"claim {n}",
        "candidates": [
            {"object_id": p, "name": f"Peer {p}", "facts": f"facts of {p}"} for p in peers
        ],
    }


class _Model:
    """Stand-in for ``_call_ollama_prompt``: records prompts, answers in turn."""

    def __init__(self, *answers):
        self.prompts: list[str] = []
        self.answers = list(answers)

    def __call__(self, base, prompt):
        self.prompts.append(prompt)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer, None

    @property
    def batch_prompts(self) -> list[str]:
        return [p for p in self.prompts if "<checks>" in p]

    @property
    def single_prompts(self) -> list[str]:
        return [p for p in self.prompts if "<new_claim>" in p]


@pytest.fixture
def model(monkeypatch):
    def install(*answers):
        fake = _Model(*answers)
        monkeypatch.setattr(ingest, "_call_ollama_prompt", fake)
        return fake

    return install


def _judge(checks):
    """Each check's contradictions (or its exception); ``_judge_full`` keeps duplicates."""
    return {
        cid: out if isinstance(out, Exception) else out["contradictions"]
        for cid, out in _judge_full(checks).items()
    }


def _judge_full(checks):
    return ingest._judge_contradiction_checks(checks, "space", None, None)


def _verdict(contradictions, duplicates=()):
    return {"contradictions": list(contradictions), "duplicates": list(duplicates)}


def _batch_answer(*entries):
    return {"results": [{"check_id": cid, "contradictions": c} for cid, c in entries]}


class TestBatchedVerdicts:
    def test_all_checks_of_a_run_take_one_model_call(self, model):
        fake = model(_batch_answer(
            ("check_1", [{"object_id": "p1", "reason": "dates differ"}]),
            ("check_2", []),
            ("check_3", [{"object_id": "p3", "reason": "names differ"}]),
        ))
        checks = [_check(1, ["p1"]), _check(2, ["p2"]), _check(3, ["p3", "p4"])]

        outcomes = _judge(checks)

        assert len(fake.prompts) == 1
        payload = fake.prompts[0].split("<checks>\n", 1)[1].split("\n</checks>", 1)[0]
        sent = json.loads(payload)
        assert [c["check_id"] for c in sent] == ["check_1", "check_2", "check_3"]
        assert sent[2] == {
            "check_id": "check_3",
            "new_claim": "claim 3",
            "candidates": checks[2]["candidates"],
        }
        assert outcomes == {
            "check_1": [{"object_id": "p1", "reason": "dates differ"}],
            "check_2": [],
            "check_3": [{"object_id": "p3", "reason": "names differ"}],
        }

    def test_each_verdict_maps_to_its_own_check_and_its_own_candidates(self, model):
        # p2 is a real candidate of check_2 only: under check_1 it is a
        # hallucinated id for that object and must be dropped (SG-2).
        model(_batch_answer(
            ("check_2", [{"object_id": "p2", "reason": "r2"}]),
            ("check_1", [{"object_id": "p2", "reason": "wrong check"},
                         {"object_id": "p1", "reason": "r1"}, "junk"]),
        ))

        outcomes = _judge([_check(1, ["p1"]), _check(2, ["p2"])])

        assert outcomes["check_1"] == [{"object_id": "p1", "reason": "r1"}]
        assert outcomes["check_2"] == [{"object_id": "p2", "reason": "r2"}]

    def test_one_check_uses_the_single_prompt_unchanged(self, model):
        fake = model({"contradictions": [{"object_id": "p1", "reason": "r"}]})

        outcomes = _judge([_check(1, ["p1"])])

        assert fake.batch_prompts == []
        assert len(fake.single_prompts) == 1
        assert "claim 1" in fake.single_prompts[0]
        assert outcomes == {"check_1": [{"object_id": "p1", "reason": "r"}]}

    def test_checks_without_candidates_make_no_model_call(self, model):
        fake = model()

        outcomes = _judge([_check(1, []), _check(2, [])])

        assert fake.prompts == []
        assert outcomes == {"check_1": [], "check_2": []}

    def test_checks_that_do_not_fit_one_prompt_are_split(self, model, monkeypatch):
        big = "x" * 900
        checks = [_check(n, [f"p{n}"]) for n in (1, 2, 3)]
        for c in checks:
            c["new_facts"] = big
        # ~2 checks per prompt: the batch prompt template is ~1.6 KB.
        share = ingest.CHARS_PER_TOKEN * ingest._BATCH_BUDGET_SHARE
        budget_tokens = int((len(ingest._batch_prompt(checks[:2])) + 10) / share) + 1
        monkeypatch.setenv("WIKI_EXTRACT_MAX_INPUT_TOKENS", str(budget_tokens))
        fake = model(
            _batch_answer(("check_1", []), ("check_2", [])),
            {"contradictions": []},
        )

        outcomes = _judge(checks)

        assert len(fake.batch_prompts) == 1 and len(fake.single_prompts) == 1
        assert set(outcomes) == {"check_1", "check_2", "check_3"}


    def test_portuguese_heavy_batches_stay_under_the_reduced_budget(self, monkeypatch):
        # Accented text is not escaped to \\uXXXX in the prompt, and packing
        # leaves headroom below the full chars-per-token budget.
        checks = [_check(n, [f"p{n}"]) for n in range(1, 9)]
        for c in checks:
            c["new_facts"] = "açúcar, coração, não, João " * 30
        budget_tokens = 2000
        monkeypatch.setenv("WIKI_EXTRACT_MAX_INPUT_TOKENS", str(budget_tokens))

        batches = ingest._pack_contradiction_batches(checks)

        limit = budget_tokens * ingest.CHARS_PER_TOKEN * ingest._BATCH_BUDGET_SHARE
        assert len(batches) > 1
        assert all(len(ingest._batch_prompt(b)) <= limit for b in batches)
        assert "\\u00e7" not in ingest._batch_prompt(batches[0])
        assert "açúcar" in ingest._batch_prompt(batches[0])

    def test_non_string_ids_in_a_batch_answer_are_skipped(self, model):
        fake = model({"results": [
            {"check_id": ["x"], "contradictions": []},
            {"check_id": "check_1", "contradictions": [
                {"object_id": ["p1"], "reason": "r"}, {"object_id": "p1", "reason": "r"}]},
            {"check_id": "check_2", "contradictions": []},
        ]})

        outcomes = _judge([_check(1, ["p1"]), _check(2, ["p2"])])

        assert outcomes == {"check_1": [{"object_id": "p1", "reason": "r"}], "check_2": []}
        assert len(fake.prompts) == 1


class TestFallbackToSingleCall:
    def test_a_missing_verdict_falls_back_for_that_check_only(self, model):
        fake = model(
            _batch_answer(("check_1", [{"object_id": "p1", "reason": "r1"}])),
            {"contradictions": [{"object_id": "p2", "reason": "single"}]},
        )

        outcomes = _judge([_check(1, ["p1"]), _check(2, ["p2"])])

        assert len(fake.batch_prompts) == 1
        assert len(fake.single_prompts) == 1
        assert "claim 2" in fake.single_prompts[0] and "facts of p2" in fake.single_prompts[0]
        assert outcomes["check_1"] == [{"object_id": "p1", "reason": "r1"}]
        assert outcomes["check_2"] == [{"object_id": "p2", "reason": "single"}]

    @pytest.mark.parametrize("entry", [
        {"check_id": "check_2", "contradictions": "p2 contradicts"},
        {"check_id": "check_2"},
        "check_2",
    ])
    def test_a_garbled_verdict_falls_back(self, model, entry):
        fake = model(
            {"results": [{"check_id": "check_1", "contradictions": []}, entry]},
            {"contradictions": []},
        )

        outcomes = _judge([_check(1, ["p1"]), _check(2, ["p2"])])

        assert len(fake.single_prompts) == 1 and "claim 2" in fake.single_prompts[0]
        assert outcomes == {"check_1": [], "check_2": []}

    def test_two_verdicts_for_one_check_fall_back(self, model):
        fake = model(
            _batch_answer(("check_1", []), ("check_2", []),
                          ("check_2", [{"object_id": "p2", "reason": "r"}])),
            {"contradictions": [{"object_id": "p2", "reason": "single"}]},
        )

        outcomes = _judge([_check(1, ["p1"]), _check(2, ["p2"])])

        assert len(fake.single_prompts) == 1
        assert outcomes["check_2"] == [{"object_id": "p2", "reason": "single"}]

    @pytest.mark.parametrize("answer", [None, {"contradictions": []}, {"results": "none"}])
    def test_an_unparseable_batch_answer_falls_back_for_every_check(self, model, answer):
        fake = model(answer, {"contradictions": []}, {"contradictions": []})

        outcomes = _judge([_check(1, ["p1"]), _check(2, ["p2"])])

        assert len(fake.batch_prompts) == 1 and len(fake.single_prompts) == 2
        assert outcomes == {"check_1": [], "check_2": []}

    def test_a_failed_batch_call_falls_back_and_keeps_each_checks_failure(self, model):
        err = httpx.ReadTimeout("slow")
        fake = model(err, {"contradictions": []}, httpx.ConnectError("down"))

        outcomes = _judge([_check(1, ["p1"]), _check(2, ["p2"])])

        assert len(fake.prompts) == 3
        assert outcomes["check_1"] == []
        assert isinstance(outcomes["check_2"], httpx.ConnectError)


class TestRunContradictionChecks:
    """The per-object effect of a verdict: warning, links and count as before."""

    @pytest.fixture
    def writes(self, monkeypatch):
        state: dict[str, list[str]] = {}
        patches: list[tuple[str, list[str]]] = []

        def patch(client, space_id, obj_id, key, ids):
            assert key == "wiki_contradictions"
            patches.append((obj_id, list(ids)))
            state[obj_id] = list(ids)

        class Reader:
            def get_object(self, space_id, obj_id):
                return {"id": obj_id, "properties": [
                    {"key": "wiki_contradictions", "objects": list(state.get(obj_id, []))}
                ]}

        monkeypatch.setattr(ingest, "_patch_relation", patch)
        return state, patches, Reader()

    def test_verdicts_become_links_warnings_and_counts(self, monkeypatch, writes):
        state, _patches, reader = writes
        monkeypatch.setattr(ingest, "_judge_contradiction_checks", lambda *a: {
            "check_1": _verdict([{"object_id": "p1", "reason": "r"}]),
            "check_2": httpx.ConnectError("down"),
            "check_3": _verdict([]),
        })
        result = {"warnings": [], "contradictions_detected": 0}
        checks = [_check(1, ["p1"]), _check(2, ["p2"], kind="concept"), _check(3, ["p3"])]

        status, notes = ingest._run_contradiction_checks(checks, "space", None, reader, result)

        assert (status, notes) == (None, [])
        assert result["contradictions_detected"] == 1
        assert result["warnings"] == ["contradiction_detection_degraded:concept"]
        assert state == {"obj-1": ["p1"], "p1": ["obj-1"]}

    def test_a_later_check_keeps_links_an_earlier_check_wrote_to_it(self, monkeypatch, writes):
        # obj-1 flags obj-2 (B-side writes obj-2 -> [obj-1]); obj-2's in-memory
        # target was read before that write. Its own link to p2 must keep obj-1.
        state, _patches, reader = writes
        monkeypatch.setattr(ingest, "_judge_contradiction_checks", lambda *a: {
            "check_1": _verdict([{"object_id": "obj-2", "reason": "r"}]),
            "check_2": _verdict([{"object_id": "obj-1", "reason": "r"},
                                 {"object_id": "p2", "reason": "r"}]),
        })
        result = {"warnings": [], "contradictions_detected": 0}
        checks = [_check(1, ["obj-2"]), _check(2, ["obj-1", "p2"])]

        ingest._run_contradiction_checks(checks, "space", None, reader, result)

        assert state["obj-2"] == ["obj-1", "p2"]
        assert state["obj-1"] == ["obj-2"]
        # obj-2 -> obj-1 was already written by check_1's B-side: not a new link.
        assert result["contradictions_detected"] == 2


    def test_a_failing_link_write_makes_the_ingest_partial(self, monkeypatch, writes):
        _state, _patches, reader = writes

        def boom(*args, **kwargs):
            raise httpx.ConnectError("write down")

        monkeypatch.setattr(ingest, "_write_contradiction_links", boom)
        monkeypatch.setattr(ingest, "_judge_contradiction_checks", lambda *a: {
            "check_1": _verdict([{"object_id": "p1", "reason": "r"}]),
        })
        result = {"warnings": [], "contradictions_detected": 0}

        status, _notes = ingest._run_contradiction_checks(
            [_check(1, ["p1"])], "space", None, reader, result
        )

        assert status == "partial"
        assert len(result["warnings"]) == 1
        assert result["warnings"][0].startswith("object_failed: 'Object 1'")
        assert result["contradictions_detected"] == 0


class TestBatchPromptPreamble:
    """AC-10 for the batch prompt: the anti-injection preamble is in the file and
    in the OSError fallback."""

    def test_prompt_file_and_fallback_carry_the_preamble(self, monkeypatch, tmp_path):
        text = ingest._load_contradiction_batch_prompt()
        assert "untrusted DATA" in text and "{{CHECKS}}" in text
        monkeypatch.setattr(ingest, "_CONTRADICTION_BATCH_PROMPT_PATH", tmp_path / "missing.md")
        fallback = ingest._load_contradiction_batch_prompt()
        assert "untrusted DATA" in fallback and "{{CHECKS}}" in fallback
