"""마감 뒤 팀이 없는 학생의 배정(공고 2.5절).

흐름: 규칙을 지키는 배정이 있는지 먼저 따짐 → AI 1·2·3차 → 모두 실패하면 앱이 직접 배정.
ctx = {"teams": [{"id", "name", "members": [학생 dict]}], "unassigned": [학생 dict]}
plan = {학생 id: 팀 id}
"""
import json
import queue
import re
import threading
import time
from dataclasses import dataclass, field

import requests

from . import rules
from .config import get_secret

API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL_TIMEOUT = 120  # 모델 하나를 부른 때부터 응답을 받을 때까지의 전체 대기 시간(초)
DEFAULT_MODELS = (
    "nvidia/nemotron-3.5-lightning:free",
    "recursive/flint-v1.0:free",
    "xingchen-agi/xing4.0-29b-a4b:free",
)


def get_models():
    """환경 변수 MODEL_1~3이 있으면 그것을, 없으면 기본 모델 3개를 쓴다."""
    models = []
    for i, default in enumerate(DEFAULT_MODELS, start=1):
        models.append(get_secret(f"MODEL_{i}") or default)
    return models


# ---------------------------------------------------------------- 검사

def _teams_after(ctx, plan):
    by_id = {t["id"]: list(t["members"]) for t in ctx["teams"]}
    students = {s["id"]: s for s in ctx["unassigned"]}
    for sid, tid in plan.items():
        if tid in by_id and sid in students:
            by_id[tid].append(students[sid])
    return {t["name"]: by_id[t["id"]] for t in ctx["teams"]}


def validate_plan(ctx, plan):
    """2.5절 4항의 다섯 가지 검사. 위반 목록을 돌려준다(비어 있으면 통과)."""
    errors = []
    unassigned_ids = {s["id"] for s in ctx["unassigned"]}
    team_ids = {t["id"] for t in ctx["teams"]}
    for s in ctx["unassigned"]:
        if s["id"] not in plan:
            errors.append(f"팀이 없는 학생 {s['name']}이(가) 배정되지 않음")
    for sid, tid in plan.items():
        if sid not in unassigned_ids:
            errors.append("이미 팀이 있는 학생이나 모르는 학생이 배정안에 들어 있음")
        if tid not in team_ids:
            errors.append("없는 팀에 배정함")
    if errors:
        return errors
    return rules.validate_teams(_teams_after(ctx, plan))


# ---------------------------------------------------------------- 앱이 직접 배정

def solve(ctx):
    """모든 경우를 따져 다섯 가지 검사를 통과하는 배정을 찾는다. 없으면 None."""
    teams = ctx["teams"]
    students = sorted(ctx["unassigned"], key=lambda s: s["id"])
    members = {t["id"]: list(t["members"]) for t in teams}
    plan = {}

    def team_ok(tid):
        return not rules.validate_team("", members[tid])

    def search(i):
        if i == len(students):
            return all(team_ok(t["id"]) for t in teams)
        s = students[i]
        # 남은 학생(이 학생 포함)으로 2명 미만인 팀을 다 채울 수 없으면 가지를 친다
        need = sum(max(0, rules.MIN_SIZE - len(members[t["id"]])) for t in teams)
        if need > len(students) - i:
            return False
        order = sorted(teams, key=lambda t: len(members[t["id"]]))
        for t in order:
            tid = t["id"]
            cur = members[tid]
            if len(cur) >= rules.MAX_SIZE or rules.main_role_conflict(cur, s):
                continue
            cur.append(s)
            plan[s["id"]] = tid
            if search(i + 1):
                return True
            cur.pop()
            del plan[s["id"]]
        return False

    return dict(plan) if search(0) else None


def explain_infeasible(ctx):
    """규칙을 지키는 배정이 없는 이유를 사람이 읽을 문장으로 돌려준다."""
    reasons = []
    teams, students = ctx["teams"], ctx["unassigned"]
    total = sum(len(t["members"]) for t in teams) + len(students)
    if total < rules.MIN_SIZE * len(teams):
        reasons.append(f"전체 {total}명으로는 모든 팀을 2명 이상으로 채울 수 없음")
    if total > rules.MAX_SIZE * len(teams):
        reasons.append(f"전체 {total}명이 모든 팀의 정원({rules.MAX_SIZE * len(teams)}명)보다 많음")
    for t in teams:
        members = t["members"]
        if len(members) > rules.MAX_SIZE:
            continue
        pool = [s for s in students if not rules.main_role_conflict(members, s)]
        for role in rules.missing_required(members):
            if " 또는 " in role:
                continue
            if not any(rules.can_fill(s, role) for s in pool):
                reasons.append(f"{t['name']}에 {role}를 맡을 학생이 없음")
        errors = rules.validate_team(t["name"], members)
        if len(members) == rules.MAX_SIZE and errors:
            reasons.extend(e for e in errors if "인원" not in e)
    if not reasons:
        reasons.append("모든 팀의 인원, 주 역할, 필수 포함 역할을 한꺼번에 만족하는 조합이 없음")
    return reasons


