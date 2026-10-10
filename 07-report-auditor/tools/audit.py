# -*- coding: utf-8 -*-
"""보고서의 숫자를 원본과 대조한다 — 값과 정의, 양쪽으로.

왜 이 도구가 있는가
-------------------
4회차에서 담당자가 오류 6건을 직접 잡아야 했다. 전부 같은 경로였다 —
조사원의 요약을 그대로 옮겨 쓴 것.

5회차에서 감사역을 붙였더니 치명 3건을 잡았다. 그런데 그중 하나는
**값은 전부 맞는데 정의가 틀린** 것이었다. 1인당 학생 수를 내면서
분자는 「학부 재적 학생」, 분모는 「대학 및 대학원 직원」을 썼다.
값만 대조하는 감사는 이것을 통과시킨다.

그래서 이 도구는 두 가지를 같이 본다.

    값  — 보고서의 숫자가 원본 파일에 실제로 있는가
    정의 — 그 숫자를 그렇게 쓸 수 있는가 (모집단·기준일)

「확인 못 함」은 「맞다」가 아니다
---------------------------------
5회차 `alimi.py parse` 는 「불완전한 데이터는 쓰지 않는다」를 지침이 아니라
**종료코드**로 만들었고, 실제로 사고를 한 번 막았다. 지침은 안 읽고 넘어갈
수 있지만 종료코드는 못 넘어간다. 같은 장치를 여기에도 넣었다.

    0  전부 일치
    3  값 불일치 — 원본과 다른 숫자가 있다
    4  미발견·불가 — 원본에 없거나, 원본을 읽지 못했다
    5  정의 문제 — 정의를 원문에서 읽지 않았거나, 모집단이 어긋난다

**심각도는 5 > 3 > 4 다.** 번호 순서가 아니다.
5회차에서 값은 전부 맞는데 정의가 틀려 보고서 전체가 흔들렸기 때문이다.

이 도구는 판정하지 않는다
-------------------------
「이 보고서는 틀렸다」를 말하지 않는다. **대조할 거리를 정확히 들이밀 뿐이다.**
모집단이 다르면 「다릅니다, 쓸 수 있는지 확인하십시오」라고 한다.
판정은 사람이 한다.

쓰는 법
-------
    python audit.py claims 보고서.md -o claims.json
    python audit.py check  claims.json --source 원본1.tsv 원본2.xlsx --defs defs.json
    python audit.py stat   원본.tsv --col 총계_계
    python audit.py defs-template -o defs.json
"""

import argparse
import csv
import io
import json
import os
import re
import statistics
import sys
import xml.etree.ElementTree as ET
import zipfile

# 콘솔 코드페이지와 무관하게 UTF-8 로 내보낸다.
# cp949 콘솔에서 한글이 깨지면 출력만 망가지는 게 아니라, 파이프로 넘긴
# 다음 단계가 통째로 죽는다 (5회차에서 JS 가 그렇게 날아갔다).
try:
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    sys.stderr.reconfigure(encoding="utf-8", newline="\n")
except AttributeError:  # py2 호환 — 이 환경엔 없지만 방어로 둔다
    import codecs
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())


# ─────────────────────────────────────────────────────────────
# 종료코드
# ─────────────────────────────────────────────────────────────
EXIT_OK = 0
EXIT_MISMATCH = 3   # 값 불일치
EXIT_NOTFOUND = 4   # 미발견 · 원본 못 읽음
EXIT_DEFS = 5       # 정의 미확인 · 모집단 불일치


# ─────────────────────────────────────────────────────────────
# 1. 원본 읽기 — 파일 형식마다 다르게, 못 읽으면 못 읽었다고 말한다
# ─────────────────────────────────────────────────────────────

NS_HWPX = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def read_hwpx(path):
    """한글 .hwpx 는 zip + XML 이다.

    자식 요소의 tail 까지 이어 붙인다. 이것을 빠뜨리면 `<hp:fwSpace/>` 뒤가
    사라져 '’26. 3. 31.' 이 '’26.' 으로 잘린다 (3회차에서 겪었다).
    날짜와 수치가 조용히 잘리므로 원인이 안 보인다.
    """
    z = zipfile.ZipFile(path)
    secs = sorted(n for n in z.namelist()
                  if re.match(r"Contents/section\d+\.xml", n))
    if not secs:
        raise ValueError("Contents/sectionN.xml 이 없다 — hwpx 가 맞는지 확인할 것")
    lines = []
    for s in secs:
        root = ET.fromstring(z.read(s))
        for para in root.iter(NS_HWPX + "p"):
            buf = []
            for t in para.iter(NS_HWPX + "t"):
                if t.text:
                    buf.append(t.text)
                for ch in t:
                    if ch.tail:
                        buf.append(ch.tail)
            lines.append("".join(buf))
    return "\n".join(lines)


def read_hwp(path):
    """구형 .hwp 는 바이너리 OLE 라 이 도구로 못 읽는다.

    읽은 척하지 않는다. 못 읽었다는 사실이 결과에 남아야 한다 —
    조용히 건너뛰고 「대조 완료」라고 내는 쪽이 훨씬 위험하다.
    """
    raise ValueError(
        "구형 .hwp 는 파이썬으로 못 읽는다. 한글에서 .hwpx 로 저장해 다시 넣거나, "
        "`--hwp-com` 으로 한글(COM)을 띄워 변환할 것")


def _ps(cmd, timeout=25):
    import subprocess
    return subprocess.run(["powershell", "-NoProfile", "-Command", cmd],
                          capture_output=True, text=True, timeout=timeout)


