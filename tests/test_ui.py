"""Streamlit 화면을 AppTest로 돌려 key와 흐름을 확인한다(가짜 DB 사용)."""
import os

import pytest
from streamlit.testing.v1 import AppTest

from src import assign, auth, db as dbmod, service
from tests.sqlite_db import SqliteDatabase
from tests.test_scenarios import EASY, roster

APP = os.path.join(os.path.dirname(os.path.dirname(__file__)), "streamlit_app.py")


@pytest.fixture()
def app(monkeypatch):
    fake = SqliteDatabase()
    monkeypatch.setenv("ADMIN_PASSWORD", "pw-admin")
    monkeypatch.setenv("DATABASE_URL", "unused")
    monkeypatch.setattr(dbmod, "create_database", lambda: fake)

    def no_network(model, prompt, timeout):  # 시험이 실제 OpenRouter 무료 한도를 쓰지 않게 막는다
        raise RuntimeError("시험 중에는 네트워크를 쓰지 않음")

    monkeypatch.setattr(assign, "call_openrouter", no_network)
    auth.ensure_admin(fake, "pw-admin")
    admin = auth.login(fake, "admin", "pw-admin")
    assert service.admin_start(fake, admin["id"], roster(2026100, EASY), 3).startswith("승인")
    import streamlit as st
    st.cache_resource.clear()
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    return at, fake


def login(at, no, pw):
    at.text_input(key="login_student_no").set_value(no)
    at.text_input(key="login_password").set_value(pw)
    at.button(key="login_submit").click()
    at.run()


def result_text(at):
    return " ".join(m.value for m in at.markdown if "result" in str(m)) or ""


def test_login_keys_and_wrong_password(app):
    at, _ = app
    login(at, "2026101", "bad")
    assert at.error and not at.exception
    login(at, "2026101", "1234")
    assert not at.exception
    assert any("학생1" in m.value for m in at.markdown)


def test_student_apply_and_vote_flow(app):
    at, fake = app
    login(at, "2026101", "1234")
    at.button(key="apply_1").click(); at.run()
    assert not at.exception
    assert [b.key for b in at.button if b.key and b.key.startswith("apply_")] == []  # 팀이 생기면 지원 단추가 사라짐
    assert any("승인" in m.value for m in at.markdown)
    # 학생4가 지원하고, 학생1이 화면에서 찬성
    me4 = auth.login(fake, "2026104", "1234")
    team1 = service.assignment_context(fake)[1]["teams"][0]["id"]
    assert service.apply_to_team(fake, me4["id"], team1).startswith("대기")
    at.run()
    at.button(key="vote_yes_2026104").click(); at.run()
    assert not at.exception
    assert any(m.value.startswith("승인") for m in at.markdown)
    assert not [b for b in at.button if b.key == "vote_yes_2026104"]


def test_admin_screen_and_student_has_no_admin_widgets(app):
    at, _ = app
    login(at, "2026101", "1234")
    keys = {b.key for b in at.button}
    assert "admin_close" not in keys and "admin_assign" not in keys
    at2 = AppTest.from_file(APP, default_timeout=30); at2.run()
    login(at2, "admin", "pw-admin")
    keys = {b.key for b in at2.button}
    assert {"admin_start", "admin_close", "admin_assign", "admin_confirm"} <= keys
    at2.button(key="admin_close").click(); at2.run()
    assert any(m.value.startswith("승인") for m in at2.markdown)
    at2.button(key="admin_assign").click(); at2.run()
    assert not at2.exception