# ---------------------------------------------------------------- AI 호출

def build_prompt(ctx):
    lines = ["너는 팀 편성 도우미이다. 아래 규칙을 모두 지키도록 팀이 없는 학생을 팀에 배정해라.", ""]
    lines += [
        "규칙:",
        "1. 이미 팀에 있는 학생은 옮기지 않는다. 팀이 없는 학생만 배정한다.",
        "2. 팀이 없는 학생은 한 명도 빠짐없이, 한 팀에만 배정한다.",
        "3. 배정이 끝난 모든 팀은 2~4명이다.",
        "4. 한 팀에 주 역할이 같은 학생이 2명 이상이면 안 된다.",
        "5. 모든 팀에는 기획자를 맡을 학생과 웹 프로그래머를 맡을 학생이 서로 다른 사람으로 1명씩 있어야 한다."
        " 주 역할이나 보조 역할로 맡을 수 있다.",
        "",
        "현재 팀:",
    ]
    for t in ctx["teams"]:
        if t["members"]:
            desc = ", ".join(
                f"{m['name']}(학번 {m['student_no']}, 주 {m['main']}, 보조 {'/'.join(m['subs']) or '없음'})"
                for m in t["members"]
            )
        else:
            desc = "(비어 있음)"
        lines.append(f"- {t['name']}: {desc}")
    lines += ["", "팀이 없는 학생:"]
    for s in ctx["unassigned"]:
        lines.append(f"- 학번 {s['student_no']}, {s['name']}, 주 {s['main']}, 보조 {'/'.join(s['subs']) or '없음'}")
    lines += [
        "",
        "설명 없이 JSON만 출력해라. 형식:",
        '{"assignments": [{"student_no": "학번", "team": "팀1"}]}',
    ]
    return "\n".join(lines)


def parse_response(text, ctx):
    """AI 응답 글에서 {학생 id: 팀 id}를 뽑는다. 틀린 형식이면 ValueError."""
    if not text or not text.strip():
        raise ValueError("빈 응답")
    body = re.sub(r"```(?:json)?", "", text)
    start, end = body.find("{"), body.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("JSON을 찾을 수 없음")
    try:
        data = json.loads(body[start:end + 1])
        items = data["assignments"]
    except (ValueError, KeyError, TypeError):
        raise ValueError("JSON 형식이 틀림")
    by_no = {s["student_no"]: s["id"] for s in ctx["unassigned"]}
    all_no = {m["student_no"] for t in ctx["teams"] for m in t["members"]}
    by_team = {t["name"]: t["id"] for t in ctx["teams"]}
    plan = {}
    for item in items:
        try:
            no = str(item["student_no"]).strip()
            team = str(item["team"]).strip()
        except (KeyError, TypeError):
            raise ValueError("배정 항목 형식이 틀림")
        if team not in by_team:  # "Team2", "team 2", "2" 같은 표기를 "팀2"로 읽는다
            digits = re.search(r"(\d+)", team)
            if digits:
                team = f"팀{int(digits.group(1))}"
        if no in all_no:
            raise ValueError("이미 팀이 있는 학생을 옮김")
        if no not in by_no:
            raise ValueError(f"모르는 학번 {no}")
        if team not in by_team:
            raise ValueError(f"없는 팀 {team}")
        if by_no[no] in plan:
            raise ValueError(f"학번 {no}를 두 번 배정함")
        plan[by_no[no]] = by_team[team]
    return plan


