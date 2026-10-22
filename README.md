# 팀 편성 웹 앱

작성자: (본인 이름)

## 1. 배포 주소
(Streamlit 배포 후 주소를 적는다. 예: https://자기앱이름.streamlit.app)

## 2. PRD와 구현 계획의 위치
- `docs/PRD.md`
- `docs/구현 계획.md`

## 3. 고른 해결 방법
| 기능 | 고른 해결 |
|---|---|
| 다른 사람의 변경 보기 | 어려운 해결: `st.fragment(run_every=5)`로 5초마다 갱신 |
| 필수 포함 역할을 지킬 수 없는 팀 | 어려운 해결: 지원 단계에서 자리 계산으로 막음(`src/rules.py`의 `check_join`) |
| 같은 팀에 대기 중인 지원이 여럿 | 어려운 해결: 승인 직전 재검사, 투표가 끝난 순서로 처리(`src/service.py`의 `_settle`) |
| 마지막 자리에 두 명이 동시에 들어감 | 어려운 해결: `tf_members`의 `(team_id, slot_no)` 기본키와 `student_id` 유일 제약(`schema.sql`) |
| AI 응답이 늦을 때 | 어려운 해결: 모델마다 전체 120초를 재서 끊고 다음 모델로(`call_with_deadline`) |
| 3차 모델까지 실패 | 어려운 해결: 모든 경우를 따져 5가지 검사를 통과하는 배정을 찾음(`solve`) |
| AI 대기 중 화면 | 어려운 해결: 몇 차 모델을 몇 초째 기다리는지 `assign_status`에 표시 |
| DB 일시정지 방지 | (고른 방법을 적는다: GitHub Actions `keepalive.yml` 또는 11/2에 앱 사용) |

## 4. 쓴 모델 3개
(실제로 쓴 모델을 적는다. 1차 `nvidia/nemotron-3.5-lightning:free`, 2차 `recursive/flint-v1.0:free`, 3차 `xingchen-agi/xing4.0-29b-a4b:free`)

## 5. 오픈라우터 AI 모델 호출 실패 사례
(실제로 겪은 실패 1건 이상과 화면을 적는다. 화면은 `docs/evidence/`에 저장한다. `tf_ai_logs` 테이블에도 기록이 남는다.)

## 6. 클로드가 잘못된 추론이나 답변을 한 사례
(실제로 겪은 사례 1건 이상과 알아챈 방법(화면이나 커밋)을 적는다.)

## 7. 내 앱에서 발견한 문제점
(연습용 시나리오의 단계와 화면을 근거로 1건 이상 적는다. "문제 없음"은 인정되지 않는다.)

## 실행 방법
```
pip install -r requirements.txt
cp .env.example .env   # 값을 채운다
streamlit run streamlit_app.py
python -m pytest tests
```
