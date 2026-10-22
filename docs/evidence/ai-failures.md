# AI 모델 호출 실패 기록 (실제로 겪은 일)

2026-10-22, 배정 문제 1개(팀2개, 미배정 학생 3명)로 OpenRouter 무료 모델을 직접 호출해 확인했다. 화면 캡처는 아직 없고, 앱에서 실제로 호출한 뒤 `tf_ai_logs`와 배포 화면으로 보강한다.

| 모델 | 결과 | 설명 |
|---|---|---|
| `minimax/minimax-m3:free` | HTTP 404 | 모델 목록(`/api/v1/models`)에 없는 모델이었음 |
| `nvidia/nemotron-3-super-120b-a12b:free` | HTTP 404 | 목록에는 있으나 호출하면 제공사(Nvidia)가 "Function ... Not found"를 돌려줌 |
| `cohere/north-mini-code:free` | 첫 호출: 응답 형식 오류 / 두 번째: 검사 불통과 | 첫 호출은 팀 이름을 `Team2`로 써서 앱이 "없는 팀"으로 거절함(이후 파서가 `Team2`를 `팀2`로 읽게 고침). 두 번째는 이미 팀에 있는 학생을 옮겨 앱이 걸러 냄 |
| `poolside/laguna-s-2.1:free` | 빈 응답 | 78초 뒤 빈 글을 돌려줌 |
| `recursive/flint-v1.0:free` | 성공 | 4.6초 |
| `nvidia/nemotron-3.5-lightning:free` | 성공 | 51초 |
| `xingchen-agi/xing4.0-29b-a4b:free` | 성공 | 67초 |

성공한 3개를 모델로 정했다. 1차는 수업에서 쓰는 `nvidia/nemotron-3.5-lightning:free`, 2차 `recursive/flint-v1.0:free`, 3차 `xingchen-agi/xing4.0-29b-a4b:free`.
