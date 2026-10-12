# -*- coding: utf-8 -*-
"""직제 요구 자료 더미를 **검색할 수 있게** 색인한다.

왜 필요한가
-----------
정기직제는 제출이 끝이 아니다. 교육부·행안부·기재부가 **요구 건마다 따로**
자료를 요구하고, 그때마다 **「작년엔 뭐라고 썼지?」를 수백 개 파일에서 찾는다.**
2027년도 자료 639개 중 **522개(82%)가 제출 이후 대응**이었다.

그 더미의 정체는 **과거 9개년치 요구 이력 전체**다. 사람이 파일명만 보고
찾기에는 너무 많고, 파일명에 내용이 다 들어 있지도 않다.

그래서 **한 번 읽어 두고 찾을 수 있게** 만든다.

읽는 법
-------
    .hwp    olefile + zlib      ← 한글 프로그램 없이 (실측 94%)
    .hwpx   zip + XML
    .xlsx   openpyxl
    .pdf    fitz

**원본은 읽기만 한다.** 수정·이동·삭제하지 않는다.
"""

import hashlib
import io
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
from hwp_text import read_hwp

DIST_LOCK = "이 문서는 상위 버전의 배포용 문서입니다"

# 파일명 앞 6자리 = YYMMDD (이 부서의 파일명 규칙)
RE_FNAME_DATE = re.compile(r"^(\d{2})(\d{2})(\d{2})\b")
# 요구 연도 — 「2027년도」·「'27년」·「2027년」
RE_REQ_YEAR = re.compile(r"(20\d{2})\s*년도?|[’'‘](\d{2})\s*년")

KIND_RULES = [
    ("서식",   re.compile(r"\(서식|서식\)|부속서류")),
    ("요구서", re.compile(r"요구서")),
    ("배정결과", re.compile(r"정원\s*배정|정원표|정원\(20")),
    ("공문",   re.compile(r"공문|제출\s*안내|작성\s*요청|협조\s*요청|제출$")),
    ("보고",   re.compile(r"보고")),
    ("업무분장", re.compile(r"업무분장")),
    ("중기계획", re.compile(r"중기인력운영")),
]


def classify(name):
    for kind, rx in KIND_RULES:
        if rx.search(name):
            return kind
    return "참고"


def file_date(name):
    m = RE_FNAME_DATE.match(name)
    if not m:
        return ""
    yy, mm, dd = m.groups()
    y = 2000 + int(yy)
    if not (1 <= int(mm) <= 12 and 1 <= int(dd) <= 31):
        return ""
    return "%04d-%s-%s" % (y, mm, dd)


def _year_in(t):
    for m in RE_REQ_YEAR.finditer(t or ""):
        y = int(m.group(1)) if m.group(1) else 2000 + int(m.group(2))
        if 2015 <= y <= 2035:
            return y
    return None


def req_year(name, folder):
    """이 자료가 **몇 년도 직제**에 관한 것인지.

    **파일명 → 가장 깊은 폴더 → 바깥 폴더** 순으로 찾는다.
    바깥부터 보면 과거 자료가 전부 바깥 폴더의 연도로 묶인다 —
    2022년도 요구서가 「2027년도」로 분류되면 **「작년엔 뭐라고 썼지」에 답을 못 한다.**
    """
    y = _year_in(name)
    if y:
        return y
    for part in reversed(folder.replace("\\", "/").split("/")):
        y = _year_in(part)
        if y:
            return y
    return None


def read_hwpx(path):
    import xml.etree.ElementTree as ET
    import zipfile
    z = zipfile.ZipFile(path)
    NS = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
    out = []
    try:
        secs = sorted(n for n in z.namelist()
                      if re.match(r"Contents/section\d+\.xml", n))
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
                out.append("".join(buf))
    finally:
        z.close()
    return "\n".join(out)


def read_xlsx(path):
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    out = []
    try:
        for ws in wb.worksheets:
            out.append("[시트] " + str(ws.title))
            for row in ws.iter_rows(values_only=True):
                cells = ["" if c is None else str(c) for c in row]
                if any(c.strip() for c in cells):
                    out.append("\t".join(cells))
    finally:
        wb.close()
    return "\n".join(out)


def read_pdf(path):
    import fitz
    d = fitz.open(path)
    try:
        return "\n".join(p.get_text() for p in d)
    finally:
        d.close()


READERS = {".hwp": read_hwp, ".hwpx": read_hwpx,
           ".xlsx": read_xlsx, ".xls": read_xlsx, ".pdf": read_pdf}


def build(root, out_path):
    t0 = time.time()
    rows, stat = [], {}
    seen = {}
    for dp, _dn, fn in os.walk(root):
        for f in sorted(fn):
            ext = os.path.splitext(f)[1].lower()
            rd = READERS.get(ext)
            rel = os.path.relpath(os.path.join(dp, f), root)
            if rd is None:
                stat["건너뜀 " + ext] = stat.get("건너뜀 " + ext, 0) + 1
                continue
            path = os.path.join(dp, f)
            try:
                text = rd(path)
                note = ""
                if DIST_LOCK in text[:200]:
                    note, text = "배포용잠김", ""
            except Exception as e:
                note, text = "읽기실패: %s" % str(e)[:50], ""
            body = re.sub(r"[ \t]+", " ", (text or "")).strip()

            h = hashlib.md5(body.encode("utf-8")).hexdigest() if body else ""
            dup = seen.get(h) if h else None
            if h and dup is None:
                seen[h] = rel

            folder = os.path.relpath(dp, root)
            rows.append({
                "id": len(rows) + 1,
                "path": rel,
                "folder": folder,
                "name": f,
                "ext": ext,
                "date": file_date(f),
                "req_year": req_year(f, folder),
                "kind": classify(f),
                "chars": len(body),
                "note": note,
                "dup_of": dup,
                "text": body,
            })
            k = note.split(":")[0] if note else ext
            stat[k] = stat.get(k, 0) + 1

    io.open(out_path, "w", encoding="utf-8").write(
        json.dumps({"root": os.path.abspath(root), "built": time.strftime("%Y-%m-%d %H:%M"),
                    "files": rows}, ensure_ascii=False))

    ok = [r for r in rows if r["chars"] > 30 and not r["note"]]
    print("색인 %d건 · 읽힌 것 %d건 · %.1f초" % (len(rows), len(ok), time.time() - t0))
    print("크기 %.1f MB" % (os.path.getsize(out_path) / 1048576.0))
    print()
    print("형식·상태:", ", ".join("%s %d" % (k, v) for k, v in sorted(stat.items())))
    print()
    ys = {}
    for r in rows:
        if r["req_year"]:
            ys[r["req_year"]] = ys.get(r["req_year"], 0) + 1
    print("요구 연도별:", ", ".join("%d년도 %d건" % (y, n) for y, n in sorted(ys.items())))
    ks = {}
    for r in rows:
        ks[r["kind"]] = ks.get(r["kind"], 0) + 1
    print("자료 종류별:", ", ".join("%s %d" % (k, n) for k, n in
                                sorted(ks.items(), key=lambda x: -x[1])))
    ndup = sum(1 for r in rows if r["dup_of"])
    print("내용이 같은 중복본: %d건" % ndup)


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else "01.원본데이터",
          sys.argv[2] if len(sys.argv) > 2 else "02.작업/index.json")
