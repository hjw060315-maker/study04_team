from src import rules

AB = {"PL": "기획자", "WP": "웹 프로그래머", "FD": "프론트엔드 디자이너", "TT": "테스터", "RW": "보고서 작성자", "PT": "발표자"}


def stu(i, main, *subs):
    return {"id": i, "student_no": str(i), "name": f"학생{i}", "main": AB[main], "subs": [AB[s] for s in subs]}


def test_required_filled_counts_one_person_once():
    assert rules.required_filled([stu(1, "PL", "WP")]) == 1  # 한 사람이 둘 다 가능해도 하나로만 센다
    assert rules.required_filled([stu(1, "PL", "WP"), stu(2, "TT")]) == 1
    assert rules.required_filled([stu(1, "PL", "WP"), stu(2, "TT", "PL")]) == 2
    assert rules.required_filled([stu(1, "FD")]) == 0


def test_notice_example_blocks_when_slots_short():
    team = [stu(1, "TT"), stu(2, "PT")]
    assert rules.check_join(team, stu(3, "RW")) == "필수 포함 역할을 맡을 학생의 자리가 모자람"


def test_reasons_order():
    full = [stu(i, r) for i, r in enumerate(["PL", "WP", "FD", "TT"], start=1)]
    assert rules.check_join(full, stu(9, "RW")) == "팀이 꽉 참"
    assert rules.check_join([stu(1, "PL")], stu(2, "PL")) == "같은 주 역할의 팀원이 있음"
    assert rules.check_join([], stu(1, "PT")) is None
    assert rules.check_join([stu(1, "PL")], stu(2, "WP")) is None


def test_validate_team():
    assert rules.validate_team("팀1", [stu(1, "PL"), stu(2, "WP")]) == []
    assert rules.validate_team("팀1", [stu(1, "PL")])  # 1명
    assert rules.validate_team("팀1", [stu(1, "PL"), stu(2, "PL", "WP")])  # 주 역할 중복
    assert rules.validate_team("팀1", [stu(1, "PL"), stu(2, "TT")])  # 웹 프로그래머 없음
