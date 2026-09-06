# 레이아웃 카탈로그

`PnuDeck` 의 덱 레벨 메서드와 `ContentSlide` 의 블록 메서드 전부.
좌표 단위는 인치.

---

## 덱 레벨

### `d.cover(year, title, dept, date, subtitle=None, label_dept="발표 부서", label_date="보고 일자")`
L1 표지. 우측 6.03in 패널에 캠퍼스 사진 + 남색 그라데이션 베일 + 화이트
엠블럼(52%). 좌측에 하늘색 점 → 연도(32pt) → 제목(60pt) → 가로 헤어라인 →
레이블/값 2행.

`title` 은 한 줄에 들어가는 길이로. 「주요업무계획 보고」 정도가 상한.

### `d.toc(items, title="목 차", eng="Table of Contents")`
L2 목차. `items` 는 `(아이브로우, 제목)` 또는 `(아이브로우, 제목, 설명)`.
2~4개 권장. 3개 이상이면 항목 아래 짧은 구분선과 설명(2행)을 넣어야
아래 여백이 뜨지 않는다.

```python
d.toc([("2025학년도", "주요 업무 성과", "인력·교육·안전·교통·감사·청렴\n6개 과제 추진 결과"), ...])
```

### `d.divider(no, title, subtitle=None)`
L3 간지. 45° 남색 그라데이션 + 흰 원 번호(0.45in) + 44pt 제목.
`subtitle` 에 그 장의 과제 수·키워드를 넣으면 목차와 호응이 좋다.

### `d.content(no, title, title_size=22) -> ContentSlide`
L4~L8 본문. `no` 는 정수 또는 `"Ⅰ"` 같은 문자열(총괄 슬라이드용).
헤더(탭·번호·제목·로고 락업)를 자동으로 그리고 커서를 `BODY_T` 에 둔다.

### `d.closing(text="경청해주셔서 감사합니다.", sub=None)`
L9 마무리.

### `d.save(path)`
저장. 매수를 출력한다.

---

## ContentSlide — 영역 제어

| 메서드 | 설명 |
|---|---|
| `s.push(x, w, y=None)` | 작업 영역을 좁힌다. 좌우 분할용. 현재 `(x, w, y)` 를 스택에 저장 |
| `s.pop(keep_y=False)` | 직전 영역 복원. `keep_y=True` 면 현재 y를 유지 |
| `s.gap(inches=0.12)` | 커서를 아래로 |
| `s.at(y)` | 커서를 절대 위치로 |
| `s.remaining` | 하단 안전선까지 남은 높이 |
| `s.check(tag="")` | 넘침 여부를 빌드 로그로 경고 |

**좌우 분할 정석**

```python
s.push(BODY_L, 6.20)                      # 왼쪽
...
s.pop()
s.push(7.16, BODY_R - 7.16, y=BODY_T)     # 오른쪽 (y를 위로 되돌림)
...
s.pop()
```

컬럼 사이 간격(거터)은 0.8~1.0in 확보. 좌 6.20 / 우 7.16 시작이 기본 조합.

---

## ContentSlide — 블록

### `s.section(title, size=24, gap_before=0.0, color=NAVY)`
□ 대분류 헤딩 + 이중 사각형 마커. 한 슬라이드에 2~3개.
좁은 컬럼에서는 `size=20`, 전체 폭에서는 `size=21~24`.

### `s.eyebrow(text, size=11.5, color=SKY)`
섹션 위 작은 하늘색 라벨.

### `s.bullets(items, base_x=None, width=None, spacing=1.35, gap=0.05, sizes=None)`
계층 불릿. `items` 는 `(레벨, 텍스트)` 튜플 리스트.
`sizes={1: 14, 2: 12}` 로 레벨별 크기를 낮출 수 있다.

```python
s.bullets([(1, "(실태조사 체계 정립) 연 2회 정기 조사 실시"),
           (2, "부서 자체 채용 인력까지 포함")], sizes={1: 15})
```

### `s.note(text, size=12.0, indent=0.30, pad=0.09)`
※ 하늘색 밴드. 근거 문서번호, 수치 출처, 한계 한 줄 등에 쓴다.
좌우 분할 컬럼 안에서는 `indent=0.0` 으로 컬럼 폭을 꽉 채운다.

