# -*- coding: utf-8 -*-
"""마크다운 보고서 → 한글(.hwp) 변환.

경로 — 마크다운 → HTML → 한글 COM 으로 열어 .hwp 로 저장.

한글 COM 의 액션 API 로 문단·표를 하나씩 쌓는 방법도 있으나, 표가 많은
보고서에서는 손이 너무 많이 간다. **한글이 HTML 을 그대로 읽는다**는 점을
이용하는 쪽이 훨씬 안전하다 — 제목 단계·표·굵기가 그대로 넘어온다.

    python md2hwp.py 입력.md [-o 출력.hwp] [--pdf]

주의 — 한글 창이 떠 있으면 COM 이 그 창을 잡아 엉뚱한 문서를 덮어쓸 수 있다.
Visible=False 로 새 인스턴스를 띄우고 끝나면 반드시 Quit 한다.
"""
import argparse
import os
import re
import sys
import time

import markdown

CSS = """
@page { size: A4; margin: 17mm 18mm 17mm 18mm; }
body { font-family: "함초롬바탕", "바탕", serif; font-size: 10.5pt; line-height: 1.45; }
h1 { font-family: "함초롬돋움", "돋움", sans-serif; font-size: 18pt; font-weight: bold;
     margin: 0 0 6mm 0; padding-bottom: 2mm; border-bottom: 2pt solid #1C4FA1; color: #12213F; }
h2 { font-family: "함초롬돋움", "돋움", sans-serif; font-size: 13pt; font-weight: bold;
     margin: 5mm 0 2mm 0; color: #1C4FA1; }
h3 { font-family: "함초롬돋움", "돋움", sans-serif; font-size: 11.5pt; font-weight: bold;
     margin: 3.5mm 0 1.5mm 0; color: #22324E; }
h4 { font-size: 11pt; font-weight: bold; margin: 4mm 0 2mm 0; }
p  { margin: 0 0 2mm 0; text-align: justify; }
ul, ol { margin: 0 0 3mm 0; padding-left: 7mm; }
li { margin-bottom: 1mm; }
table { border-collapse: collapse; width: 100%; margin: 2mm 0 3mm 0; font-size: 9.5pt; }
th { background: #EDF1F7; border: 0.5pt solid #90A0B8; padding: 1mm 1.5mm;
     font-family: "함초롬돋움", "돋움", sans-serif; font-weight: bold; text-align: center; }
td { border: 0.5pt solid #90A0B8; padding: 1mm 1.5mm; vertical-align: top; }
blockquote { margin: 2mm 0; padding: 1.5mm 3mm; border-left: 3pt solid #2DA7E0;
             background: #F5F8FC; }
blockquote p { margin: 0 0 1mm 0; }
code { font-family: "D2Coding", "консоль", monospace; font-size: 9.5pt; background: #F2F2F2; }
pre { background: #F7F7F7; border: 0.5pt solid #CCCCCC; padding: 2mm 3mm;
      font-size: 9.5pt; white-space: pre-wrap; }
hr { border: none; border-top: 0.5pt solid #BBBBBB; margin: 5mm 0; }
strong { font-weight: bold; }
"""


def md_to_html(path):
    src = open(path, encoding="utf-8").read()
    # 한글에서 깨지는 문자를 미리 바꾼다
    src = src.replace("→", "→").replace("←", "←")
    body = markdown.markdown(
        src, extensions=["tables", "sane_lists"],
        output_format="html")
    title = os.path.splitext(os.path.basename(path))[0]
    m = re.search(r"^#\s+(.+)$", src, re.M)
    if m:
        title = m.group(1).strip()
    return ("<!DOCTYPE html>\n<html><head><meta charset=\"utf-8\">"
            "<title>%s</title><style>%s</style></head><body>\n%s\n"
            "</body></html>" % (title, CSS, body))


def kill_orphan_hwp():
    """COM 이 남긴 '창 없는' 한글만 정리한다.

    창이 있는 한글은 사용자가 열어 둔 것이므로 절대 건드리지 않는다
    (CLAUDE.md 의 EXCEL.EXE 함정과 같은 규칙)."""
    import subprocess
    ps = (
        "Get-Process Hwp -ErrorAction SilentlyContinue | "
        "Where-Object { $_.MainWindowHandle -eq 0 } | "
        "ForEach-Object { Stop-Process -Id $_.Id -Force; $_.Id }"
    )
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           capture_output=True, text=True, timeout=30)
        killed = [x for x in r.stdout.split() if x.strip()]
        if killed:
            print("  (창 없는 한글 %d개 정리: %s)" % (len(killed), ", ".join(killed)))
            time.sleep(1.5)
    except Exception as e:
        print("  (한글 정리 건너뜀: %s)" % e)


def html_to_hwp(html_path, hwp_path, make_pdf=False):
    import win32com.client as win32
    kill_orphan_hwp()
    html_path = os.path.abspath(html_path)
    hwp_path = os.path.abspath(hwp_path)
    for p in (hwp_path,):
        if os.path.exists(p):
            os.remove(p)
    hwp = win32.gencache.EnsureDispatch("HWPFrame.HwpObject")
    pdf_path = None
    try:
        try:
            hwp.XHwpWindows.Item(0).Visible = False
        except Exception:
            pass
        # 보안 모듈 경고 없이 파일 접근
        try:
            hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")
        except Exception:
            pass
        if not hwp.Open(html_path, "HTML", "forceopen:true"):
            raise SystemExit("한글이 HTML 을 열지 못했습니다: %s" % html_path)
        hwp.SaveAs(hwp_path, "HWP", "")
        if make_pdf:
            pdf_path = os.path.splitext(hwp_path)[0] + ".pdf"
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
            hwp.SaveAs(pdf_path, "PDF", "")
    finally:
        try:
            hwp.Clear(1)
            hwp.Quit()
        except Exception:
            pass
    return hwp_path, pdf_path


def main(argv=None):
    ap = argparse.ArgumentParser(description="마크다운 → 한글(.hwp)")
    ap.add_argument("src")
    ap.add_argument("-o", "--out")
    ap.add_argument("--pdf", action="store_true", help="PDF 도 함께 만든다(쪽수 확인용)")
    ap.add_argument("--keep-html", action="store_true")
    a = ap.parse_args(argv)

    out = a.out or os.path.splitext(a.src)[0] + ".hwp"
    html = os.path.splitext(out)[0] + "_tmp.html"
    open(html, "w", encoding="utf-8").write(md_to_html(a.src))

    hwp, pdf = html_to_hwp(html, out, a.pdf)
    print("한글: %s (%.0f KB)" % (hwp, os.path.getsize(hwp) / 1024))
    if pdf and os.path.exists(pdf):
        try:
            import fitz
            with fitz.open(pdf) as d:
                print("      %d쪽" % d.page_count)
        except Exception:
            pass
    if not a.keep_html:
        os.remove(html)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
