"""공고 2.7절 표의 key가 화면 코드에 그대로 있는지 확인한다(틀리면 -5점)."""
import re
from pathlib import Path

SRC = (Path(__file__).resolve().parent.parent / "streamlit_app.py").read_text(encoding="utf-8")

FIXED = ["login_student_no", "login_password", "login_submit", "whoami", "result", "admin_roster_file",
         "admin_team_count", "admin_start", "admin_close", "unassigned", "admin_assign", "assign_status",
         "admin_confirm"]
PATTERNS = ['f"team_{', 'f"apply_{', 'f"vote_yes_{', 'f"vote_no_{']


def test_fixed_keys_present():
    for k in FIXED:
        assert f'key="{k}"' in SRC, k


def test_dynamic_keys_present():
    for p in PATTERNS:
        assert p in SRC, p


def test_only_ascii_keys():
    for k in re.findall(r'key=f?"([^"]+)"', SRC):
        assert re.fullmatch(r"[A-Za-z0-9_{}\[\]'.]+", k), k
