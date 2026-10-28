# 생성 영상 왜곡 판정 일치도 연구 — 도구 모음

판정 가이드 v1 → v2 보완이 판정자 간 일치도를 높이는지 확인하는 연구용 스크립트입니다.
세 파일을 같은 폴더에 두고 순서대로 실행합니다.

## 준비 (한 번만)

```
pip install datasets pandas numpy openpyxl scipy
```

## 순서

| 단계 | 명령 | 결과 |
|---|---|---|
| 1주 | `python 01_sample_videos.py` | `videos_A.csv`, `videos_B.csv` (각 120개) |
| 1주 | `python 02_make_sheets.py A v1` | 판정자 4명분 엑셀 `sheet_A_v1_R1~R4.xlsx` |
| 3주 | 판정자에게 시트를 나눠 주고 채운 파일을 같은 폴더로 회수 | |
| 4주 | `python 03_agreement.py A v1` | 일치도 보고서 + `disagreements_A_v1.csv` (가이드 v2 재료) |
| 5주 | `python 02_make_sheets.py B v2` | 2차 판정 시트 |
| 6주 | `python 02_make_sheets.py A v2` | 세트 A 재판정 시트 (1차 후 2주 이상 간격) |
| 7주 | `python 03_agreement.py A v1 B v2` | v1 대 v2 비교 (주 결과) |
| 7주 | `python 03_agreement.py A v1 A v2` | 같은 영상 재판정 비교 (보강 결과) |

## 알아 둘 점

- 판정자 파일 이름(`sheet_A_v1_R1.xlsx`)은 바꾸지 마세요. 스크립트가 이름으로 찾습니다.
- 판정자마다 영상 순서가 다르게 섞여 있습니다. 일부러 그렇게 만든 것입니다.
- 화질 점수(visual_quality)는 판정 시트에 넣지 않았습니다. 판정자가 보면 결과가 오염됩니다.
- `disagreements_*.csv`의 마지막 칸 "유형(A~): 직접 적기"에 갈린 이유를 유형으로 적어 나가면
  그것이 가이드 v2와 논문 4장(결과)의 표가 됩니다.
- 영상은 VideoFeedback(Apache-2.0) 기준입니다. 논문에는 영상 ID와 캡처만 싣고 영상은 재배포하지 않습니다.
- `01_sample_videos.py`의 `PERSON_WORDS`로 사람 영상만 고릅니다. 링크 몇 개를 열어 실제로 사람이 나오는지 확인하세요.

## 계산 방법

- Fleiss 카파 (판정자 3명 이상용), statsmodels 결과와 일치함을 확인했습니다.
- 95% 구간: 영상 단위 부트스트랩 2,000회.
- 두 조건 비교: 차이의 95% 구간이 0을 포함하지 않으면 "차이 있음".
- 화질 점수와의 관계: 스피어만 상관.
