"""팀 편성 웹 앱. 화면 요소의 key는 공고 2.7절 표를 그대로 따른다."""
import sys
import traceback
from pathlib import Path

import streamlit as st

from src import assign, auth, service
from src.config import get_secret
from src.db import create_database

st.set_page_config(page_title="팀 편성", page_icon="👥", layout="wide")

SCHEMA_PATH = Path(__file__).parent / "schema.sql"
GENERIC_ERROR = "막힘: 서버에서 오류가 났음. 잠시 뒤 다시 시도해 주세요"


@st.cache_resource(show_spinner="DB에 연결하는 중…")
def get_db():
    """연결은 한 번만 만들고 모든 화면이 다시 쓴다. 테이블과 관리자 계정도 여기서 준비한다."""
    password = get_secret("ADMIN_PASSWORD")
    if not password:
        raise RuntimeError("ADMIN_PASSWORD가 없음")
    db = create_database()
    with db.tx() as t:
        t.x(SCHEMA_PATH.read_text(encoding="utf-8"))
    auth.ensure_admin(db, password)
    return db


def safe(fn, *args):
    """DB 오류의 자세한 내용은 서버 로그에만 남기고 화면에는 짧은 안내만 보인다."""
    try:
        return fn(*args)
    except Exception:  # noqa: BLE001
        traceback.print_exc(file=sys.stderr)
        return GENERIC_ERROR


def set_result(msg):
    st.session_state["result"] = msg


# ---------------------------------------------------------------- 로그인

def render_login(db):
    st.title("팀 편성")
    with st.form("login_form"):
        no = st.text_input("학번", key="login_student_no")
        pw = st.text_input("비밀번호", type="password", key="login_password")
        submitted = st.form_submit_button("로그인", key="login_submit")
    if submitted:
        try:
            user = auth.login(db, no, pw)
        except Exception:  # noqa: BLE001
            traceback.print_exc(file=sys.stderr)
            st.error("서버에서 오류가 났음. 잠시 뒤 다시 시도해 주세요")
            return
        if user is None:
            st.error("로그인 실패: 학번이나 비밀번호가 틀림")
        else:
            st.session_state["user"] = user
            st.session_state["result"] = ""
            st.session_state.pop("plan", None)
            st.rerun()


# ---------------------------------------------------------------- 팀 현황 (5초마다 자동 갱신)

def member_line(m):
    subs = ", ".join(m["subs"]) if m["subs"] else "없음"
    return f"{m['name']} — 주 역할: {m['main']} / 보조 역할: {subs}"


@st.fragment(run_every=5)
def render_board(db, user):
    try:
        with db.tx() as t:
            state = service.load_state(t)
    except Exception:  # noqa: BLE001
        traceback.print_exc(file=sys.stderr)
        st.warning("현황을 불러오지 못함. 잠시 뒤 자동으로 다시 시도함")
        return

    is_admin = user["is_admin"]
    me = user["id"]
    my_team = state["member_team"].get(me)
    my_pending = service.pending_app_of(state, me)
    can_apply = not is_admin and not state["closed"] and my_team is None and my_pending is None
    st.subheader("팀 목록" + (" (모집 마감됨)" if state["closed"] else ""))

    if not is_admin:
        if my_team is None:
            st.caption("아직 팀이 없음")
        mine = [a for a in state["apps"] if a["student_id"] == me]
        if mine:
            last = mine[-1]
            st.caption(f"내 지원: {state['teams'][last['team_id']]['name']} — {last['status']}"
                       + (f" ({last['reason']})" if last["reason"] and last["status"] == "거절" else ""))

    cols = st.columns(2)
    for i, team in enumerate(sorted(state["teams"].values(), key=lambda x: x["no"])):
        with cols[i % 2]:
            with st.container(key=f"team_{team['no']}", border=True):
                mark = " (내 팀)" if team["id"] == my_team else ""
                st.markdown(f"**{team['name']}{mark}** — {len(team['members'])}/4명")
                if team["members"]:
                    for m in team["members"]:
                        st.write(member_line(m))
                else:
                    st.caption("빈 팀")
                if can_apply:
                    if st.button(f"{team['name']}에 지원", key=f"apply_{team['no']}"):
                        set_result(safe(service.apply_to_team, db, me, team["id"]))
                        st.rerun()
                if team["id"] == my_team and not is_admin:
                    for app in state["apps"]:
                        if app["team_id"] != team["id"] or app["status"] != "대기":
                            continue
                        who = state["students"][app["student_id"]]
                        votes = state["votes"].get(app["id"], {})
                        st.markdown(f"**지원자:** {member_line(who)}")
                        st.caption("투표 현황: " + (", ".join(
                            f"{state['students'][v]['name']} {votes[v]}" for v in votes) or "아직 없음"))
                        if me in votes:
                            st.write(f"내 투표: {votes[me]}")
                        elif not state["closed"]:
                            c1, c2 = st.columns(2)
                            if c1.button("찬성", key=f"vote_yes_{who['student_no']}"):
                                set_result(safe(service.cast_vote, db, me, who["student_no"], "찬성"))
                                st.rerun()
                            if c2.button("거부", key=f"vote_no_{who['student_no']}"):
                                set_result(safe(service.cast_vote, db, me, who["student_no"], "거부"))
                                st.rerun()

    if is_admin:
        with st.container(key="unassigned", border=True):
            free = service.unassigned_students(state)
            st.markdown(f"**팀이 없는 학생** ({len(free)}명)")
            st.write(", ".join(s["name"] for s in free) if free else "없음")


