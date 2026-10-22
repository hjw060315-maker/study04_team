"""커밋한 파일만 압축한다. 사용: python scripts/make_zip.py 학번  (.env가 들어가면 중단)"""
import subprocess
import sys
import zipfile

student_no = sys.argv[1]
files = subprocess.check_output(["git", "ls-files", "-z"]).decode("utf-8").split("\0")  # -z: 한글 파일 이름을 그대로 받는다
files = [f for f in files if f]
bad = [f for f in files if f == ".env" or f.endswith("secrets.toml")]
if bad:
    sys.exit(f"비밀 파일이 커밋되어 있음: {bad}")
with zipfile.ZipFile(f"{student_no}.zip", "w", zipfile.ZIP_DEFLATED) as z:
    for f in files:
        z.write(f)
with zipfile.ZipFile(f"{student_no}.zip") as z:
    assert not any(n == ".env" for n in z.namelist())
print(f"{student_no}.zip 만듦({len(files)}개 파일, .env 없음 확인)")
