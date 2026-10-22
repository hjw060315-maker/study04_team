"""공고 부록의 연습용 시나리오 3개를 서비스 로직으로 단계마다 확인한다."""
import json
import os

import pytest

from src import assign, auth, service
from tests.sqlite_db import SqliteDatabase

AB = {"PL": "기획자", "WP": "웹 프로그래머", "FD": "프론트엔드 디자이너", "TT": "테스터", "RW": "보고서 작성자", "PT": "발표자"}

EASY = ["PL;RW", "PL;PT", "PL;TT", "WP;FD", "WP", "WP;TT", "FD;PT", "TT;RW;PT"]
MID = ["PL;PT;TT", "PL;TT", "PL;RW", "PL", "WP;TT", "WP;FD", "WP", "WP;PT", "FD;WP", "TT;PL", "RW", "PT;RW;FD"]
HARD = ["PL;RW", "PL;PT", "PL;TT", "WP;PL", "WP;FD", "WP;RW", "FD;PT;TT", "FD;TT", "FD;WP", "TT;RW", "TT;PT",
        "TT;PL", "RW;PT;FD", "RW;TT", "PT;FD", "PT"]


def roster(base, rows):
    lines = ["student_no,name,main_role,sub_roles"]
    for i, spec in enumerate(rows, start=1):
        roles = [AB[r] for r in spec.split(";")]
        lines.append(f"{base + i},학생{i}({spec}),{roles[0]},{';'.join(roles[1:])}")
    return ("\ufeff" + "\n".join(lines) + "\n").encode("utf-8")


class World:
    last_result = None

    def __init__(self, base, rows, teams):
        self.db = SqliteDatabase()
        pw = os.environ.get("TEST_ADMIN_PW", "pw-admin")  # 실제 DB로 돌릴 때는 진짜 관리자 비밀번호를 쓴다
        auth.ensure_admin(self.db, pw)
        self.base = base
        self.admin = auth.login(self.db, "admin", pw)
        msg = service.admin_start(self.db, self.admin["id"], roster(base, rows), teams)
        assert msg.startswith("승인"), msg

    def user(self, n):
        return auth.login(self.db, str(self.base + n), "1234")

    def do(self, action, who, target):
        me = self.user(who)
        if action == "apply":
            return service.apply_to_team(self.db, me["id"], self.team_id(target))
        return service.cast_vote(self.db, me["id"], str(self.base + target), "찬성" if action == "yes" else "거부")

    def team_id(self, n):
        _, ctx = service.assignment_context(self.db)
        return next(t["id"] for t in ctx["teams"] if t["name"] == f"팀{n}")

    def run(self, steps):
        for action, who, target, expected in steps:
            msg = self.do(action, who, target)
            assert msg.startswith(expected), f"{action} {who}->{target}: 기대 {expected}, 실제 {msg}"

    def run_ai(self, ctx, via_ai):
        """배정안을 얻는다. 환경 변수 REAL_AI=1이면 가짜 대신 실제 OpenRouter 모델을 부른다."""
        if os.environ.get("REAL_AI") == "1":
            res = assign.run_assignment(ctx)
            World.last_result = res
            return res
        if via_ai:
            def fake(model, prompt, timeout):
                plan = assign.solve(ctx)
                names = {t["id"]: t["name"] for t in ctx["teams"]}
                no = {s["id"]: s["student_no"] for s in ctx["unassigned"]}
                return json.dumps({"assignments": [{"student_no": no[s], "team": names[t]} for s, t in plan.items()]})
            res = assign.run_assignment(ctx, call=fake, models=["m1", "m2", "m3"])
            assert res.source.startswith("AI 1차")
        else:
            res = assign.run_assignment(ctx, call=lambda *a: "", models=["m1", "m2", "m3"])
            assert res.source.startswith("앱이 직접")
        World.last_result = res
        return res

    def finish(self, via_ai):
        assert service.admin_close(self.db, self.admin["id"]).startswith("승인")
        state, ctx = service.assignment_context(self.db)
        res = self.run_ai(ctx, via_ai)
        assert res.plan is not None
        assert service.admin_confirm(self.db, self.admin["id"], res.plan).startswith("승인")
        state, ctx = service.assignment_context(self.db)
        assert ctx["unassigned"] == []
        for t in ctx["teams"]:
            from src import rules
            assert rules.validate_team(t["name"], t["members"]) == [], t["name"]
        return state


