"""지원, 투표, 승인, 마감, 명단 올리기, 배정 확정. 안내 글은 '승인/대기/거절/막힘'으로 시작한다."""
import csv
import io

from . import assign, rules
from .auth import ADMIN_NO, hash_password
from .db import is_integrity_error

STUDENT_PASSWORD = "1234"
PENDING, APPROVED, REJECTED = "대기", "승인", "거절"
YES, NO = "찬성", "거부"


# ---------------------------------------------------------------- 상태 읽기

def load_state(t):
    """화면과 규칙 검사에 필요한 현재 상태를 한꺼번에 읽는다."""
    students = {}
    for r in t.q("select id, student_no, name, main_role from tf_students where is_admin = false order by student_no"):
        students[r["id"]] = {"id": r["id"], "student_no": r["student_no"], "name": r["name"],
                             "main": r["main_role"], "subs": []}
    for r in t.q("select student_id, role from tf_student_sub_roles order by role"):
        if r["student_id"] in students:
            students[r["student_id"]]["subs"].append(r["role"])
    teams = {}
    for r in t.q("select id, name from tf_teams order by id"):
        teams[r["id"]] = {"id": r["id"], "name": r["name"], "no": int(r["name"].replace("팀", "") or 0), "members": []}
    member_team = {}
    for r in t.q("select team_id, student_id from tf_members order by team_id, slot_no"):
        if r["student_id"] in students and r["team_id"] in teams:
            teams[r["team_id"]]["members"].append(students[r["student_id"]])
            member_team[r["student_id"]] = r["team_id"]
    apps = t.q("select id, team_id, student_id, status, reason from tf_applications order by id")
    votes = {}
    for r in t.q("select application_id, voter_id, vote from tf_votes"):
        votes.setdefault(r["application_id"], {})[r["voter_id"]] = r["vote"]
    rows = t.q("select value from tf_settings where key = 'closed'")
    closed = bool(rows) and rows[0]["value"] == "1"
    return {"students": students, "teams": teams, "member_team": member_team,
            "apps": apps, "votes": votes, "closed": closed}


def pending_app_of(state, student_id):
    for a in state["apps"]:
        if a["student_id"] == student_id and a["status"] == PENDING:
            return a
    return None


def unassigned_students(state):
    return [s for s in state["students"].values() if s["id"] not in state["member_team"]]


def team_label_no(name):
    return int(name.replace("팀", ""))


# ---------------------------------------------------------------- 지원

def _first_free_slot(t, team_id):
    used = {r["slot_no"] for r in t.q("select slot_no from tf_members where team_id = %s", (team_id,))}
    for slot in range(1, rules.MAX_SIZE + 1):
        if slot not in used:
            return slot
    return None


def _add_member(t, team_id, student_id):
    slot = _first_free_slot(t, team_id)
    if slot is None:
        return False
    t.x("insert into tf_members (team_id, slot_no, student_id) values (%s, %s, %s)", (team_id, slot, student_id))
    return True


def apply_to_team(db, student_id, team_id):
    """지원 단추. (안내 글) 반환."""
    try:
        with db.tx() as t:
            state = load_state(t)
            me = state["students"].get(student_id)
            team = state["teams"].get(team_id)
            if me is None or team is None:
                return "막힘: 지원할 수 없는 대상임"
            if state["closed"]:
                return "막힘: 모집이 마감됨"
            if student_id in state["member_team"]:
                return "막힘: 이미 팀이 있음"
            if pending_app_of(state, student_id):
                return "막힘: 결과를 기다리는 지원이 있음"
            reason = rules.check_join(team["members"], me)
            if reason:
                return f"막힘: {reason}"
            if not team["members"]:
                _add_member(t, team_id, student_id)
                t.x("insert into tf_applications (team_id, student_id, status, reason) values (%s, %s, %s, %s)",
                    (team_id, student_id, APPROVED, "빈 팀에 지원"))
                return f"승인: {team['name']}에 들어감(빈 팀이라 바로 승인)"
            t.x("insert into tf_applications (team_id, student_id, status) values (%s, %s, %s)",
                (team_id, student_id, PENDING))
            return f"대기: {team['name']} 팀원의 투표를 기다리는 중"
    except Exception as e:  # noqa: BLE001
        if is_integrity_error(e):
            return "막힘: 방금 다른 학생이 먼저 들어가 자리가 사라짐"
        raise


# ---------------------------------------------------------------- 투표와 승인