def hwp_windows_open():
    """사용자가 열어 둔 한글 창이 있는지 센다."""
    try:
        r = _ps("(Get-Process Hwp -EA SilentlyContinue | "
                "Where-Object { $_.MainWindowHandle -ne 0 } | Measure-Object).Count")
        return int((r.stdout or "0").strip() or 0)
    except Exception:
        return -1      # 셀 수 없으면 모르는 것이다. 모르면 건드리지 않는다


def kill_headless_hwp():
    """창 없는 한글 프로세스를 치운다.

    `Quit()` 을 불러도 남는다. 실측에서 **두 개가 남았다.**
    남은 프로세스는 다음 실행을 막으므로, 쓴 사람이 치워야 한다.

    **`MainWindowHandle -eq 0` 조건은 절대 빼지 않는다.**
    창이 있는 한글은 사용자가 열어 둔 것이다.
    """
    try:
        _ps("Get-Process Hwp -EA SilentlyContinue | "
            "Where-Object { $_.MainWindowHandle -eq 0 } | Stop-Process -Force")
    except Exception:
        pass


def _purge_gen_py():
    """깨진 COM 타입라이브러리 캐시를 지운다 — 다음 호출에서 재생성된다.

    `EnsureDispatch` 가 `... has no attribute 'CLSIDToClassMap'` 로 죽으면
    캐시가 만들어지다 만 것이다. 실측에서 실제로 이 상태였고,
    **같은 방식을 쓰는 기존 스킬도 그때 같이 고장나 있었다.**
    늦은 바인딩으로 내려가면 이번엔 인자 개수가 안 맞아 또 막히므로,
    우회하지 말고 캐시를 고치는 쪽이 맞다.
    """
    import shutil
    import win32com
    for base in {os.path.join(os.environ.get("LOCALAPPDATA", ""), "Temp", "gen_py"),
                 os.path.join(os.path.dirname(win32com.__file__), "gen_py")}:
        if base and os.path.isdir(base):
            for sub in os.listdir(base):
                shutil.rmtree(os.path.join(base, sub), ignore_errors=True)


def read_hwp_via_com(path, workdir):
    """한글(HWP) COM 으로 .hwp → .hwpx 변환 후 읽는다.

    **창이 있는(사용자가 열어 둔) 한글은 절대 건드리지 않는다.**
    COM 은 이미 떠 있는 한글 인스턴스에 붙는다. 그 상태로 Open/SaveAs 를 부르면
    사용자가 작업 중인 문서가 밀려난다. 원본 대조 한 번 하자고 남의 작업을
    건드리는 것은 어떤 경우에도 수지가 안 맞는다.

    그래서 **지침이 아니라 거부로 막는다.** 이 도구의 다른 안전장치와 같은 방식이다.
    """
    n = hwp_windows_open()
    if n != 0:
        raise ValueError(
            "한글 창이 열려 있어 COM 변환을 하지 않았다(창 %s개). "
            "COM 은 떠 있는 한글에 붙으므로 작업 중인 문서를 건드릴 수 있다. "
            "한글을 모두 닫고 다시 실행하거나, 그 파일을 .hwpx 로 저장해 넣을 것"
            % ("알 수 없음" if n < 0 else n))

    try:
        import win32com.client as win32
    except ImportError:
        raise ValueError("pywin32 가 없어 COM 을 못 쓴다 (`pip install pywin32`)")

    out = os.path.join(workdir, os.path.basename(path) + "x")
    hwp = None
    try:
        try:
            hwp = win32.gencache.EnsureDispatch("HWPFrame.HwpObject")
        except AttributeError:
            _purge_gen_py()                     # 캐시가 깨졌다. 지우고 한 번만 다시
            import importlib
            importlib.reload(win32.gencache)
            hwp = win32.gencache.EnsureDispatch("HWPFrame.HwpObject")
        try:
            hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")
        except Exception:
            pass   # 보안 모듈이 없어도 열린다. 없으면 승인 창이 뜰 수 있다
        if not hwp.Open(os.path.abspath(path), "HWP", "forceopen:true"):
            raise ValueError("한글이 파일을 열지 못했다")
        hwp.SaveAs(os.path.abspath(out), "HWPX")
    finally:
        if hwp is not None:
            try:
                hwp.Quit()
            except Exception:
                pass
        del hwp
        kill_headless_hwp()     # Quit() 만으로는 안 죽는다. 실측에서 둘이 남았다
    return read_hwpx(out)


def read_xlsx(path):
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    lines = []
    for ws in wb.worksheets:
        for row in ws.iter_rows(values_only=True):
            cells = ["" if c is None else str(c) for c in row]
            if any(c.strip() for c in cells):
                lines.append("\t".join(cells))
    wb.close()
    return "\n".join(lines)


def read_pdf(path):
    import fitz
    d = fitz.open(path)
    t = "\n".join(p.get_text() for p in d)
    d.close()
    return t


def read_source(path, hwp_com=False, workdir=None):
    """원본 파일 하나를 텍스트로. 못 읽으면 ValueError 를 올린다."""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".md", ".txt", ".tsv", ".csv", ".json"):
        return io.open(path, encoding="utf-8", errors="replace").read()
    if ext == ".hwpx":
        return read_hwpx(path)
    if ext == ".hwp":
        if hwp_com:
            return read_hwp_via_com(path, workdir or os.path.dirname(path))
        return read_hwp(path)
    if ext in (".xlsx", ".xlsm"):
        return read_xlsx(path)
    if ext == ".pdf":
        return read_pdf(path)
    raise ValueError("지원하지 않는 형식: %s" % ext)


