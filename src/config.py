"""비밀 값 읽기. 로컬은 .env, 배포는 Streamlit Secrets. 값을 출력하지 않는다."""
import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # 배포 환경에는 .env가 없다
    pass


def get_secret(name, default=None):
    value = os.environ.get(name)
    if value:
        return value
    try:
        import streamlit as st

        return st.secrets.get(name, default)
    except Exception:  # noqa: BLE001  secrets 파일이 없으면 예외가 난다
        return default


def has_secret(name):
    return bool(get_secret(name))
