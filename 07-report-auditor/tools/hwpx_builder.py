# -*- coding: utf-8 -*-
"""원본 보고서 서식을 그대로 쓰는 .hwpx 생성기.

왜 이렇게 만드나
----------------
마크다운/HTML 을 거쳐 한글로 변환하면 **서식이 통째로 날아간다.**
한글은 HTML 의 `margin-left` 를 무시하고 문단 앞 공백(`&nbsp;`·전각공백)까지 지운다.
글꼴·크기도 원본과 맞출 수 없어, 본문이 15pt 인 서식을 10.5pt 로 뽑아 놓고
「골격은 따랐다」고 말하게 된다.

그래서 **원본 .hwpx 의 스타일 정의(`Contents/header.xml`)를 통째로 가져다 쓰고,
본문(`Contents/section0.xml`)만 새로 쓴다.**

**구조가 복잡한 부분(제목 상자·취지 상자)은 재현하려 들지 말고
원본 표를 통째로 복사해 글자만 바꾼다.** 다시 짜면 또 틀린다.

원본에서 읽어 온 것
-------------------
    제목 상자      원본 표1 복사 — 회색 #F1F1F1, 위아래 굵은 선
    취지 상자      원본 표2 복사 — 테두리 상자
    쪽번호         <hp:pageNum pos="BOTTOM_CENTER" sideChar="-">  (첫 문단 두 번째 run)
    날짜·부서      맑은 고딕 13pt  오른쪽            para 26 / char 20
    □ 대제목       HY헤드라인M 16pt                   para 29 / char 2
    ○ 중제목       휴먼명조 15pt   내어쓰기 -3004     para 32 / char 22
    - 내용         휴먼명조 15pt   내어쓰기 -3004     para 35 / char 22
    * 각주         한양중고딕 13pt 내어쓰기 -3338     para 34 / char 23
    ※ 주석         한양중고딕 13pt                    para 36 / char 23
    ▸ 검토의견     맑은 고딕 13pt  내어쓰기 -1260     para 46 / char 20

표 테두리는 **행 위치마다 다르다.** 두 종류만 쓰면 행마다 이중선이 그려진다.

    머리행        23 · 24 · 25   윗선 굵게 · 아랫선 이중가는선 · 면 #DFE6F7
    머리 아래 행  19 · 14 · 20   윗선 이중가는선
    중간 행       26 ·  2 · 27   위아래 얇은 실선
    마지막 행     21 · 15 · 22   **아랫선 굵게**

들여쓰기는 **내어쓰기 + 텍스트 앞 공백**으로 구현돼 있다.
hwpx 에 직접 쓰면 그 공백이 살아남는다 — HTML 을 거칠 때만 지워졌다.
"""

import io
import os
import re
import sys
import zipfile

try:
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
except AttributeError:
    pass


STYLE = {
    "meta":  (26, 20),
    "h1":    (29, 2),     # □
    "h2":    (32, 22),    # ○
    "item":  (35, 22),    # -
    "star":  (34, 23),    # *
    "note":  (36, 23),    # ※
    "op":    (46, 20),    # ▸
    "blank": (29, 2),
}

TBL_WIDTH = 45907
# 행 위치별 테두리 — 좌 · 중 · 우
BF_HEAD = (23, 24, 25)     # 머리행
BF_UNDER = (19, 14, 20)    # 머리 바로 아래
BF_MID = (26, 2, 27)       # 중간
BF_LAST = (21, 15, 22)     # 마지막 (아랫선 굵게)
# 셀 문단모양 — **한 행 안에서 줄간격을 통일해야 한다.**
# 왼쪽 정렬에 본문용 para 29(줄간격 160)를 쓰면 같은 행의 가운데 셀(130)과 어긋나
# 글자가 아래로 밀린 것처럼 보인다. 원본은 셀에 130·145 만 쓴다.
PARA_HEAD = 38      # 머리행 — 가운데, 줄간격 130
PARA_CELL_C = 40    # 본문 가운데 — 줄간격 145
PARA_CELL_L = 41    # 본문 왼쪽   — 줄간격 145
CHAR_CELL = 20


def esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class Builder(object):
    def __init__(self, template_hwpx):
        self.tpl = template_hwpx
        z = zipfile.ZipFile(template_hwpx)
        self.src = z.read("Contents/section0.xml").decode("utf-8")
        z.close()
        self._pid = 1000
        self.body = []

        m = re.search(r"<hp:secPr\b.*?</hp:secPr>", self.src, re.S)
        if not m:
            raise SystemExit("원본에서 secPr 을 못 찾았다")
        self.secpr = m.group(0)
        # colPr 은 자기 닫는 태그다 (`<hp:colPr ... />`). 닫는 태그를 찾으면 못 잡는다
        m2 = re.search(r"<hp:ctrl>\s*<hp:colPr\b[^>]*/>\s*</hp:ctrl>", self.src, re.S)
        self.colpr = m2.group(0) if m2 else ""
        m3 = re.search(r"<hp:ctrl>\s*<hp:pageNum\b[^>]*/>\s*</hp:ctrl>", self.src, re.S)
        self.pagenum = m3.group(0) if m3 else ""

        # 원본 표 조각 — 제목 상자(0) · 취지 상자(1)
        self.tbls = []
        for mm in re.finditer(r"<hp:tbl\b", self.src):
            i = mm.start()
            j = self.src.find("</hp:tbl>", i) + len("</hp:tbl>")
            self.tbls.append(self.src[i:j])

    def nid(self):
        self._pid += 1
        return self._pid

    # 글자 태그는 `<hp:t>` 뿐이다. `[^>]*` 로 받으면 **`<hp:tc>`·`<hp:tr>`·`<hp:tbl>`
    # 까지 매치되어** 셀 여는 태그부터 통째로 삼킨다 — 표 구조가 날아가고
    # 한글이 파일을 열지 못한다. 태그 이름 뒤가 공백이거나 `>` 인 것만 받는다.
    RE_TEXT = re.compile(r"<hp:t(?:\s[^>]*)?>.*?</hp:t>", re.S)

    # ── 원본 표를 복사해 글자만 바꾼다 ───────────────────────
    def _copy_tbl(self, idx, text):
        t = self.tbls[idx]
        cnt = [0]

        def rep(m):
            cnt[0] += 1
            return "<hp:t>%s</hp:t>" % esc(text) if cnt[0] == 1 else "<hp:t></hp:t>"

        return self.RE_TEXT.sub(rep, t)

    def title_box(self, text):
        """제목 — 원본 표1(회색 상자)을 그대로 쓴다. 첫 문단이라 용지·쪽번호도 여기 담긴다."""
        run1 = '<hp:run charPrIDRef="12">%s%s</hp:run>' % (self.secpr, self.colpr)
        run2 = '<hp:run charPrIDRef="12">%s%s</hp:run>' % (
            self.pagenum, self._copy_tbl(0, text))
        self.body.append(
            '<hp:p id="%d" paraPrIDRef="27" styleIDRef="0" pageBreak="0" '
            'columnBreak="0" merged="0">%s%s</hp:p>' % (self.nid(), run1, run2))
        return self

    def intro_box(self, text):
        """보고 취지 — 원본 표2(테두리 상자)를 그대로 쓴다."""
        self.body.append(
            '<hp:p id="%d" paraPrIDRef="29" styleIDRef="0" pageBreak="0" '
            'columnBreak="0" merged="0"><hp:run charPrIDRef="%d">%s</hp:run></hp:p>'
            % (self.nid(), CHAR_CELL, self._copy_tbl(1, text)))
        return self

    # ── 문단 ────────────────────────────────────────────────
    def p(self, kind, text=""):
        para, char = STYLE[kind]
        run = '<hp:run charPrIDRef="%d">%s</hp:run>' % (
            char, ("<hp:t>%s</hp:t>" % esc(text)) if text else "")
        self.body.append(
            '<hp:p id="%d" paraPrIDRef="%d" styleIDRef="0" pageBreak="0" '
            'columnBreak="0" merged="0">%s</hp:p>' % (self.nid(), para, run))
        return self

    def blank(self):
        return self.p("blank", "")

    # ── 표 ──────────────────────────────────────────────────
    def table(self, rows, widths=None, aligns=None):
        """rows[0] 을 머리행으로 본다. 테두리는 행 위치에 따라 네 벌을 쓴다."""
        nrow, ncol = len(rows), len(rows[0])
        if widths is None:
            widths = [1] * ncol
        tot = float(sum(widths))
        ws = [int(TBL_WIDTH * w / tot) for w in widths]
        ws[-1] += TBL_WIDTH - sum(ws)
        if aligns is None:
            aligns = ["c"] + ["l"] * (ncol - 1)

        def bf(r, c):
            if r == 0:
                pal = BF_HEAD
            elif r == nrow - 1:
                pal = BF_LAST
            elif r == 1:
                pal = BF_UNDER
            else:
                pal = BF_MID
            return pal[0] if c == 0 else (pal[2] if c == ncol - 1 else pal[1])

        trs = []
        for r, row in enumerate(rows):
            tcs = []
            for c, cell in enumerate(row):
                al = "c" if r == 0 else aligns[c]
                if r == 0:
                    ppr = PARA_HEAD
                else:
                    ppr = PARA_CELL_C if al == "c" else PARA_CELL_L
                ps = "".join(
                    '<hp:p id="%d" paraPrIDRef="%d" styleIDRef="0" pageBreak="0" '
                    'columnBreak="0" merged="0"><hp:run charPrIDRef="%d">'
                    '<hp:t>%s</hp:t></hp:run></hp:p>'
                    % (self.nid(), ppr, CHAR_CELL, esc(ln))
                    for ln in str(cell).split("\n"))
                tcs.append(
                    '<hp:tc name="" header="%d" hasMargin="1" protect="0" editable="0" '
                    'dirty="0" borderFillIDRef="%d">'
                    '<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" '
                    'vertAlign="CENTER" linkListIDRef="0" linkListNextIDRef="0" '
                    'textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">%s</hp:subList>'
                    '<hp:cellAddr colAddr="%d" rowAddr="%d"/>'
                    '<hp:cellSpan colSpan="1" rowSpan="1"/>'
                    '<hp:cellSz width="%d" height="600"/>'
                    '<hp:cellMargin left="400" right="400" top="141" bottom="141"/></hp:tc>'
                    % (1 if r == 0 else 0, bf(r, c), ps, c, r, ws[c]))
            trs.append("<hp:tr>%s</hp:tr>" % "".join(tcs))

        tbl = (
            '<hp:tbl id="%d" zOrder="0" numberingType="TABLE" textWrap="TOP_AND_BOTTOM" '
            'textFlow="BOTH_SIDES" lock="0" dropcapstyle="None" pageBreak="CELL" '
            'repeatHeader="1" rowCnt="%d" colCnt="%d" cellSpacing="0" borderFillIDRef="2" '
            'noAdjust="0">'
            '<hp:sz width="%d" widthRelTo="ABSOLUTE" height="%d" heightRelTo="ABSOLUTE" protect="0"/>'
            '<hp:pos treatAsChar="1" affectLSpacing="0" flowWithText="1" allowOverlap="0" '
            'holdAnchorAndSO="0" vertRelTo="PARA" horzRelTo="PARA" vertAlign="TOP" '
            'horzAlign="LEFT" vertOffset="0" horzOffset="0"/>'
            '<hp:outMargin left="0" right="0" top="283" bottom="283"/>'
            '<hp:inMargin left="0" right="0" top="56" bottom="56"/>%s</hp:tbl>'
            % (self.nid(), nrow, ncol, TBL_WIDTH, nrow * 600, "".join(trs)))

        self.body.append(
            '<hp:p id="%d" paraPrIDRef="29" styleIDRef="0" pageBreak="0" columnBreak="0" '
            'merged="0"><hp:run charPrIDRef="%d">%s</hp:run></hp:p>'
            % (self.nid(), CHAR_CELL, tbl))
        return self

    # ── 저장 ────────────────────────────────────────────────
    def save(self, out):
        head = self.src[:self.src.index("<hp:p ")]
        sec = head + "".join(self.body) + "</hs:sec>"

        # **깨진 XML 을 저장하지 않는다.** 한 번 저장하면 한글이 「열지 못했다」고만
        # 말하고 어디가 틀렸는지는 알려 주지 않는다. 여기서 막는 쪽이 훨씬 싸다.
        import xml.etree.ElementTree as ET
        try:
            ET.fromstring(sec)
        except ET.ParseError as e:
            raise SystemExit("생성한 XML 이 깨졌다 — 저장하지 않는다: %s" % e)

        if os.path.exists(out):
            os.remove(out)
        zin = zipfile.ZipFile(self.tpl)
        zout = zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED)
        for it in zin.infolist():
            data = zin.read(it.filename)
            if it.filename == "Contents/section0.xml":
                data = sec.encode("utf-8")
            if it.filename == "mimetype":
                zout.writestr(it, data, zipfile.ZIP_STORED)
            else:
                zout.writestr(it, data)
        zin.close()
        zout.close()
        return out