# ─────────────────────────────────────────────────────────────
# 2. 숫자 뽑기
# ─────────────────────────────────────────────────────────────

# 단위가 붙은 수만 「주장」으로 본다. 단위 없는 수는 절번호·연도·각주가
# 대부분이라, 전부 주워 담으면 잡음에 진짜 오류가 묻힌다.
UNITS = "명|%p|%|위|원|곳|개교|건|점|배|쪽|㎡|억|만"
NUM = r"[+\-−▲▼]?\d[\d,]*(?:\.\d+)?"

RE_CLAIM = re.compile(r"(?P<num>%s)\s*(?P<unit>%s)" % (NUM, UNITS))
RE_ANY_NUM = re.compile(NUM)

# 숫자처럼 보이지만 주장이 아닌 것 — 숫자를 뽑기 전에 지운다.
# 지우지 않고 뽑은 뒤 거르면 「§2-3」의 -3 이 「3 감소」로 들어온다.
RE_MASK = re.compile(
    r"§\s*\d+(?:[-–‑]\d+)*"      # §2-3
    r"|\[\^[^\]]*\]"              # 각주 참조 [^1]
    r"|\bv\d+(?:\.\d+)?\b"        # v1 · v0.5
    r"|\b\d+회차\b"
    r"|\b\d+-[가-힣]\b"           # 공시항목 번호 14-사
)

RE_NOISE = [
    re.compile(r"^(19|20)\d\d$"),             # 연도
    re.compile(r"^\d{1,2}$"),                 # 한두 자리 (절번호·각주·순번)
]


def norm_num(s):
    """'1,085' → 1085.0 / '−56' → -56.0 / '+1.5' → 1.5"""
    s = s.replace(",", "").replace("−", "-").replace("▲", "+").replace("▼", "-")
    s = s.lstrip("+")
    try:
        return float(s)
    except ValueError:
        return None


def mask(line):
    """절번호·각주·판본번호를 같은 길이의 공백으로 덮는다.

    길이를 유지해야 뒤에서 뽑은 위치(`m.start()`)가 원문과 어긋나지 않는다.
    """
    return RE_MASK.sub(lambda m: " " * len(m.group(0)), line)


def is_noise(raw, val, unit=""):
    """단위가 붙었으면 한두 자리여도 주장이다.

    '+14명' 을 「두 자리라 잡음」으로 버리면 5개년 증감이 통째로 빠진다.
    단위 없는 한두 자리만 버린다 — 표의 순번 열 따위다.
    """
    if val is None:
        return True
    bare = raw.replace(",", "").lstrip("+-−▲▼")
    if unit:
        return bool(RE_NOISE[0].match(bare))      # 연도만 거른다
    for r in RE_NOISE:
        if r.match(bare):
            return True
    return False


# 문장 경계 — 소수점은 경계가 아니다 ('21.7' 이 '21' 과 '7' 로 갈리면 안 된다)
RE_BOUND = re.compile(r"[。!?·|]|\.(?!\d)")


def split_sentence(line, pos):
    """숫자가 들어 있는 문장 한 토막만 잘라 낸다 (문맥 표시용)."""
    left = 0
    for m in RE_BOUND.finditer(line, 0, pos):
        left = m.end()
    m = RE_BOUND.search(line, pos)
    right = m.start() if m else len(line)
    s = line[left:right].strip()
    return s if s else line.strip()


def extract_claims(path):
    """보고서(.md)에서 숫자 주장을 뽑는다.

    본문과 마크다운 표를 모두 본다. 보고서 숫자의 대부분이 표 안에 있고,
    표는 단위가 머리글에만 적히므로 셀은 단위 없이도 주장으로 본다.
    """
    text = io.open(path, encoding="utf-8").read()
    claims = []
    section = ""
    seq = 0

    for ln, line in enumerate(text.split("\n"), 1):
        st = line.strip()

        if st.startswith("#"):
            section = st.lstrip("#").strip()
            continue
        if st.startswith("[^") and "]:" in st:   # 각주 정의
            continue

        in_table = st.startswith("|")
        if in_table and set(st) <= set("|-: "):   # 표 구분선
            continue

        if in_table:
            cells = [c.strip() for c in st.strip("|").split("|")]
            label = ""
            for cell in cells:
                t = re.sub(r"[*`]", "", cell).strip()
                if t and not RE_ANY_NUM.fullmatch(t):
                    label = t[:40]
                    break
            for cell in cells:
                plain = mask(re.sub(r"[*`]", "", cell))
                if plain.strip()[:40] == label and label:
                    continue   # 라벨 칸 자신의 숫자는 주장이 아니다 (「9곳 평균」의 9)
                for m in RE_ANY_NUM.finditer(plain):
                    raw = m.group(0)
                    val = norm_num(raw)
                    um = re.match(r"\s*(%s)" % UNITS, plain[m.end():])
                    if is_noise(raw, val, um.group(1) if um else ""):
                        continue
                    seq += 1
                    claims.append({
                        "id": "C%03d" % seq, "line": ln, "section": section,
                        "where": "표", "label": label,
                        "raw": raw, "value": val,
                        "unit": um.group(1) if um else "",
                        "pre": plain[max(0, m.start() - 12):m.start()],
                        "context": plain.strip()[:120],
                    })
        else:
            for m in RE_CLAIM.finditer(mask(line)):
                raw, unit = m.group("num"), m.group("unit")
                val = norm_num(raw)
                if is_noise(raw, val, unit):
                    continue
                seq += 1
                claims.append({
                    "id": "C%03d" % seq, "line": ln, "section": section,
                    "where": "본문", "label": "",
                    "raw": raw, "value": val, "unit": unit,
                    "pre": line[max(0, m.start() - 12):m.start()],
                    "context": split_sentence(line, m.start())[:120],
                })
    return claims