def _settle(t, state, app):
    """대기 중인 지원 하나의 투표를 모아 거절/승인/대기를 정한다. (상태, 안내) 반환."""
    team = state["teams"][app["team_id"]]
    applicant = state["students"][app["student_id"]]
    votes = state["votes"].get(app["id"], {})
    if any(v == NO for v in votes.values()):
        t.x("update tf_applications set status = %s, reason = %s where id = %s", (REJECTED, "팀원이 거부함", app["id"]))
        return REJECTED, "팀원이 거부함"
    voters = [m["id"] for m in team["members"]]
    if not all(votes.get(v) == YES for v in voters):
        return PENDING, "아직 투표하지 않은 팀원이 있음"
    # 승인 직전 재검사: 앞의 지원이 먼저 승인되어 팀이 바뀌었을 수 있다
    reason = rules.check_join(team["members"], applicant)
    if reason:
        t.x("update tf_applications set status = %s, reason = %s where id = %s",
            (REJECTED, f"승인 직전 검사: {reason}", app["id"]))
        return REJECTED, f"승인 직전 검사에서 규칙을 어김({reason})"
    if not _add_member(t, team["id"], applicant["id"]):
        t.x("update tf_applications set status = %s, reason = %s where id = %s",
            (REJECTED, "승인 직전 검사: 팀이 꽉 참", app["id"]))
        return REJECTED, "승인 직전 검사에서 규칙을 어김(팀이 꽉 참)"
    t.x("update tf_applications set status = %s where id = %s", (APPROVED, app["id"]))
    return APPROVED, f"{team['name']}의 팀원이 됨"


def cast_vote(db, voter_id, applicant_no, vote):
    """찬성/거부 단추. 지원자 학번으로 그 지원을 찾는다. (안내 글) 반환."""
    try:
        with db.tx() as t:
            state = load_state(t)
            applicant = next((s for s in state["students"].values() if s["student_no"] == applicant_no), None)
            if applicant is None:
                return "막힘: 없는 지원임"
            app = pending_app_of(state, applicant["id"])
            if state["closed"]:
                return "막힘: 모집이 마감됨"
            if app is None:
                last = [a for a in state["apps"] if a["student_id"] == applicant["id"]]
                status = last[-1]["status"] if last else "없음"
                return f"{status}: 이미 결과가 나온 지원임" if last else "막힘: 없는 지원임"
            if state["member_team"].get(voter_id) != app["team_id"]:
                return "막힘: 우리 팀에 들어온 지원이 아님"
            votes = state["votes"].setdefault(app["id"], {})
            if voter_id in votes:
                return f"막힘: 이미 투표했음(내 투표: {votes[voter_id]})"
            votes[voter_id] = vote
            t.x("insert into tf_votes (application_id, voter_id, vote) values (%s, %s, %s)",
                (app["id"], voter_id, vote))
            status, note = _settle(t, state, app)
            return f"{status}: {applicant['name']}의 지원 - {note}"
    except Exception as e:  # noqa: BLE001
        if is_integrity_error(e):
            return "막힘: 방금 다른 변경이 먼저 반영됨. 새로 고친 뒤 다시 확인해 주세요"
        raise


# ---------------------------------------------------------------- 관리자 기능

def _require_admin(t, actor_id):
    rows = t.q("select is_admin from tf_students where id = %s", (actor_id,))
    return bool(rows) and bool(rows[0]["is_admin"])


def parse_roster(raw):
    """명단 CSV(BOM 있는 UTF-8도 읽음)를 학생 목록으로 바꾼다. 틀리면 ValueError."""
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError("UTF-8 파일이 아님")
    reader = csv.reader(io.StringIO(text))
    rows = [r for r in reader if any(c.strip() for c in r)]
    if not rows:
        raise ValueError("빈 파일임")
    header = [c.strip() for c in rows[0]]
    if header != ["student_no", "name", "main_role", "sub_roles"]:
        raise ValueError("첫 줄이 student_no,name,main_role,sub_roles 가 아님")
    out, seen = [], set()
    for i, r in enumerate(rows[1:], start=2):
        r = [c.strip() for c in r]
        if len(r) != 4:
            raise ValueError(f"{i}번째 줄의 열이 {len(r)}개임(4개여야 함)")
        no, name, main, subs_raw = r
        subs = [s.strip() for s in subs_raw.split(";") if s.strip()]
        if not no or not name:
            raise ValueError(f"{i}번째 줄에 학번이나 이름이 비어 있음")
        if no == ADMIN_NO:
            raise ValueError("학번 admin은 쓸 수 없음")
        if no in seen:
            raise ValueError(f"학번 {no}가 두 번 나옴")
        seen.add(no)
        if main not in rules.ROLES:
            raise ValueError(f"{i}번째 줄의 주 역할 '{main}'이 6개 역할이 아님")
        if len(subs) > 2 or any(s not in rules.ROLES for s in subs) or len(set(subs)) != len(subs):
            raise ValueError(f"{i}번째 줄의 보조 역할이 틀림")
        out.append({"student_no": no, "name": name, "main": main, "subs": subs})
    if not out:
        raise ValueError("학생이 한 명도 없음")
    return out


