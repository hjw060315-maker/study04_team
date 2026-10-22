"""팀 규칙(공고 2.3절). DB와 화면을 모르는 순수 함수만 둔다.

학생은 {"id", "student_no", "name", "main", "subs": [...]} 형태의 dict이다.
"""

ROLES = ("기획자", "웹 프로그래머", "프론트엔드 디자이너", "테스터", "보고서 작성자", "발표자")
PLANNER = "기획자"
WEB_DEV = "웹 프로그래머"
MIN_SIZE = 2
MAX_SIZE = 4


def can_fill(student, role):
    return student["main"] == role or role in student["subs"]


def _planners_and_devs(members):
    planners = [m["id"] for m in members if can_fill(m, PLANNER)]
    devs = [m["id"] for m in members if can_fill(m, WEB_DEV)]
    return planners, devs


def required_filled(members):
    """기획자와 웹 프로그래머를 서로 다른 학생이 맡아 채운 역할 수(0~2)."""
    planners, devs = _planners_and_devs(members)
    if not planners and not devs:
        return 0
    if not planners or not devs:
        return 1
    if len(planners) == 1 and len(devs) == 1 and planners[0] == devs[0]:
        return 1
    return 2


def missing_required(members):
    """아직 채우지 못한 필수 포함 역할의 이름 목록."""
    if required_filled(members) == 2:
        return []
    planners, devs = _planners_and_devs(members)
    if not planners and not devs:
        return [PLANNER, WEB_DEV]
    if not planners:
        return [PLANNER]
    if not devs:
        return [WEB_DEV]
    return [f"{PLANNER} 또는 {WEB_DEV}를 맡을 다른 학생"]


def main_role_conflict(members, student):
    return any(m["main"] == student["main"] for m in members)


def check_join(members, applicant):
    """지원자가 이 팀에 들어갈 수 있는지 검사한다. 막는 이유를 돌려주고, 들어갈 수 있으면 None."""
    if len(members) >= MAX_SIZE:
        return "팀이 꽉 참"
    if main_role_conflict(members, applicant):
        return "같은 주 역할의 팀원이 있음"
    after = list(members) + [applicant]
    slots_left = MAX_SIZE - len(after)
    unfilled = 2 - required_filled(after)
    if slots_left < unfilled:
        return "필수 포함 역할을 맡을 학생의 자리가 모자람"
    return None


def validate_team(name, members):
    """확정한 팀 하나의 위반 목록."""
    errors = []
    if not MIN_SIZE <= len(members) <= MAX_SIZE:
        errors.append(f"{name}의 인원이 {len(members)}명임(2~4명이어야 함)")
    seen = {}
    for m in members:
        if m["main"] in seen:
            errors.append(f"{name}에 주 역할이 같은 학생이 있음({m['main']})")
        seen[m["main"]] = True
    missing = missing_required(members)
    if missing:
        errors.append(f"{name}에 {' / '.join(missing)}을(를) 맡을 학생이 없음")
    return errors


def validate_teams(teams):
    """teams: {팀 이름: 팀원 목록}. 모든 위반을 모아 돌려준다."""
    errors = []
    for name, members in teams.items():
        errors.extend(validate_team(name, members))
    return errors