# ─────────────────────────────────────────────────────────────
# 3. 원본과 대조
# ─────────────────────────────────────────────────────────────

def index_source(text):
    """원본 텍스트에서 모든 수를 뽑아 {값: [설명, ...]} 로."""
    idx = {}
    for ln, line in enumerate(text.split("\n"), 1):
        for m in RE_ANY_NUM.finditer(line):
            v = norm_num(m.group(0))
            if v is None:
                continue
            idx.setdefault(v, []).append("원본 %d줄" % ln)
    return idx


def index_derived(path, group_col=None, group_strip=None):
    """표 원본(.tsv/.csv)에서 **계산해야 나오는 값**까지 인덱스에 넣는다.

    보고서의 숫자가 원본에 그대로 없는 것은 대부분 정상이다 —
    캠퍼스를 합치고, 평균을 내고, 순위를 매긴 값이기 때문이다.
    그것을 전부 「미발견」으로 던지면 사람이 한 건씩 손으로 가려야 하고,
    그 더미 속에 진짜 오류가 묻힌다.

    그래서 합·평균·중앙값까지 미리 계산해 두고 **어떻게 나온 값인지**를 같이 돌려준다.

    5회차에서 캠퍼스 합산을 하다 **열이 하나 밀려 부산대가 1,567명**이 된 적이 있다.
    여기서 합산을 다시 계산하므로, 그런 값은 끝내 안 맞는다.
    """
    delim = "\t" if path.lower().endswith(".tsv") else ","
    rows = list(csv.DictReader(io.open(path, encoding="utf-8"), delimiter=delim))
    if not rows:
        return {}

    cols = list(rows[0].keys())
    numcols = [c for c in cols
               if sum(1 for r in rows if norm_num(r.get(c) or "") is not None) > len(rows) * 0.6]

    idx = {}
    # 통계값은 따로도 모은다. 「중앙값」이라고 적힌 숫자는 **원본에 그 값이
    # 있더라도** 통계와 맞는지 봐야 하기 때문이다.
    # 5회차에서 9곳 중앙값을 847 로 적었는데, 847 은 충남대 총계라 원본에
    # 버젓이 있다. 존재 대조만 하는 감사는 이것을 그냥 통과시킨다.
    stats = {"중앙값": set(), "평균": set(), "합": set()}

    def put(v, how, kind=None):
        if v is not None:
            idx.setdefault(round(v, 4), []).append(how)
            if kind:
                stats[kind].add(round(v, 4))

    # ① 그룹 합산 — 캠퍼스가 여러 행인 대학의 합계가 여기서 나온다.
    #    한 기관이 여러 행으로 공시되는 것은 공공데이터에서 흔하다
    #    (본교/분교, 본원/지원). 행 이름이 「강원대학교_제2캠퍼스」처럼
    #    접미사로 갈리므로, 그 접미사를 떼어 같은 기관으로 묶는다.
    if group_col and group_col in cols:
        strip = re.compile(group_strip) if group_strip else None
        groups = {}
        for r in rows:
            key = r.get(group_col, "")
            if strip:
                key = strip.sub("", key)
            groups.setdefault(key, []).append(r)
        for g, rs in groups.items():
            if len(rs) < 2:
                continue
            for c in numcols:
                vs = [norm_num(r.get(c) or "") for r in rs]
                vs = [v for v in vs if v is not None]
                if len(vs) == len(rs):
                    put(sum(vs), "%s %d행 합 · %s" % (g, len(rs), c))

    # ② 열별 통계 — 평균·중앙값을 썼다면 여기서 맞아야 한다
    for c in numcols:
        vs = [norm_num(r.get(c) or "") for r in rows]
        vs = [v for v in vs if v is not None]
        if len(vs) < 2:
            continue
        put(sum(vs), "%s 전체 합" % c, "합")
        put(round(statistics.mean(vs), 1), "%s 평균" % c, "평균")
        put(statistics.median(vs), "%s 중앙값" % c, "중앙값")

    # 그룹 합산을 했다면 그 합들의 통계도 쓴다 —
    # 「9곳 중앙값」은 캠퍼스를 합친 9개 값의 중앙값이지, 원본 행들의 중앙값이 아니다.
    if group_col and group_col in cols:
        strip = re.compile(group_strip) if group_strip else None
        gsum = {}
        for r in rows:
            key = r.get(group_col, "")
            if strip:
                key = strip.sub("", key)
            for c in numcols:
                v = norm_num(r.get(c) or "")
                if v is not None:
                    gsum.setdefault(c, {}).setdefault(key, 0.0)
                    gsum[c][key] += v
        for c, d in gsum.items():
            vs = list(d.values())
            if len(vs) < 2:
                continue
            put(round(statistics.mean(vs), 1), "%s 그룹합 평균" % c, "평균")
            put(statistics.median(vs), "%s 그룹합 중앙값" % c, "중앙값")

    return idx, stats


def nearest(idx, val, k=3):
    """미발견일 때 원본에서 가장 가까운 값들 — 「불일치」의 실질이다."""
    if not idx:
        return []
    cand = sorted(idx.keys(), key=lambda v: (abs(v - val), v))[:k]
    return [{"값": v, "차이": round(v - val, 4)} for v in cand if v != val]