def call_openrouter(model, prompt, timeout):
    """OpenRouter에 질문하고 답변 글을 돌려준다. 실패하면 예외."""
    key = get_secret("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY가 없음")
    resp = requests.post(
        API_URL,
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 12000,
            "temperature": 0,
            "reasoning": {"effort": "low"},
        },
        timeout=(10, timeout + 10),
    )
    if resp.status_code != 200:
        try:
            detail = str(resp.json().get("error", {}).get("message", ""))[:80]
        except ValueError:
            detail = ""
        raise RuntimeError(f"HTTP {resp.status_code} {detail}".strip())
    data = resp.json()
    try:
        choice = data["choices"][0]
        content = choice["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        return ""
    if not content.strip() and choice.get("finish_reason") == "length":
        raise RuntimeError("생각하느라 응답 길이 한도를 다 써서 답이 비어 있음")
    return content


def call_with_deadline(fn, seconds, on_tick=None):
    """fn()을 따로 돌리고, 시작부터 seconds초가 지나면 기다리지 않고 TimeoutError를 낸다.
    요청 라이브러리의 timeout은 응답이 시작될 때까지만 재는 경우가 많아 전체 시간을 직접 잰다."""
    box = queue.Queue()

    def run():
        try:
            box.put(("ok", fn()))
        except Exception as e:  # noqa: BLE001
            box.put(("err", e))

    threading.Thread(target=run, daemon=True).start()
    started = time.monotonic()
    while True:
        elapsed = time.monotonic() - started
        if elapsed >= seconds:
            raise TimeoutError(f"{seconds}초 안에 응답하지 않음")
        try:
            kind, value = box.get(timeout=min(1.0, seconds - elapsed))
        except queue.Empty:
            if on_tick:
                on_tick(int(time.monotonic() - started))
            continue
        if kind == "err":
            raise value
        return value


# ---------------------------------------------------------------- 전체 흐름

@dataclass
class AssignResult:
    plan: dict = None
    source: str = ""
    reasons: list = field(default_factory=list)
    attempts: list = field(default_factory=list)  # (차수, 모델, 결과, 걸린 시간, 설명)


def run_assignment(ctx, models=None, call=None, timeout=MODEL_TIMEOUT, on_status=None, on_log=None):
    """검사를 통과한 배정안만 돌려준다. call(model, prompt, timeout) -> 글 은 시험용으로 바꿀 수 있다."""
    say = on_status or (lambda text: None)
    result = AssignResult()

    if not ctx["unassigned"]:
        errors = rules.validate_teams({t["name"]: t["members"] for t in ctx["teams"]})
        if errors:
            result.reasons = errors
        else:
            result.plan, result.source = {}, "팀이 없는 학생이 없어 배정할 필요가 없음"
        return result

    fallback = solve(ctx)
    if fallback is None:
        result.reasons = explain_infeasible(ctx)
        say("규칙을 지키는 배정이 없음. AI를 부르지 않음")
        return result

    models = models or get_models()
    call = call or call_openrouter
    prompt = build_prompt(ctx)
    for n, model in enumerate(models, start=1):
        started = time.monotonic()
        say(f"AI가 생각하는 중: {n}차 모델({model})의 응답을 기다리는 중 (최대 {timeout}초)")
        outcome, detail = "성공", ""
        plan = None
        try:
            text = call_with_deadline(
                lambda: call(model, prompt, timeout),
                timeout,
                on_tick=lambda sec: say(
                    f"AI가 생각하는 중: {n}차 모델({model})의 응답을 기다리는 중 ({sec}초 경과 / 최대 {timeout}초)"
                ),
            )
            plan = parse_response(text, ctx)
            errors = validate_plan(ctx, plan)
            if errors:
                outcome, detail = "검사 불통과", "; ".join(errors)
        except TimeoutError as e:
            outcome, detail = "시간 초과", str(e)
        except ValueError as e:
            outcome, detail = "응답 형식 오류", str(e)
        except Exception as e:  # noqa: BLE001
            outcome, detail = "호출 오류", str(e)[:200]
        elapsed = round(time.monotonic() - started, 1)
        result.attempts.append((n, model, outcome, elapsed, detail))
        if on_log:
            on_log(n, model, outcome, elapsed, detail)
        if outcome == "성공":
            result.plan, result.source = plan, f"AI {n}차 모델({model})"
            say(f"{n}차 모델의 배정안이 검사를 통과함")
            return result
        say(f"{n}차 모델 실패({outcome}). 다음 모델로 넘어감")

    result.plan, result.source = fallback, "앱이 직접 배정(3차 모델까지 실패)"
    say("3차 모델까지 실패해 앱이 직접 배정함")
    return result
