"""나눠 준 CSV(쉬움/중간/어려움)로 실제 Supabase에서 연습용 시나리오 3개를 돌린다(AI 호출은 가짜).
명단 데이터를 지우고 다시 만든다. 사용: python scripts/real_db_scenarios.py [CSV 폴더]"""
import os
import sys

sys.path.insert(0, ".")
from src import service
from src.config import get_secret
from src.db import create_database
import tests.test_scenarios as ts

folder = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/Downloads")
files = {2026100: "쉬움.csv", 2026200: "중간.csv", 2026300: "어려움.csv"}
raw = {base: open(os.path.join(folder, name), "rb").read() for base, name in files.items()}

for base, spec in ((2026100, ts.EASY), (2026200, ts.MID), (2026300, ts.HARD)):
    mine = service.parse_roster(ts.roster(base, spec))
    given = service.parse_roster(raw[base])
    assert mine == given, f"{files[base]}가 시험에 쓴 명단과 다름"
    print(files[base], "명단 일치,", len(given), "명")

real = create_database()
os.environ["TEST_ADMIN_PW"] = get_secret("ADMIN_PASSWORD")
ts.SqliteDatabase = lambda: real
ts.roster = lambda base, rows: raw[base]  # 올리는 파일을 나눠 준 파일 그대로 쓴다
# REAL_AI=1 python scripts/real_db_scenarios.py 로 돌리면 마감 뒤 배정에서 실제 OpenRouter 무료 모델을 부른다(시나리오당 최대 3번)
names = sys.argv[2].split(",") if len(sys.argv) > 2 else ["test_easy", "test_middle", "test_hard", "test_vote_rules_and_double_apply"]
for name in names:
    ts.World.last_result = None
    getattr(ts, name)()
    r = ts.World.last_result
    extra = ""
    if r is not None:
        extra = f" | 배정: {r.source} | 시도: " + ", ".join(f"{a[0]}차 {a[2]}({a[3]}초)" for a in r.attempts)
    print(name, "통과" + extra)