RE_STAT_WORD = re.compile(r"중앙값|평균|합계|총계|소계")

# 어느 통계를 말하는지 — 「9곳 중앙값」이면 중앙값과 맞아야 한다.
#
# **「총계」를 넣으면 안 된다.** 한국어에서 총계는 통계 연산이 아니라
# 열 이름으로 훨씬 자주 쓰인다 — 「직원 총계 944명」은 그 학교의 값이지
# 9곳의 합이 아니다. 넣어 봤더니 거짓 지적이 일곱 건 쏟아졌다.
#
# 그리고 통계어 **바로 뒤**에 숫자가 와야 한다. 「중앙값보다 0.4명 위」의
# 0.4 는 중앙값이 아니라 중앙값과의 차이다. 조사가 붙으면 비교지 값이 아니다.
# 조사까지는 허용한다 — 「중앙값은 847명」의 847 은 중앙값이다.
# 다만 「중앙값보다 0.4명 위」의 0.4 는 차이지 중앙값이 아니므로
# '보다 · 대비 · 와 · 과 · 에서' 는 받지 않는다.
_TAIL = r"(?:은|는|이|가)?\s*[(\[:]?\s*$"
STAT_KIND = [(re.compile(r"중앙값" + _TAIL), "중앙값"),
             (re.compile(r"평균" + _TAIL), "평균"),
             (re.compile(r"합계" + _TAIL), "합")]
STAT_LABEL = [(re.compile(r"중앙값\s*$"), "중앙값"),
              (re.compile(r"평균\s*$"), "평균"),
              (re.compile(r"합계\s*$"), "합")]


def stat_kind_of(c):
    """주장이 어떤 통계를 자처하는지.

    **문장 전체를 보면 안 된다.** 「… 21.7명으로 3위(중앙값 21.3)다」 한 문장에
    21.7 · 3 · 21.3 이 들어 있는데, 중앙값인 것은 21.3 하나뿐이다.
    문맥으로 판정하면 나머지 둘까지 「중앙값이 아니다」라고 잡아내
    거짓 지적이 쏟아진다 — 그러면 진짜 오류가 그 속에 묻힌다.

    그래서 **표의 행 라벨**과 **숫자 바로 앞 12자**만 본다.
    """
    for rx, kind in STAT_LABEL:
        if rx.search((c.get("label") or "").strip()):
            return kind
    for rx, kind in STAT_KIND:
        if rx.search(c.get("pre") or ""):
            return kind
    return None


def grade_unfound(c):
    """원본에 없는 숫자를 등급으로 가른다.

    「전부 확인하라」는 확인하지 말라는 말과 같다. 56건을 한 줄로 던지면
    사람이 손으로 가려야 하고, 그 더미 안에 진짜 오류가 묻힌다.

    가장 위험한 것은 **단위가 명이고 부호도 소수점도 없는 정수**다.
    그런 숫자는 원본에 있어야 정상인데 없다 — 옮겨 적다 틀렸거나, 지어낸 값이다.
    """
    if stat_kind_of(c):
        return "검산필요"          # 중앙값·평균이라고 적혀 있다. stat 으로 다시 계산할 것
    if c.get("unit") in ("%", "%p", "위", "배", "곳", "개교"):
        # 「9곳」·「10개교」는 비교 대상의 개수지 데이터 값이 아니다.
        # 원본에 없는 것이 정상이라, 설명 요구에 끼면 잡음만 된다.
        return "파생값"
    if not float(c["value"]).is_integer():
        return "파생값"
    if c["raw"][:1] in "+-−▲▼":
        return "파생값"            # 증감
    return "설명필요"              # ← 여기가 진짜 위험구간


def check_values(claims, sources, hwp_com=False, workdir=None,
                 group_col=None, group_strip=None):
    direct, derived, stats, unreadable = {}, {}, {}, []
    for sp in sources:
        try:
            direct[sp] = index_source(read_source(sp, hwp_com, workdir))
        except Exception as e:
            unreadable.append({"파일": os.path.basename(sp), "이유": str(e)})
            continue
        if sp.lower().endswith((".tsv", ".csv")):
            try:
                derived[sp], stats[sp] = index_derived(sp, group_col, group_strip)
            except Exception:
                pass   # 파생값 인덱스는 보조다. 실패해도 직접 대조는 살아 있다

    rows = []
    for c in claims:
        v = round(c["value"], 4)

        # ① 통계를 자처하는 숫자는 **원본에 그 값이 있어도** 통계와 대조한다.
        #    847 은 충남대 총계라 원본에 있다. 그런데 9곳 중앙값은 867 이다.
        kind = stat_kind_of(c)
        if kind and stats:
            pool = set()
            for sp in stats:
                pool |= stats[sp].get(kind, set())
            if pool:
                if v in pool:
                    rows.append(dict(c, 결과="일치(통계)", 근거=[{"유형": kind}]))
                else:
                    cand = sorted(pool, key=lambda x: abs(x - c["value"]))[:3]
                    rows.append(dict(c, 결과="통계불일치", 통계=kind,
                                     원본통계=[{"값": x, "차이": round(x - c["value"], 4)}
                                            for x in cand]))
                continue

        hits = [{"파일": os.path.basename(sp), "근거": idx[v][:3], "유형": "원본"}
                for sp, idx in direct.items() if v in idx]
        if hits:
            rows.append(dict(c, 결과="일치", 근거=hits))
            continue

        calc = [{"파일": os.path.basename(sp), "근거": idx[v][:3], "유형": "계산"}
                for sp, idx in derived.items() if v in idx]
        if calc:
            rows.append(dict(c, 결과="일치(계산)", 근거=calc))
            continue

        near = []
        for sp, idx in direct.items():
            for n in nearest(idx, c["value"]):
                near.append(dict(n, 파일=os.path.basename(sp)))
        near.sort(key=lambda d: abs(d["차이"]))
        rows.append(dict(c, 결과="미발견", 등급=grade_unfound(c), 근접값=near[:3]))
    return rows, unreadable


