---
name: pnu-work-report-ppt
description: 부산대학교 「2026 업무보고 서식」 디자인을 그대로 재현한 PPT(.pptx)를 만든다. 트리거 — "주요업무보고 PPT", "업무보고 서식으로 만들어줘", "부산대 PPT", "총무과/기획처 등 부서 업무보고 발표자료", 또는 한글(.hwpx/.hwp) 업무보고 원고를 주며 발표용 슬라이드로 바꿔 달라고 할 때. 표지·목차·간지·본문(계층불릿/표/KPI카드/좌우분할/단계다이어그램/Before-After)·마무리 9종 레이아웃을 제공하며, 남색 1C4FA1·하늘색 2DA7E0·페이퍼로지 임베드 서체·헤더 탭 도형을 원본과 동일하게 유지하고 80주년 기념 로고 자리는 부산대학교 엠블럼으로 대체한다.
---

# 부산대학교 주요업무보고 PPT 빌더

원본 서식 「2026 업무보고 서식 1부.pptx」(9매)의 디자인 언어를 코드로 재현한
파이썬 라이브러리다. 원본은 자리표시자(OOOO과, 가나다라마바사)만 들어 있어
내용량이 달라지면 레이아웃이 무너지므로, **디자인 토큰은 고정하고 본문은
내용량에 맞춰 조립**하는 방식으로 만들었다.

## 0. 준비

```bash
pip install python-pptx pillow
```

`assets/base.pptx` 는 원본에서 슬라이드만 제거하고 **테마·임베드 서체
(페이퍼로지 4/5/6/7/9, 공체 Bold, 맑은 고딕)를 보존**한 파일이다.
따라서 페이퍼로지가 설치되지 않은 PC에서도 서체가 정상 렌더링된다.
새 슬라이드는 모두 이 파일 위에 얹는다.

## 1. 기본 사용법

```python
import sys; sys.path.insert(0, "<스킬경로>/scripts")
from pnu_deck import PnuDeck, BODY_L, BODY_R, BODY_B, NAVY, PALE, INK, PP_ALIGN

d = PnuDeck()

# ① 표지
d.cover(year="2026", title="주요업무계획 보고",
        dept="총무과", date="2026. 3. 16. (월)")

# ② 목차 (2~4개 권장)
d.toc([("2025학년도", "주요 업무 성과",     "6개 과제 추진 결과"),
       ("2026학년도", "주요 업무 추진계획", "4개 중점 과제"),
       ("총장공약",   "공약사업 추진현황",  "14개 공약 이행 현황")])

# ③ 간지
d.divider(1, "2025학년도 주요 업무 성과", "인력 · 교육 · 안전 · 감사 · 청렴")

# ④ 본문 — 커서(s.y)가 위에서 아래로 내려가며 블록을 쌓는다
s = d.content(1, "효율적인 인력 운영을 위한 행정직원 총괄 관리 기반 구축")
s.section("주요 성과")                       # □ 대분류 + 이중사각형 마커
s.bullets([(1, "(실태조사 체계 정립) 연 2회 정기 조사 실시"),
           (2, "부서 자체 채용 인력까지 포함한 전수 조사")])
s.note("(’25. 4.) 무기계약직 현황 조사(총무과-6441)")   # ※ 하늘색 밴드
s.check()                                    # 하단 넘침 경고

# ⑤ 마무리
d.closing("경청해주셔서 감사합니다.", sub="2026 총무과 주요업무보고")
d.save("보고서.pptx")
```

`build_chongmu_2026.py` 가 20매짜리 완성 예제다. 새 부서 보고서를 만들 때는
이 파일을 복사해 내용만 바꾸는 것이 가장 빠르다.

## 2. 레이아웃 9종

| # | 메서드 | 쓰임 |
|---|---|---|
| L1 | `d.cover()` | 표지 — 캠퍼스 사진 + 남색 베일 + 화이트 엠블럼 |
| L2 | `d.toc()` | 목차 — 상단 스카이라인 띠 + 번호 원 + 점선 |
| L3 | `d.divider()` | 간지 — 45° 남색 그라데이션 |
| L4 | `s.bullets()` | 계층 불릿 (◦ / － / ※) — 한글 보고서 골격 그대로 |
| L5 | `s.note()` | ※ 근거·수치 강조 밴드 |
| L6 | `s.panel()` + `s.push()` | 좌우 분할 — 한쪽 개요 패널, 다른 쪽 항목 나열 |
| L7 | `s.table()` | 표 — 남색 머리행 + 교대 음영 |
| L8 | `s.kpi()` `s.cards()` `s.steps()` `s.compare()` | 인포그래픽 |
| L9 | `d.closing()` | 마무리 |

레이아웃별 인자와 배치 요령 → `references/layout-catalog.md`
색·서체·좌표 토큰 → `references/design-tokens.md`

## 3. 레이아웃 선택 기준

내용의 **형태**를 보고 고른다. 억지로 인포그래픽으로 바꾸지 말 것.

