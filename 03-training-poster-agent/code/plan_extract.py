# -*- coding: utf-8 -*-
"""
직장교육 계획(안) → 포스터에 쓸 구조화 데이터

PDF / HWPX 를 모두 받는다. 계획안은 달마다 서식이 조금씩 다르므로
'있으면 쓰고 없으면 비운다'를 원칙으로 하고, **없는 값을 지어내지 않는다.**

확인된 변형 (2025-02 ~ 2026-09, 19건)
  - 유형 : 집합교육형(일시·장소·강사·예산 있음) / 이러닝형(수강기간, 강사 없음)
  - 라벨 : '교육내용' 과 '교육주제' 혼용
  - 대상 : '전 직원' 과 '전 교직원' 혼용
"""
import argparse
import json
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

WEEK = "월화수목금토일"


# ------------------------------------------------------------------ 텍스트 추출
def text_from_pdf(path):
    import fitz
    d = fitz.open(path)
    t = "\n".join(p.get_text() for p in d)
    d.close()
    return t


def text_from_hwpx(path):
    """CLAUDE.md 6항: <hp:t> 의 .text 만 이으면 자식 요소 뒤의 tail 이 빠져
    날짜·수치가 잘린다. 자식의 tail 까지 이어 붙인다."""
    z = zipfile.ZipFile(path)
    secs = sorted(n for n in z.namelist() if re.match(r"Contents/section\d+\.xml", n))
    NS = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
    lines = []
    for s in secs:
        root = ET.fromstring(z.read(s))
        for para in root.iter(NS + "p"):
            buf = []
            for t in para.iter(NS + "t"):
                if t.text:
                    buf.append(t.text)
                for ch in t:
                    if ch.tail:
                        buf.append(ch.tail)
            lines.append("".join(buf))
    return "\n".join(lines)