# ─────────────────────────────────────────────────────────────
# 4. 정의 감사 — 이 도구의 핵심
# ─────────────────────────────────────────────────────────────

DEFS_TEMPLATE = {
    "_설명": "지표마다 원문을 직접 읽어 채운다. 「원문」 칸이 비면 종료코드 5 로 떨어진다.",
    "지표": {
        "<지표ID 예: 14-사>": {
            "이름": "",
            "공시기관": "",
            "모집단": "이 숫자가 세는 대상. 포함·제외를 그대로 적는다",
            "기준일": "YYYY-MM-DD",
            "출처": "파일명 · 쪽",
            "원문": "지침서에서 그대로 옮긴 문장. 요약하지 않는다"
        }
    },
    "파생지표": {
        "<이름 예: 직원 1인당 학생 수>": {"분자": "<지표ID>", "분모": "<지표ID>"}
    }
}


def check_defs(defs):
    """정의 파일을 감사한다. 판정하지 않고 「어긋난 곳」을 들이민다."""
    issues = []
    if not defs:
        return [{"급": "정의미확인", "무엇": "정의 파일이 없다",
                 "확인할 것": "보고서가 쓴 지표의 정의를 원문에서 읽어 defs.json 에 적을 것"}]

    ind = defs.get("지표", {})
    for key, d in ind.items():
        if key.startswith("<"):
            continue
        for must in ("모집단", "기준일", "원문"):
            if not str(d.get(must, "")).strip():
                issues.append({
                    "급": "정의미확인", "지표": key,
                    "무엇": "「%s」 칸이 비어 있다" % must,
                    "확인할 것": "지침서 원문을 열어 채울 것. 요약본·조사원 메모는 근거가 아니다"})

    for name, d in defs.get("파생지표", {}).items():
        if name.startswith("<"):
            continue
        a, b = d.get("분자"), d.get("분모")
        da, db = ind.get(a), ind.get(b)
        if not da or not db:
            issues.append({
                "급": "정의미확인", "파생지표": name,
                "무엇": "분자(%s) 또는 분모(%s)의 정의가 없다" % (a, b),
                "확인할 것": "양쪽 모두 원문으로 확인할 것"})
            continue

        pa, pb = str(da.get("모집단", "")).strip(), str(db.get("모집단", "")).strip()
        if pa != pb:
            issues.append({
                "급": "모집단불일치", "파생지표": name,
                "무엇": "분자와 분모가 세는 대상이 다르다",
                "분자": "%s — %s" % (a, pa),
                "분모": "%s — %s" % (b, pb),
                "확인할 것": "이 둘을 나눌 수 있는지 확인할 것. "
                            "다른 모집단을 나누면 값이 맞아도 지표가 틀린다"})

        ba, bb = str(da.get("기준일", "")).strip(), str(db.get("기준일", "")).strip()
        if ba != bb:
            issues.append({
                "급": "기준일불일치", "파생지표": name,
                "무엇": "분자와 분모의 기준일이 다르다",
                "분자": "%s — %s" % (a, ba), "분모": "%s — %s" % (b, bb),
                "확인할 것": "그 사이의 변동이 값에 안 들어 있다. 각주로 밝힐 것"})
    return issues


# ─────────────────────────────────────────────────────────────
# 5. 통계 재계산 — 값이 원본에 있어도 계산이 틀릴 수 있다
# ─────────────────────────────────────────────────────────────