- 수치가 3~6개 나열 → `kpi()`
- 항목이 3~9개 병렬 → `cards(cols=2~4)`
- 연도·캠퍼스·유형별 대비 → `table()`
- 순차 절차(1→2→3단계) → `steps()`
- 개선 전/후 대비 → `compare()`
- 「배경·목적」처럼 서술이 필요한 덩어리 + 항목 나열 → `panel()` 좌우 분할
- 그 외 서술형 → `bullets()` + `note()`

한 슬라이드에 인포그래픽은 **최대 2종**. 3종 이상 섞으면 산만해진다.

## 4. 좌우 분할 작성 패턴

`push(x, w, y)` 로 작업 영역을 좁히고 `pop()` 으로 되돌린다.

```python
s.push(BODY_L, 6.20)          # 좌측 컬럼
s.section("전기차 충전 인프라"); s.table(...); s.bullets(...)
s.pop()
s.push(7.16, BODY_R - 7.16, y=1.24)   # 우측 컬럼 (y를 헤더 아래로 되돌림)
s.section("교통안전 관리 강화"); s.cards(..., cols=1)
s.pop()
```

`panel()` 은 커서와 무관하게 절대좌표로 그리므로 분할 컬럼 한쪽을
통째로 색 패널로 채울 때 쓴다.

## 5. 본문 텍스트 마크업

`bullets` / `para` / `cards` / `panel` / `table` 의 문자열에서:

- 문두 괄호 `(청렴 문화 확산)` → 자동으로 남색 볼드 (한글 보고서의 소제목 관례)
- `**강조**` → 남색 볼드. 남색 패널 안에서는 밝은 하늘색으로 자동 전환
- `\n` → 줄바꿈 (표 셀·KPI 라벨에서 유용)

## 6. 넘침 관리

`est_height()` 로 블록 높이를 추정해 커서를 옮기지만 추정이므로,
슬라이드마다 `s.check("태그")` 를 호출해 하단 안전선(7.05in) 초과 여부를
빌드 로그로 확인한다. 경고가 뜨면 → 글자 크기 축소(`sizes={1: 14}`),
카드 높이 축소, 또는 슬라이드 분리.

`cards(h=None)` 은 남은 세로 공간을 균등 분배하므로 하단 여백 조절에 편하다.

## 7. 로고 규칙 (중요)

원본의 **80주년 기념 로고는 사용하지 않는다.** 모두 부산대학교 엠블럼으로 대체:

- 표지 : `pnu_emblem_white.png` 를 우측 사진 패널 중앙에 52% 투명도로
- 본문 헤더 우측 : `pnu_emblem.png`(컬러) + 세로 구분선 + `부산대학교 /
  PUSAN NATIONAL UNIVERSITY` 텍스트 락업 — `_logo_lockup()` 이 자동 처리
- 목차 : 상단 흰 띠 우측에 컬러 엠블럼
- 마무리 : 화이트 엠블럼

엠블럼 원본은 `부산대로고 BASIC-01-1.ai`(PDF 1.4) 를 PyMuPDF 로 8배 확대
렌더링 후 알파 크롭한 1140×1140 투명 PNG다. 재생성이 필요하면
`scripts/make_assets.py` 참고.

## 8. 한글(.hwpx) 원고에서 내용 뽑기

`.hwpx` 는 zip이다. `Contents/section0.xml` 의 `<hp:t>` 를 순서대로 이으면
되지만, **`<hp:fwSpace/>` 같은 자식 요소의 `tail` 을 놓치면 날짜·수치가
잘려 나간다.** 반드시 tail 까지 이어 붙일 것.

```python
def t_text(el):                 # el = hp:t
    s = el.text or ""
    for ch in el:
        if ch.tag.endswith("}fwSpace"): s += " "
        elif ch.tag.endswith("}tab"):   s += "\t"
        s += (ch.tail or "")
    return s
```

## 9. 결과 확인

Windows + PowerPoint 환경에서는 COM으로 슬라이드를 PNG로 뽑아 눈으로 검수한다.

```powershell
$app = New-Object -ComObject PowerPoint.Application
$p = $app.Presentations.Open("<절대경로>.pptx", $true, $false, $false)
$p.Export("<출력폴더>", "PNG", 1600, 900)
$p.Close(); $app.Quit()
```

## 10. 파일 구성

```
pnu-work-report-ppt/
├── SKILL.md
├── assets/
│   ├── base.pptx              원본 테마·임베드 서체 보존 (슬라이드 0매)
│   ├── pnu_emblem.png         부산대 엠블럼 (컬러·투명)
│   ├── pnu_emblem_white.png   부산대 엠블럼 (화이트 모노)
│   ├── campus.png             캠퍼스 전경 (표지용)
│   └── campus_gray.png        캠퍼스 전경 흑백 (목차 상단 띠용)
├── references/
│   ├── design-tokens.md       색·서체·좌표·도형 사양
│   └── layout-catalog.md      레이아웃별 API와 배치 요령
└── scripts/
    ├── pnu_deck.py            빌더 라이브러리
    ├── make_assets.py         assets 재생성
    └── build_chongmu_2026.py  총무과 2026 보고서 20매 예제
```
