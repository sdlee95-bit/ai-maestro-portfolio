# -*- coding: utf-8 -*-
"""공공기관 게시판의 첨부파일(.hwpx/.hwp/.pdf)을 내려받아 본문 텍스트를 뽑는다.

교육부·부산시·연구재단 게시판은 본문에 요약만 싣고 **상세 내용을 전부 첨부로
넘긴다.** 그래서 웹 본문만 읽으면 전담인력 요건·사업비 집행 기준 같은 정작
필요한 대목이 빠진다. 조사원이 실제로 그 지점에서 막혔다.

    python fetch_attachment.py <URL> [--out 저장폴더] [--text]

HWPX 파싱은 3회차 `plan_extract.py` 와 같은 방식이다 — `<hp:t>` 의 `.text` 만
이으면 자식 요소 뒤의 `tail` 이 빠져 날짜·수치가 잘리므로 `tail` 까지 이어 붙인다.
"""
import argparse
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from urllib.parse import unquote, urlparse

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def download(url, outdir):
    os.makedirs(outdir, exist_ok=True)
    r = requests.get(url, headers={"User-Agent": UA}, timeout=60, stream=True)
    r.raise_for_status()

    # 파일명은 Content-Disposition 이 먼저, 없으면 URL 에서 딴다.
    name = None
    cd = r.headers.get("Content-Disposition", "")
    m = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)", cd)
    if m:
        name = unquote(m.group(1))
    if not name:
        name = os.path.basename(urlparse(url).path) or "attachment.bin"
    name = re.sub(r'[\\/:*?"<>|]', "_", name).strip() or "attachment.bin"

    path = os.path.join(outdir, name)
    with open(path, "wb") as f:
        for chunk in r.iter_content(65536):
            f.write(chunk)
    return path


def text_from_hwpx(path):
    """자식 요소의 tail 까지 이어 붙인다 (안 그러면 '’26. 3. 31.' 이 '’26.' 로 잘린다)"""
    z = zipfile.ZipFile(path)
    secs = sorted(n for n in z.namelist()
                  if re.match(r"Contents/section\d+\.xml", n))
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


def text_from_pdf(path):
    import fitz
    d = fitz.open(path)
    t = "\n".join(p.get_text() for p in d)
    d.close()
    return t


def extract(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".hwpx":
        return text_from_hwpx(path)
    if ext == ".pdf":
        return text_from_pdf(path)
    if ext == ".hwp":
        raise SystemExit(
            "구형 .hwp 는 이 도구로 못 읽는다. 한글에서 .hwpx 로 저장하거나\n"
            "같은 게시물에 .hwpx/.pdf 첨부가 있는지 확인할 것.")
    raise SystemExit("지원하지 않는 형식: %s (.hwpx / .pdf 만)" % ext)


def main():
    ap = argparse.ArgumentParser(description="게시판 첨부파일 내려받아 본문 추출")
    ap.add_argument("url")
    ap.add_argument("--out", default="첨부", help="저장 폴더")
    ap.add_argument("--text", action="store_true", help="본문을 .txt 로도 저장")
    a = ap.parse_args()

    path = download(a.url, a.out)
    print("내려받음: %s (%.0f KB)" % (path, os.path.getsize(path) / 1024))

    body = extract(path)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    print("본문 %d자" % len(body))

    if a.text:
        tp = os.path.splitext(path)[0] + ".txt"
        with open(tp, "w", encoding="utf-8") as f:
            f.write(body)
        print("본문 저장:", tp)
    else:
        print("-" * 60)
        print(body[:3000])
        if len(body) > 3000:
            print("... (%d자 더 있음. 전체는 --text 로 저장)" % (len(body) - 3000))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