def cmd_stat(args):
    """원본 한 열의 통계를 다시 계산한다.

    5회차에서 「9곳 중앙값 847」이 틀렸다(정답 867). 847 은 충남대 총계로
    **원본에 실제로 있는 값**이라, 존재 대조로는 절대 안 잡힌다.
    내림차순 6번째를 중앙값으로 잘못 센 것이었다.
    """
    rows = list(csv.DictReader(io.open(args.source, encoding="utf-8"),
                               delimiter="\t" if args.source.lower().endswith(".tsv") else ","))
    if args.col not in (rows[0].keys() if rows else []):
        print("열 이름이 없다: %s" % args.col, file=sys.stderr)
        print("있는 열: %s" % ", ".join(rows[0].keys() if rows else []), file=sys.stderr)
        return 2

    # 모집단을 좁힌다. 「9곳 중앙값」을 검산하려면 10번째 학교를 빼야 한다 —
    # 이 한 줄을 빠뜨리면 873.5 가 나오고, 867 과 맞춰 보지 못한다.
    for f in args.filter or []:
        if "!=" in f:
            k, _, v = f.partition("!=")
            rows = [r for r in rows if r.get(k.strip(), "") != v.strip()]
        else:
            k, _, v = f.partition("=")
            rows = [r for r in rows if r.get(k.strip(), "") == v.strip()]

    vals, labels = [], []
    for r in rows:
        v = norm_num(r[args.col] or "")
        if v is not None:
            vals.append(v)
            labels.append(r.get(args.label or "", "") if args.label else "")

    if not vals:
        print("값이 없다", file=sys.stderr)
        return 2

    pairs = sorted(zip(vals, labels), reverse=True)
    print("# %s · %s (n=%d)" % (os.path.basename(args.source), args.col, len(vals)))
    if args.filter:
        print("# 필터: %s" % " ".join(args.filter))
    print()
    print("| 통계 | 값 |")
    print("|---|---|")
    print("| 합계 | %s |" % fmt(sum(vals)))
    print("| 평균 | %s |" % fmt(statistics.mean(vals)))
    print("| **중앙값** | **%s** |" % fmt(statistics.median(vals)))
    print("| 최대 | %s |" % fmt(max(vals)))
    print("| 최소 | %s |" % fmt(min(vals)))
    print()
    n = len(vals)
    mid = (n + 1) // 2
    if n % 2:
        print("## 내림차순 — 중앙값은 %d개 중 **%d번째**다" % (n, mid))
    else:
        # 짝수면 가운데가 둘이다. 「k번째」로 적으면 그 자체가 중앙값 오산을 부른다.
        print("## 내림차순 — %d개는 짝수라 중앙값은 **%d·%d번째의 평균**이다"
              % (n, n // 2, n // 2 + 1))
    print()
    print("| 순위 | 값 | %s |" % (args.label or ""))
    print("|---|---|---|")
    for i, (v, lb) in enumerate(pairs, 1):
        if n % 2 and i == mid:
            mark = "  ← **중앙값**"
        elif not n % 2 and i in (n // 2, n // 2 + 1):
            mark = "  ← 가운데"
        else:
            mark = ""
        print("| %d | %s | %s%s |" % (i, fmt(v), lb, mark))
    return EXIT_OK


def fmt(v):
    return ("%,.0f" % v).replace("%", "") if False else (
        "{:,.0f}".format(v) if float(v).is_integer() else "{:,.2f}".format(v))


# ─────────────────────────────────────────────────────────────
# 6. 명령
# ─────────────────────────────────────────────────────────────

def cmd_claims(args):
    claims = extract_claims(args.report)
    out = args.out or (os.path.splitext(args.report)[0] + ".claims.json")
    io.open(out, "w", encoding="utf-8").write(
        json.dumps(claims, ensure_ascii=False, indent=1))
    tbl = sum(1 for c in claims if c["where"] == "표")
    print("주장 %d건 추출 (본문 %d · 표 %d) → %s"
          % (len(claims), len(claims) - tbl, tbl, out))
    return EXIT_OK


def cmd_check(args):
    claims = json.loads(io.open(args.claims, encoding="utf-8").read())
    rows, unreadable = check_values(claims, args.source, args.hwp_com,
                                    args.workdir, args.group, args.group_strip)

    defs = None
    if args.defs:
        defs = json.loads(io.open(args.defs, encoding="utf-8").read())
    def_issues = check_defs(defs)

    n = lambda k: sum(1 for r in rows if r["결과"] == k)
    bad = [r for r in rows if r["결과"] == "미발견"]
    mism = [r for r in rows if r["결과"] == "통계불일치"]
    g = lambda k: [b for b in bad if b["등급"] == k]

    result = {"대조": rows, "못읽은파일": unreadable, "정의": def_issues,
              "요약": {"주장": len(rows), "일치": n("일치"), "일치(계산)": n("일치(계산)"),
                     "일치(통계)": n("일치(통계)"), "통계불일치": len(mism),
                     "설명필요": len(g("설명필요")), "검산필요": len(g("검산필요")),
                     "파생값": len(g("파생값")), "못읽은파일": len(unreadable),
                     "정의지적": len(def_issues)}}
    if args.out:
        io.open(args.out, "w", encoding="utf-8").write(
            json.dumps(result, ensure_ascii=False, indent=1))

    print_report(result)

    # 심각도 순으로 하나를 돌려준다 — 정의가 가장 위다.
    # 5회차에서 값은 전부 맞는데 정의가 틀려 보고서 전체가 흔들렸다.
    if def_issues:
        return EXIT_DEFS
    if mism:
        return EXIT_MISMATCH
    if unreadable or g("설명필요"):
        return EXIT_NOTFOUND
    return EXIT_OK


def _tbl(rowset, note=None):
    print("| ID | 줄 | 절 | 숫자 | 문맥 | 원본의 근접값 |")
    print("|---|---|---|---|---|---|")
    for b in rowset:
        near = " · ".join("%s(%+g)" % (fmt(x["값"]), x["차이"])
                          for x in b.get("근접값", [])) or "—"
        print("| %s | %d | %s | **%s%s** | %s | %s |"
              % (b["id"], b["line"], (b["section"] or "")[:16],
                 b["raw"], b["unit"], b["context"][:44].replace("|", "/"), near))
    if note:
        print("\n> %s" % note)
    print()


def print_report(r):
    s = r["요약"]
    print("# 대조 결과\n")
    print("주장 **%d건** — 원본 확인 %d · 계산 확인 %d · 통계 확인 %d · "
          "**통계 불일치 %d** · **설명 필요 %d** · 검산 필요 %d · 파생값 %d\n"
          % (s["주장"], s["일치"], s["일치(계산)"], s["일치(통계)"],
             s["통계불일치"], s["설명필요"], s["검산필요"], s["파생값"]))

    if r["정의"]:
        print("## 1. 정의 — 값보다 먼저 본다\n")
        for i in r["정의"]:
            print("### [%s] %s" % (i["급"], i["무엇"]))
            for k, v in i.items():
                if k not in ("급", "무엇"):
                    print("- **%s** : %s" % (k, v))
            print()

    if r["못읽은파일"]:
        print("## 2. 읽지 못한 원본 — 「확인 못 함」은 「맞다」가 아니다\n")
        for u in r["못읽은파일"]:
            print("- `%s` — %s" % (u["파일"], u["이유"]))
        print()

    mism = [x for x in r["대조"] if x["결과"] == "통계불일치"]
    if mism:
        print("## 3. 통계값이 원본과 어긋난다 %d건 ← 가장 먼저 본다\n" % len(mism))
        print("| ID | 줄 | 절 | 자처 | 보고서 | 원본의 같은 통계 | 문맥 |")
        print("|---|---|---|---|---|---|---|")
        for b in mism:
            cand = " · ".join("%s(%+g)" % (fmt(x["값"]), x["차이"])
                              for x in b.get("원본통계", [])) or "—"
            print("| %s | %d | %s | %s | **%s%s** | %s | %s |"
                  % (b["id"], b["line"], (b["section"] or "")[:14], b["통계"],
                     b["raw"], b["unit"], cand,
                     b["context"][:30].replace("|", "/")))
        print("\n> 통계값이라고 적어 놓고 **제출된 원본의 어느 열 통계와도 맞지 않는다.**\n"
              "> 원본에 그 숫자가 있어도 통계로는 틀렸다는 뜻이다. 셋 중 하나다 —\n"
              ">\n"
              "> ⓐ **계산이 틀렸다** (5회차에서 9곳 중앙값을 847 로 적었다. 정답은 867)\n"
              "> ⓑ **원본의 일부만 골라 계산했는데 그 부분집합이 제출되지 않았다**\n"
              "> ⓒ **그 지표의 원본 자체가 없다** (파생지표를 만들어 놓고 원본을 안 냈다)\n"
              ">\n"
              "> `audit.py stat <원본> --col <열> --filter '열!=값'` 으로 모집단을 좁혀\n"
              "> 다시 계산하면 셋이 갈린다. **가리지 않고 넘기지 말 것.**\n")

    bad = [x for x in r["대조"] if x["결과"] == "미발견"]
    grp = lambda k: [b for b in bad if b["등급"] == k]

    if grp("설명필요"):
        print("## 3. 설명이 필요한 숫자 %d건 ← 먼저 본다\n" % len(grp("설명필요")))
        _tbl(grp("설명필요"),
             "부호도 소수점도 없는 정수인데 원본에 없다. **옮겨 적다 틀렸거나 "
             "지어낸 값**일 수 있다. 근접값이 가까우면 오타를 의심한다.")

    if grp("검산필요"):
        print("## 4. 중앙값·평균이라고 적힌 숫자 %d건\n" % len(grp("검산필요")))
        _tbl(grp("검산필요"),
             "통계값이라고 써 놓고 원본의 통계와 안 맞는다. "
             "`audit.py stat <원본> --col <열>` 로 다시 계산해 볼 것. "
             "**5회차에서 9곳 중앙값을 847 로 적었는데 정답은 867 이었다.**")

    if grp("파생값"):
        print("## 5. 파생값 %d건 (비율·순위·증감) — 원본에 없는 것이 정상\n"
              % len(grp("파생값")))
        _tbl(grp("파생값")[:15],
             "계산식이 보고서에 적혀 있는지만 본다. 15건까지만 보인다.")


def cmd_defs_template(args):
    out = args.out or "defs.json"
    io.open(out, "w", encoding="utf-8").write(
        json.dumps(DEFS_TEMPLATE, ensure_ascii=False, indent=1))
    print("정의 파일 뼈대 → %s" % out)
    print("「원문」 칸은 지침서를 직접 열어 채운다. 요약본은 근거가 아니다.")
    return EXIT_OK


def main():
    p = argparse.ArgumentParser(
        prog="audit.py", description="보고서의 숫자를 원본과 대조한다 — 값과 정의, 양쪽으로")
    sub = p.add_subparsers(dest="cmd")

    a = sub.add_parser("claims", help="보고서에서 숫자 주장을 뽑는다")
    a.add_argument("report")
    a.add_argument("-o", "--out")
    a.set_defaults(fn=cmd_claims)

    b = sub.add_parser("check", help="원본과 대조한다")
    b.add_argument("claims")
    b.add_argument("--source", nargs="+", required=True)
    b.add_argument("--defs")
    b.add_argument("-o", "--out")
    b.add_argument("--group", help="이 열의 값이 같은 행들을 합산해 둔다 (예: 학교). "
                                   "캠퍼스가 여러 행인 대학의 합계가 여기서 나온다")
    b.add_argument("--group-strip", metavar="정규식",
                   help="그룹 키에서 이 패턴을 떼고 묶는다 "
                        r"(예: '_제\d+캠퍼스$' — 강원대학교_제2캠퍼스 → 강원대학교)")
    b.add_argument("--hwp-com", action="store_true",
                   help="구형 .hwp 를 한글(COM)로 변환해 읽는다")
    b.add_argument("--workdir", help="COM 변환본을 둘 폴더")
    b.set_defaults(fn=cmd_check)

    c = sub.add_parser("stat", help="원본 한 열을 다시 계산한다")
    c.add_argument("source")
    c.add_argument("--col", required=True)
    c.add_argument("--label", help="같이 보여 줄 이름 열 (예: 학교)")
    c.add_argument("--filter", nargs="*", help="열=값")
    c.set_defaults(fn=cmd_stat)

    d = sub.add_parser("defs-template", help="정의 파일 뼈대를 만든다")
    d.add_argument("-o", "--out")
    d.set_defaults(fn=cmd_defs_template)

    args = p.parse_args()
    if not getattr(args, "fn", None):
        p.print_help()
        return 2
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