def test_easy():
    w = World(2026100, EASY, 3)
    w.run([("apply", 1, 1, "승인"), ("apply", 2, 2, "승인"), ("apply", 3, 3, "승인"),
           ("apply", 4, 1, "대기"), ("yes", 1, 4, "승인"),
           ("apply", 5, 2, "대기"), ("yes", 2, 5, "승인"),
           ("apply", 7, 1, "대기"), ("yes", 1, 7, "대기"), ("no", 4, 7, "거절"),
           ("apply", 6, 3, "대기"), ("yes", 3, 6, "승인")])
    w.finish(via_ai=True)


def test_middle():
    w = World(2026200, MID, 4)
    w.run([("apply", 1, 1, "승인"),
           ("apply", 5, 1, "대기"), ("yes", 1, 5, "승인"),
           ("apply", 2, 1, "막힘"),
           ("apply", 6, 2, "승인"),
           ("apply", 9, 2, "대기"), ("yes", 6, 9, "승인"),
           ("apply", 10, 2, "대기"), ("yes", 6, 10, "대기"), ("no", 9, 10, "거절"),
           ("apply", 3, 3, "승인"), ("apply", 11, 4, "승인"),
           ("apply", 12, 4, "대기"), ("apply", 12, 3, "막힘")])
    assert service.admin_close(w.db, w.admin["id"]).startswith("승인")
    state, ctx = service.assignment_context(w.db)
    names = {s["name"] for s in ctx["unassigned"]}
    assert "학생3(PL;RW)" in names and "학생11(RW)" in names
    app12 = [a for a in state["apps"] if a["student_id"] == w.user(12)["id"]][0]
    assert app12["status"] == "거절"
    assert w.do("apply", 2, 3).startswith("막힘")  # 마감
    res = w.run_ai(ctx, False)
    assert res.plan and service.admin_confirm(w.db, w.admin["id"], res.plan).startswith("승인")
    state, ctx = service.assignment_context(w.db)
    assert ctx["unassigned"] == []
    from src import rules
    assert all(rules.validate_team(t["name"], t["members"]) == [] for t in ctx["teams"])


def test_hard():
    w = World(2026300, HARD, 4)
    w.run([("apply", 1, 1, "승인"),
           ("apply", 4, 1, "대기"), ("yes", 1, 4, "승인"),
           ("apply", 7, 1, "대기"), ("yes", 1, 7, "대기"), ("yes", 4, 7, "승인"),
           ("apply", 2, 2, "승인"),
           ("apply", 8, 2, "대기"), ("yes", 2, 8, "승인"),
           ("apply", 5, 2, "대기"), ("apply", 6, 2, "대기"),
           ("yes", 2, 5, "대기"), ("yes", 8, 5, "승인"),
           ("yes", 2, 6, "대기"), ("yes", 8, 6, "대기"), ("yes", 5, 6, "거절"),
           ("apply", 11, 3, "승인"),
           ("apply", 15, 3, "대기"), ("yes", 11, 15, "승인"),
           ("apply", 14, 3, "막힘"),
           ("apply", 10, 4, "승인"),
           ("apply", 13, 1, "대기"), ("yes", 1, 13, "대기")])
    w.finish(via_ai=False)


def test_student_cannot_use_admin_and_wrong_password():
    w = World(2026100, EASY, 3)
    me = w.user(1)
    assert service.admin_close(w.db, me["id"]).startswith("막힘")
    assert service.admin_start(w.db, me["id"], roster(2026100, EASY), 3).startswith("막힘")
    assert auth.login(w.db, "2026101", "wrong") is None
    assert auth.login(w.db, "2026101", "") is None


def test_vote_rules_and_double_apply():
    w = World(2026100, EASY, 3)
    w.run([("apply", 1, 1, "승인"), ("apply", 4, 1, "대기")])
    assert w.do("apply", 4, 2).startswith("막힘")  # 결과를 기다리는 지원이 있음
    assert w.do("apply", 1, 2).startswith("막힘")  # 이미 팀이 있음
    assert w.do("yes", 2, 4).startswith("막힘")  # 우리 팀이 아님
    assert w.do("yes", 1, 4).startswith("승인")
    assert w.do("yes", 1, 4)  # 이미 결과가 난 지원


def test_roster_errors_and_password_hashed():
    w = World(2026100, EASY, 3)
    assert service.admin_start(w.db, w.admin["id"], b"a,b\n1,2\n", 3).startswith("막힘")
    bad = roster(2026100, EASY).replace("기획자".encode(), "대장".encode(), 1)
    assert service.admin_start(w.db, w.admin["id"], bad, 3).startswith("막힘")
    with w.db.tx() as t:
        rows = t.q("select password_hash from tf_students")
    assert all(r["password_hash"] != "1234" and r["password_hash"].startswith("$2") for r in rows)
    assert auth.login(w.db, "admin", "pw-admin")  # 명단을 다시 올려도 관리자 계정이 남는다