### `s.para(text, size=13.5, font=F_MED, color=INK, spacing=1.35, align=None)`
불릿 없는 문단.

### `s.footnote(text, size=10.5)`
회색 각주. 원문의 `*` 주석에 대응.

### `s.table(headers, rows, widths=None, height=None, size=11.5, head_size=11.5, align=None, first_col_left=True, row_h=0.30)`
- `headers=None` 이면 머리행 없음
- `widths` 는 비율 리스트(합 1.0) 또는 인치 리스트
- `align` 은 열별 `PP_ALIGN` 리스트. 생략하면 마지막 열만 좌측 정렬
- 셀에서 `**강조**` 사용 가능 (합계 행 강조에 유용)
- `row_h` 는 최소 행 높이. 슬라이드를 채우려면 0.44~0.62 까지 올린다

```python
s.table(["캠퍼스", "급속", "완속", "계"],
        [["부산", "4", "48", "52"], ["합계", "6", "64", "**70**"]],
        widths=[0.3, 0.2, 0.2, 0.3], row_h=0.34,
        align=[PP_ALIGN.CENTER] * 4)
```

### `s.kpi(cards, h=0.92, gapx=0.14, value_size=25, label_size=10.5, unit_size=12.5)`
수치 카드 행. `cards = [(값, 단위, 라벨), ...]`, 3~4개가 적정.
라벨에 `\n` 을 넣어 2행으로. 값에 `22.4→82` 처럼 변화를 넣어도 좋다.

### `s.cards(items, cols=2, h=None, gapx=0.16, gapy=0.14, title_size=13.5, body_size=11.5, pad=0.18)`
항목 카드 격자. `items = [(제목, 본문 또는 [불릿, ...]), ...]`
`h=None` 이면 남은 세로 공간을 균등 분배한다 (하단 여백 0.12 자동 확보).
`cols=1` 이면 좁은 우측 컬럼용 세로 스택이 된다.

### `s.steps(items, h=0.86, gapx=0.10, title_size=13, desc_size=10.5)`
쉐브론 단계 다이어그램. 남색 → 하늘색으로 진행감을 준다.
`items` 는 `(제목, 설명)` 또는 `(라벨, 제목, 설명)`.
라벨을 쓰면 "1 단계 / 제목 / 설명" 3행이 되어 제목이 짧아진다 — 권장.
쉐브론 안쪽 폭(`w − 1.05in`)에 맞춰 제목 글자를 자동 축소한다.

### `s.compare(left, right, h=1.55, arrow_w=0.52, size=11.5)`
Before ➡ After 비교 패널.

```python
s.compare({"tag": "AS-IS ’24년", "value": "22.38%", "items": ["...", "..."]},
          {"tag": "TO-BE ’25년", "value": "82%",    "items": ["...", "..."]}, h=2.02)
```

### `s.panel(x, y, w, h, title=None, body=None, items=None, fill=NAVY, fg=WHITE, title_size=17, body_size=12.5, pad=0.26)`
색 패널. **절대좌표**로 그리므로 커서와 무관하다.
- `fill=NAVY, fg=WHITE` → 강조 패널 (배경·목적, 한계)
- `fill=PALE, fg=INK` → 보조 패널 (개선 방향, 추진 일정)

`title` 을 주면 제목 아래 짧은 강조선이 자동으로 들어간다.

---

## 슬라이드 구성 레시피

| 원문 구조 | 권장 구성 |
|---|---|
| □ 주요 성과 / □ 한계 | 좌 `bullets`+`note` (7.28in) / 우 `panel`(한계) + `panel`(개선방향) |
| 영역이 3~4개 병렬 | `section` + `cards(cols=3~4)` + 하단 `note` |
| 연도 대비 실적 | `section` + 리드 `bullets` 1줄 + `table` + 좌우 분할(제도/한계) |
| 개선 전후 | `section` + `compare` + 좌우 `bullets` 2단 + 하단 `note` |
| 배경·현황·방안·일정 | 좌 `panel`(배경) / 우 `bullets`(현황) → 하단 `steps` → `note`(일정) |
| 항목 14건 이상 목록 | 표 2개를 좌우로 나눠 7행씩 (`push`/`pop`) + 하단 요약 `note` |
| 총괄(한눈에 보기) | `kpi` 1~2행 + `cards(cols=3)` |