def admin_start(db, actor_id, raw, team_count):
    try:
        students = parse_roster(raw)
    except ValueError as e:
        return f"막힘: 명단을 읽을 수 없음({e})"
    if not 1 <= team_count <= 20:
        return "막힘: 팀 수는 1~20이어야 함"
    pw_hash = hash_password(STUDENT_PASSWORD, rounds=8)
    with db.tx() as t:
        if not _require_admin(t, actor_id):
            return "막힘: 관리자만 할 수 있음"
        for table in ("tf_votes", "tf_applications", "tf_members", "tf_student_sub_roles"):
            t.x(f"delete from {table}")
        t.x("delete from tf_students where is_admin = false")
        t.x("delete from tf_teams")
        for s in students:
            row = t.q(
                "insert into tf_students (student_no, name, main_role, password_hash, is_admin)"
                " values (%s, %s, %s, %s, false) returning id",
                (s["student_no"], s["name"], s["main"], pw_hash),
            )
            for role in s["subs"]:
                t.x("insert into tf_student_sub_roles (student_id, role) values (%s, %s)", (row[0]["id"], role))
        for n in range(1, team_count + 1):
            t.x("insert into tf_teams (name) values (%s)", (f"팀{n}",))
        t.x("delete from tf_settings where key = 'closed'")
        t.x("insert into tf_settings (key, value) values ('closed', '0')")
    return f"승인: 학생 {len(students)}명과 빈 팀 {team_count}개로 처음 상태를 만듦"


def admin_close(db, actor_id):
    with db.tx() as t:
        if not _require_admin(t, actor_id):
            return "막힘: 관리자만 할 수 있음"
        state = load_state(t)
        if state["closed"]:
            return "막힘: 이미 마감됨"
        if not state["teams"]:
            return "막힘: 명단을 먼저 올려야 함"
        pending = [a for a in state["apps"] if a["status"] == PENDING]
        for a in pending:
            t.x("update tf_applications set status = %s, reason = %s where id = %s", (REJECTED, "모집 마감", a["id"]))
        freed = 0
        for team in state["teams"].values():
            if len(team["members"]) == 1:
                t.x("delete from tf_members where team_id = %s", (team["id"],))
                freed += 1
        t.x("delete from tf_settings where key = 'closed'")
        t.x("insert into tf_settings (key, value) values ('closed', '1')")
    return f"승인: 모집을 마감함(대기 지원 {len(pending)}건 거절, 1명뿐인 팀 {freed}개 해체)"


def assignment_context(db):
    with db.tx() as t:
        state = load_state(t)
    teams = [{"id": tm["id"], "name": tm["name"], "members": tm["members"]} for tm in state["teams"].values()]
    return state, {"teams": teams, "unassigned": unassigned_students(state)}


def log_ai_call(db, attempt, model, outcome, elapsed, detail):
    try:
        with db.tx() as t:
            t.x("insert into tf_ai_logs (attempt, model, outcome, elapsed_sec, detail) values (%s, %s, %s, %s, %s)",
                (attempt, model, outcome, elapsed, detail[:500]))
    except Exception:  # noqa: BLE001  기록 실패가 배정을 막지 않는다
        pass


def admin_confirm(db, actor_id, plan):
    """검사를 통과한 배정안을 다시 검사한 뒤 저장한다."""
    if plan is None:
        return "막힘: 확정할 배정안이 없음"
    with db.tx() as t:
        if not _require_admin(t, actor_id):
            return "막힘: 관리자만 할 수 있음"
        state = load_state(t)
        if not state["closed"]:
            return "막힘: 모집을 먼저 마감해야 함"
        ctx = {"teams": [{"id": tm["id"], "name": tm["name"], "members": tm["members"]}
                         for tm in state["teams"].values()],
               "unassigned": unassigned_students(state)}
        errors = assign.validate_plan(ctx, plan)
        if errors:
            return "막힘: 배정안이 규칙을 어김(" + "; ".join(errors) + ")"
        for sid, tid in plan.items():
            if not _add_member(t, tid, sid):
                raise RuntimeError("자리가 없음")
    return f"승인: 배정안을 확정함({len(plan)}명)"
