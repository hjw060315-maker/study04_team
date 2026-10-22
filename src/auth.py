"""비밀번호 해시와 로그인, 관리자 계정 만들기."""
import bcrypt

ADMIN_NO = "admin"


def hash_password(password, rounds=10):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds)).decode()


def verify_password(password, hashed):
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


def ensure_admin(db, admin_password):
    """앱이 시작할 때 관리자 계정을 만들거나 비밀번호를 갱신한다."""
    with db.tx() as t:
        rows = t.q("select id, password_hash from tf_students where student_no = %s", (ADMIN_NO,))
        if not rows:
            t.x(
                "insert into tf_students (student_no, name, main_role, password_hash, is_admin)"
                " values (%s, %s, null, %s, true)",
                (ADMIN_NO, "관리자", hash_password(admin_password)),
            )
        elif not verify_password(admin_password, rows[0]["password_hash"]):
            t.x(
                "update tf_students set password_hash = %s, is_admin = true where id = %s",
                (hash_password(admin_password), rows[0]["id"]),
            )


def login(db, student_no, password):
    """맞으면 {"id", "student_no", "name", "is_admin"}, 틀리면 None. 틀린 이유는 알려 주지 않는다."""
    student_no = (student_no or "").strip()
    if not student_no or not password:
        return None
    with db.tx() as t:
        rows = t.q(
            "select id, student_no, name, password_hash, is_admin from tf_students where student_no = %s",
            (student_no,),
        )
    if not rows or not verify_password(password, rows[0]["password_hash"]):
        return None
    r = rows[0]
    return {"id": r["id"], "student_no": r["student_no"], "name": r["name"], "is_admin": bool(r["is_admin"])}
