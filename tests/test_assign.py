import json
import time

from src import assign
from tests.test_rules import stu


def ctx_basic():
    return {
        "teams": [{"id": 1, "name": "팀1", "members": [stu(1, "PL"), stu(2, "WP")]},
                  {"id": 2, "name": "팀2", "members": []}],
        "unassigned": [stu(3, "PL"), stu(4, "WP"), stu(5, "TT")],
    }


def good_answer(ctx):
    plan = assign.solve(ctx)
    by_id = {t["id"]: t["name"] for t in ctx["teams"]}
    no = {s["id"]: s["student_no"] for s in ctx["unassigned"]}
    return json.dumps({"assignments": [{"student_no": no[s], "team": by_id[t]} for s, t in plan.items()]})


def test_solve_and_validate():
    ctx = ctx_basic()
    plan = assign.solve(ctx)
    assert plan is not None and assign.validate_plan(ctx, plan) == []


def test_infeasible_has_reason_and_skips_ai():
    ctx = {"teams": [{"id": 1, "name": "팀1", "members": []}, {"id": 2, "name": "팀2", "members": []}],
           "unassigned": [stu(1, "PL"), stu(2, "TT"), stu(3, "FD"), stu(4, "PT")]}
    called = []
    res = assign.run_assignment(ctx, call=lambda *a: called.append(1))
    assert res.plan is None and not called
    assert any("웹 프로그래머" in r for r in res.reasons)


def test_ai_first_model_ok():
    ctx = ctx_basic()
    res = assign.run_assignment(ctx, models=["a", "b", "c"], call=lambda m, p, t: good_answer(ctx))
    assert res.source.startswith("AI 1차") and len(res.attempts) == 1


def test_fallback_chain_and_own_solver():
    ctx = ctx_basic()
    bad = json.dumps({"assignments": [{"student_no": "3", "team": "팀2"}]})  # 일부만 배정 -> 검사 불통과
    answers = {"a": "", "b": bad, "c": "not json"}
    logs = []
    res = assign.run_assignment(ctx, models=["a", "b", "c"], call=lambda m, p, t: answers[m],
                                on_log=lambda *a: logs.append(a))
    assert res.source.startswith("앱이 직접 배정")
    assert [a[2] for a in res.attempts] == ["응답 형식 오류", "검사 불통과", "응답 형식 오류"]
    assert assign.validate_plan(ctx, res.plan) == [] and len(logs) == 3


def test_second_model_after_exception_and_timeout():
    ctx = ctx_basic()

    def call(m, p, t):
        if m == "a":
            raise RuntimeError("HTTP 429")
        if m == "b":
            time.sleep(5)
        return good_answer(ctx)

    res = assign.run_assignment(ctx, models=["a", "b", "c"], call=call, timeout=1)
    assert [a[2] for a in res.attempts] == ["호출 오류", "시간 초과", "성공"]
    assert res.source.startswith("AI 3차")


def test_deadline_counts_total_time():
    start = time.monotonic()
    try:
        assign.call_with_deadline(lambda: time.sleep(10), 1)
    except TimeoutError:
        pass
    assert time.monotonic() - start < 3


def test_moving_existing_student_is_rejected():
    ctx = ctx_basic()
    text = json.dumps({"assignments": [{"student_no": "1", "team": "팀2"}]})
    try:
        assign.parse_response(text, ctx)
        assert False
    except ValueError:
        pass