def load_text(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        return text_from_pdf(path)
    if ext in (".hwpx", ".zip"):
        return text_from_hwpx(path)
    raise SystemExit("지원하지 않는 형식입니다: %s (PDF 또는 HWPX)" % ext)


# ------------------------------------------------------------------ 항목 추출
def field(t, *names):
    """'○교육일시: ...' 형태에서 값을 뽑는다. 라벨이 여러 개면 먼저 걸리는 것."""
    for n in names:
        m = re.search(r"[○ㅇ●]?\s*" + n + r"\s*[:：]\s*([^\n]+)", t)
        if m:
            return re.sub(r"\s+", " ", m.group(1)).strip()
    return None


def parse_datetime(s):
    """'2026. 9. 16.(수) 15:00~17:00' → 날짜/요일/시간"""
    if not s:
        return {}
    out = {}
    m = re.search(r"(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\.?\s*\(?([월화수목금토일])?\)?", s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        out["연"], out["월"], out["일"] = y, mo, d
        wd = m.group(4)
        if not wd:
            import datetime
            wd = WEEK[datetime.date(y, mo, d).weekday()]
        out["요일"] = wd
        out["날짜표기"] = "%d. %d. %d.(%s)" % (y, mo, d, wd)
    m = re.search(r"(\d{1,2}:\d{2})\s*[~\-–]\s*(\d{1,2}:\d{2})", s)
    if m:
        out["시작"], out["종료"] = m.group(1), m.group(2)
        out["시간표기"] = "%s~%s" % (m.group(1), m.group(2))
    return out


def parse_lecturer(t):
    """표 안의 강사 정보. '이 안 나\n(젠더&... 대표,\n한국양성평등교육진흥원 전문강사)' 형태."""
    m = re.search(r"강\s*사\s*\n(.+?)(?=\n\s*○|\n\s*-\s*\(|\Z)", t, re.S)
    if not m:
        return {}
    blob = m.group(1)
    # 표가 '강의시간 / 교육내용 / 강사' 순이라 앞에 교육내용이 섞여 들어온다.
    # 괄호 안에 직위 낱말(강사·교수·대표 등)이 있는 것만 강사 소속으로 인정하고,
    # 그 바로 앞 줄머리에 오는 낱말을 이름으로 본다.
    # 직위 낱말. 좁게 잡으면 강사를 놓친다 —
    # '부울경 정보보호산업협회 회장' 이 '회장' 누락으로 인식되지 않았다.
    ROLE = (r"강사|교수|대표|연구|센터|원장|변호사|박사|위원|소장|팀장|관|"
            r"회장|이사|국장|과장|실장|본부장|협회|학회|연구소|아카데미|"
            r"청장|처장|단장|부장|차장|주사|사무관|컨설턴트|전문가")
    # 소속 괄호에 직위 낱말이 없는 경우가 있다 — '(청렴연수원)' 처럼 기관명만 오기도.
    # 그래서 직위 낱말만으로 거르지 않고 **이름 길이**로 먼저 판별한다.
    # 한국 사람 이름은 2~4음절이고, 이 문서들은 '이 안 나' 처럼 띄어 쓴다.
    # 교육내용('폭력예방교육' 5음절)은 이 조건에서 자연히 걸러진다.
    with_role, any_cand = [], []
    for mm in re.finditer(
            r"(?:^|\n)\s*([가-힣](?:\s?[가-힣]){1,3})\s*\n?\s*\(([^)]+)\)", blob, re.S):
        name = re.sub(r"\s+", " ", mm.group(1)).strip()
        if len(name.replace(" ", "")) > 4:
            continue
        aff = re.sub(r"\s*\n\s*", " ", mm.group(2)).strip()
        any_cand.append((name, aff))
        if re.search(ROLE, aff):
            with_role.append((name, aff))
    # 직위가 붙은 쪽이 강사일 가능성이 높다. 없으면 마지막 후보(주 강의)를 쓴다.
    pool = with_role or any_cand
    if not pool:
        return {}
    return {"성명": pool[-1][0], "소속": pool[-1][1]}


def detect_mode(t, 운영방법):
    s = (운영방법 or "") + " " + t[:2500]
    이러닝 = bool(re.search(r"이러닝|e-?learning|나라배움터|온라인 수강", s, re.I))
    대면 = bool(re.search(r"대면\s*집합교육|집합교육", s))
    비대면 = bool(re.search(r"ZOOM|줌|비대면", s, re.I))
    if 이러닝 and not 대면:
        return "이러닝"
    if 대면 and 비대면:
        return "혼합"
    if 대면:
        return "집합"
    return "미상"


def parse(path):
    t = load_text(path)
    t = t.replace(" ", " ")
    flat = re.sub(r"[ \t]+", " ", t)

    d = {"원본파일": os.path.basename(path)}

    m = re.search(r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*직장교육", flat)
    if m:
        d["연도"], d["월"] = int(m.group(1)), int(m.group(2))

    d["교육대상"] = field(flat, "교육대상")
    # 라벨이 달마다 다르다. 2025-03·06·07·09·11, 2026-03 은 '교육과정' 을 쓴다.
    d["교육내용"] = field(flat, "교육내용", "교육주제", "교육과정")
    # '세부운영' 의 '- (교육내용) …' 이 더 구체적인 경우가 있다(예: 사회적 장애인식개선교육)
    m = re.search(r"-\s*\(교육내용\)\s*([^\n]+)", flat)
    if m:
        detail = re.sub(r"\s+", " ", m.group(1)).strip()
        if detail and len(detail) > len(d["교육내용"] or ""):
            d["교육내용상세"] = detail
    d["운영방법"] = field(flat, "운영방법")
    d["소요예산"] = field(flat, "소요예산")
    d["일시원문"] = field(flat, "교육일시", "교육기간")
    d.update({"일시": parse_datetime(d["일시원문"])})
    d["유형"] = detect_mode(flat, d["운영방법"])

    # 장소 — '대면 집합교육(본관 3층 대회의실)' 안쪽
    m = re.search(r"대면\s*집합교육\s*\(([^)]+)\)", flat)
    d["장소"] = m.group(1).strip() if m else None

    # 이러닝 달은 하루가 아니라 기간이다. '2026. 5. 12.(화) ~ 5. 31.(일)'
    m = re.search(r"~\s*(\d{1,2})\.\s*(\d{1,2})\.?\s*\(?([월화수목금토일])?\)?",
                  d.get("일시원문") or "")
    if m and d["일시"].get("연"):
        y = d["일시"]["연"]
        mo, dd = int(m.group(1)), int(m.group(2))
        wd = m.group(3)
        if not wd:
            wd = WEEK[datetime.date(y, mo, dd).weekday()]
        d["일시"]["종료표기"] = "%d. %d. %d.(%s)" % (y, mo, dd, wd)

    # 이러닝 수강처 (나라배움터 등)
    m = re.search(r"\(홈페이지\)\s*([^\n]+)", flat)
    if m:
        s = re.sub(r"\s+", " ", m.group(1)).strip()
        d["수강처"] = s
        mu = re.search(r"(https?://\S+)", s)
        d["수강처URL"] = mu.group(1) if mu else None
    # 이러닝 이수기준 (진도율)
    m = re.search(r"진도율\s*(\d+)\s*%", flat)
    if m:
        d["진도율"] = int(m.group(1))

    d["강사"] = parse_lecturer(t)

    # 상시학습 인정
    m = re.search(r"상시학습시간\s*인정\s*[:：]\s*([^\n]+)", flat)
    d["상시학습"] = re.sub(r"\s+", " ", m.group(1)).strip() if m else None
    m = re.search(r"(\d+)\s*시간\s*인정", flat)
    d["인정시간"] = int(m.group(1)) if m else None
    m = re.search(r"인정기준\s*[:：]\s*([^\n]+)", flat)
    d["인정기준"] = re.sub(r"\s+", " ", m.group(1)).strip() if m else None

    # 비대면 이수 기준
    m = re.search(r"비대면\s*교육\s*이수\s*기준\s*[:：]?\s*([^\n]+)", flat.replace(" ", " "))
    if not m:
        m = re.search(r"전체\s*교육\s*시간\s*(\d+)%\s*이상\s*이수", flat)
        d["이수기준"] = "전체 교육시간 %s%% 이상 이수" % m.group(1) if m else None
    else:
        d["이수기준"] = re.sub(r"\s+", " ", m.group(1)).strip()

    # 캠퍼스 특례 · 참석 예외
    m = re.search(r"(양산[·,\s]*밀양[^\n]*?(?:인정|참여[^\n]*))", flat)
    d["캠퍼스특례"] = re.sub(r"\s+", " ", m.group(1)).strip() if m else None
    # 줄바꿈으로 문장이 끊기므로 다음 항목 머리(-, ○, ※)를 만날 때까지 이어 붙인다
    m = re.search(r"(부서별\s*필수요원.+?)(?=\n\s*[-○ㅇ●※]|\Z)", flat, re.S)
    if m:
        s = re.sub(r"\s+", " ", m.group(1)).strip()
        # 쪽이 넘어가며 다음 장 제목이 딸려 온다 → 잘라낸다
        s = re.split(r"\s*(?:행정사항|교육운영\s*방법|교육개요|붙임)\b", s)[0].strip()
        d["참석예외"] = s
    else:
        d["참석예외"] = None

    # 근거 법령
    m = re.search(r"교육시행근거\s*[:：]\s*([^\n]+)", flat)
    d["근거"] = re.sub(r"\s+", " ", m.group(1)).strip() if m else None

    # 이러닝 강좌 표 · 준비사항
    if d["유형"] == "이러닝":
        d["강좌"] = parse_courses(t, d.get("월"))
        d["표경고"] = check_courses(d)
        m = re.search(r"교육\s*신청\s*전\s*([^\n*]+)", flat)
        d["준비사항"] = re.sub(r"\s+", " ", m.group(1)).strip() if m else None
        m = re.search(r"(모든\s*과목\s*이수\s*후[^\n]+)", flat.replace(" ", " "))
        d["이수확인"] = re.sub(r"\s+", "", m.group(1)).strip() if m else None
        m = re.search(r"(동일\s*연도[^\n]*?중복[^\n]*)", flat)
        d["중복이수"] = re.sub(r"\s+", " ", m.group(1)).strip() if m else None
        d["수강흐름"] = parse_flow(t)

    return d


# ------------------------------------------------------------------ 이러닝 강좌 표
def parse_courses(t, month=None):
    """이러닝 계획안의 강좌 표를 읽는다. 표는 PDF 에서 한 줄씩 풀려 나온다.

        구분 / 적극행정교육 / 갈등관리교육 / 강좌명 / [5월 직장교육] /
        국민의 생활을 / 바꾸는 적극행정 / [5월 직장교육] / 조직갈등 SOS! / ...
        / 인정시간 / 50분 / 1시간 10분 / 이수기준 / 진도율 100% / 이수사이트 / ...

    '구분'과 '인정시간'은 한 줄에 하나씩이라 그대로 읽고, 강좌명만 여러 줄로
    쪼개져 있어 '[N월 직장교육]' 표시를 기준으로 나눈다. (9건 확인, 모두 2강좌)"""
    m = re.search(r"\n\s*구분\s*\n(.*?)\n\s*강좌명\s*\n(.*?)\n\s*인정시간\s*\n(.*?)"
                  r"\n\s*이수기준\s*\n(.*?)\n\s*이수사이트\s*\n([^\n]+)", t, re.S)
    if not m:
        return []
    names = [s.strip() for s in m.group(1).split("\n") if s.strip()]
    times = [s.strip() for s in m.group(3).split("\n") if s.strip()]
    기준 = re.sub(r"\s+", " ", m.group(4)).strip()
    사이트 = re.sub(r"\s+", " ", m.group(5)).strip()

    tag = r"\[\s*%s월\s*직장교육\s*\]" % (month if month else r"\d+")
    parts = re.split(tag, m.group(2))
    titles = [re.sub(r"\s+", " ", p).strip() for p in parts[1:]]   # 첫 조각은 빈 앞머리

    out = []
    for i, name in enumerate(names):
        out.append({
            "구분": name,
            "강좌명": titles[i] if i < len(titles) else None,
            "태그": "[%s월 직장교육]" % month if month else None,
            "인정시간": times[i] if i < len(times) else None,
            "이수기준": 기준 or None,
            "이수사이트": 사이트 or None,
        })
    return out


def parse_flow(t):
    """'학습방법' 도표의 단계. PDF 에서 화살표가 한 줄씩 풀려 나온다.

        접속 / → / 수강신청 및 수강 / → / 교육이수 / → / 상시학습인정

    구성원 입장에서 '내가 무엇을 해야 하나'에 답하는 부분이라 포스터에 싣는다."""
    m = re.search(r"\n\s*접속\s*\n\s*→\s*\n(.*?)(?=\n\s*(?:부산대학교|개인별|\Z))",
                  t, re.S)
    if not m:
        return []
    steps = ["접속"] + [re.sub(r"\s+", " ", s).strip()
                        for s in re.split(r"\n\s*→\s*\n", m.group(1))]
    return [s for s in steps if s and len(s) <= 20]


def check_courses(d):
    """표의 '구분'이 교육내용과 어긋나면 알린다.

    2026년 1월 계획안이 그렇다 — 교육내용은 '폭력예방교육, 반부패·청렴교육'인데
    표의 구분은 '통일교육 / 갈등관리교육'(전달 계획안의 값)이다. 인정시간은
    폭력예방·반부패 값이라 구분 행만 안 고친 것으로 보인다.
    **임의로 고치지 않는다.** 담당자 확인에 맡기고 표시만 남긴다."""
    내용 = d.get("교육내용") or ""
    강좌 = d.get("강좌") or []
    if not 내용 or not 강좌:
        return None
    # '·' 로 자르면 안 된다. '반부패·청렴교육' 처럼 과목 이름 안에도 쓰인다.
    과목 = [s.strip() for s in re.split(r"\s*[,、]\s*", 내용) if s.strip()]
    구분 = [c["구분"] for c in 강좌]
    if len(과목) != len(구분):
        return "교육내용 %d건과 표의 구분 %d건이 다릅니다" % (len(과목), len(구분))
    def norm(s):
        return re.sub(r"\s+", "", s)
    어긋남 = [(a, b) for a, b in zip(과목, 구분)
              if norm(a) not in norm(b) and norm(b) not in norm(a)]
    if 어긋남:
        return ("교육내용과 표의 구분이 다릅니다 — " +
                " / ".join("교육내용 '%s' ↔ 표 '%s'" % ab for ab in 어긋남) +
                " (담당자 확인 필요, 임의로 고치지 않음)")
    return None


def report(d):
    print("■ %s" % d.get("원본파일"))
    print("  %s년 %s월 · 유형 %s" % (d.get("연도"), d.get("월"), d.get("유형")))
    rows = [
        ("교육내용", d.get("교육내용")),
        ("일시", (d.get("일시") or {}).get("날짜표기", "") + " " +
                 (d.get("일시") or {}).get("시간표기", "")),
        ("장소", d.get("장소")),
        ("대상", d.get("교육대상")),
        ("강사", (d.get("강사") or {}).get("성명")),
        ("강사소속", (d.get("강사") or {}).get("소속")),
        ("상시학습", d.get("상시학습")),
        ("이수기준", d.get("이수기준")),
        ("캠퍼스특례", d.get("캠퍼스특례")),
        ("참석예외", d.get("참석예외")),
        ("근거", d.get("근거")),
    ]
    miss = []
    for k, v in rows:
        v = (v or "").strip()
        if v:
            print("   %-8s %s" % (k, v[:78]))
        else:
            miss.append(k)
    if miss:
        print("   [비어 있음] %s  ← 지어내지 않고 비워 둔다" % ", ".join(miss))
    for i, c in enumerate(d.get("강좌") or [], 1):
        print("   강좌%d     %s · %s · %s" % (i, c["구분"], c["강좌명"], c["인정시간"]))
    if d.get("강좌"):
        c = d["강좌"][0]
        print("   이수      %s · %s" % (c["이수기준"], c["이수사이트"]))
    if d.get("준비사항"):
        print("   준비      %s" % d["준비사항"])
    if d.get("표경고"):
        print("   ⚠ 원자료 확인 필요 : %s" % d["표경고"])


def main(argv=None):
    ap = argparse.ArgumentParser(description="직장교육 계획(안) PDF/HWPX → 구조화 데이터")
    ap.add_argument("paths", nargs="+", help="계획(안) 파일 경로")
    ap.add_argument("--json", help="결과를 JSON 으로 저장")
    a = ap.parse_args(argv)

    out = []
    for p in a.paths:
        d = parse(p)
        out.append(d)
        report(d)
        print()
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(out if len(out) > 1 else out[0], f, ensure_ascii=False, indent=2)
        print("저장:", a.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