# ---------------------------------------------------------------- 관리자 화면

def render_admin(db, user, result_box):
    st.header("관리자")
    up = st.file_uploader("명단 CSV", type=["csv"], key="admin_roster_file")
    count = st.number_input("팀 수", min_value=1, max_value=20, value=3, step=1, key="admin_team_count")
    c1, c2 = st.columns(2)
    if c1.button("명단으로 처음 상태 만들기", key="admin_start"):
        if up is None:
            msg = "막힘: 명단 CSV 파일을 먼저 올려 주세요"
        else:
            msg = safe(service.admin_start, db, user["id"], up.getvalue(), int(count))
        st.session_state.pop("plan", None)
        set_result(msg)
        st.rerun()
    if c2.button("모집 마감", key="admin_close"):
        set_result(safe(service.admin_close, db, user["id"]))
        st.session_state.pop("plan", None)
        st.rerun()

    st.subheader("AI 배정")
    with st.container(key="assign_status"):
        status_box = st.empty()
        status_box.write(st.session_state.get("assign_text", ""))

    if st.button("AI 배정", key="admin_assign"):
        run_assign(db, user, status_box, result_box)

    plan_view = st.session_state.get("plan_view")
    if plan_view is not None:
        st.write(f"배정안({st.session_state.get('plan_source', '')}) — 검사를 통과한 안만 보여 줌")
        st.dataframe(plan_view, hide_index=True)
    if st.button("배정안 확정", key="admin_confirm"):
        msg = safe(service.admin_confirm, db, user["id"], st.session_state.get("plan"))
        if msg.startswith("승인"):
            for k in ("plan", "plan_view", "plan_source", "assign_text"):
                st.session_state.pop(k, None)
        set_result(msg)
        st.rerun()


def run_assign(db, user, status_box, result_box):
    def say(text):
        st.session_state["assign_text"] = text
        status_box.write(text)

    def show(msg):
        set_result(msg)
        result_box.write(msg)

    for k in ("plan", "plan_view", "plan_source"):
        st.session_state.pop(k, None)
    try:
        state, ctx = service.assignment_context(db)
    except Exception:  # noqa: BLE001
        traceback.print_exc(file=sys.stderr)
        show(GENERIC_ERROR)
        return
    if not state["closed"]:
        say("모집을 먼저 마감해야 함")
        show("막힘: 모집을 먼저 마감해야 함")
        return
    result = assign.run_assignment(
        ctx,
        on_status=say,
        on_log=lambda n, model, outcome, elapsed, detail: service.log_ai_call(db, n, model, outcome, elapsed, detail),
    )
    if result.plan is None:
        say("규칙을 지키는 배정이 없음: " + " / ".join(result.reasons))
        show("막힘: 규칙을 지키는 배정이 없음(" + "; ".join(result.reasons) + ")")
        return
    teams = {t["id"]: t["name"] for t in ctx["teams"]}
    students = {s["id"]: s for s in ctx["unassigned"]}
    st.session_state["plan"] = result.plan
    st.session_state["plan_source"] = result.source
    st.session_state["plan_view"] = [
        {"학생": students[sid]["name"], "주 역할": students[sid]["main"], "배정된 팀": teams[tid]}
        for sid, tid in sorted(result.plan.items(), key=lambda kv: (kv[1], kv[0]))
    ]
    notes = "; ".join(f"{n}차 {model} {outcome}" for n, model, outcome, _, _ in result.attempts if outcome != "성공")
    say(f"배정안 준비됨: {result.source}" + (f" (앞선 실패: {notes})" if notes else ""))
    show(f"승인: 배정안을 만들었음({result.source}). 확인한 뒤 확정해 주세요")


# ---------------------------------------------------------------- 진입점

def main():
    try:
        db = get_db()
    except Exception:  # noqa: BLE001
        traceback.print_exc(file=sys.stderr)
        st.error("앱 설정(DATABASE_URL, ADMIN_PASSWORD)을 확인할 수 없음. 관리자에게 문의하세요")
        return

    user = st.session_state.get("user")
    if user is None:
        render_login(db)
        return

    top = st.columns([4, 1])
    with top[0]:
        with st.container(key="whoami"):
            st.write(f"{user['name']} ({user['student_no']})로 로그인함")
    if top[1].button("로그아웃", key="logout"):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()

    with st.container(key="result"):
        result_box = st.empty()
        result_box.write(st.session_state.get("result", "") or " ")

    if user["is_admin"]:
        render_admin(db, user, result_box)
    render_board(db, user)


main()
