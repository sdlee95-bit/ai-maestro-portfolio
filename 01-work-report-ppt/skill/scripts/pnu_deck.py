# -*- coding: utf-8 -*-
"""
pnu_deck.py — 부산대학교 「주요업무보고」 PPT 빌더

원본 서식 「2026 업무보고 서식」의 디자인 토큰(색·서체·간격·헤더 도형)을
그대로 재현하면서, 본문은 내용량에 맞춰 레이아웃을 조립할 수 있게 만든 라이브러리.

사용 예:
    from pnu_deck import PnuDeck
    d = PnuDeck()
    d.cover(year="2026", title="주요업무계획 보고", dept="총무과", date="2026. 3. 16. (월)")
    s = d.content(1, "효율적인 인력 운영 기반 구축")
    s.section("주요 성과")
    s.bullet("(실태조사 체계화) 연 2회 정기 조사 실시", lvl=1)
    s.note("‘25.4. 무기계약직 현황 조사(총무과-6441)")
    d.save("out.pptx")

모든 좌표 단위는 인치(float). 내부에서 EMU로 변환한다.
"""
from __future__ import annotations

import copy
import math
import os
import re
import unicodedata

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

# ─────────────────────────────────────────────────────────────────────
# 1. 디자인 토큰
# ─────────────────────────────────────────────────────────────────────

NAVY = RGBColor(0x1C, 0x4F, 0xA1)  # PNU 메인 남색 — 제목·불릿·헤더 탭
SKY = RGBColor(0x2D, 0xA7, 0xE0)  # PNU 하늘색 — 아이브로우·강조 숫자
SKY_L = RGBColor(0x8E, 0xD8, 0xFF)  # 남색 배경 위 강조용 밝은 하늘색
INK = RGBColor(0x26, 0x26, 0x26)  # 본문 먹색 (tx1 lumMod 85%)
GRAY = RGBColor(0x70, 0x70, 0x70)  # 캡션·보조 텍스트
BAND = RGBColor(0xDC, 0xEA, 0xF7)  # ※ 노트 밴드 / 표 짝수행
LINE = RGBColor(0xBF, 0xD0, 0xE8)  # 표 괘선
PALE = RGBColor(0xF4, 0xF7, 0xFC)  # 카드 배경
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

# 임베드 서체 (원본 pptx에 포함되어 있어 미설치 PC에서도 렌더링됨)
F_BLACK = "페이퍼로지 9 Black"  # 대제목·섹션명·숫자
F_BOLD = "페이퍼로지 7 Bold"  # 간지 타이틀·1단계 불릿
F_SEMI = "페이퍼로지 6 SemiBold"  # 레이블·표 머리행
F_MED = "페이퍼로지 5 Medium"  # 2단계 불릿
F_REG = "페이퍼로지 4 Regular"  # 3단계 불릿·※
F_BUL = "공체 Bold"  # 2단계 불릿 문자 '－'

SLIDE_W = 13.333
SLIDE_H = 7.5

# 본문 안전 영역
BODY_L = 0.72  # 좌측 기준선 (□ 마커 위치)
BODY_R = 12.62  # 우측 한계
BODY_T = 1.24  # 헤더 아래 시작점
BODY_B = 7.05  # 하단 한계
BODY_W = BODY_R - BODY_L

# 레벨별 기본 서식 (크기, 서체, 불릿문자, 불릿서체, 들여쓰기(in), 행갈이 보정)
LEVELS = {
    1: dict(size=17.0, font=F_BOLD, bu="•", bufont="Arial", mar=0.33, ind=0.20),
    2: dict(size=14.0, font=F_MED, bu="－", bufont=F_BUL, mar=0.78, ind=0.30),
    3: dict(size=12.0, font=F_REG, bu="※", bufont=F_REG, mar=1.24, ind=0.32),
}

_HEADER_TAB_PATH = (
    '<a:custGeom xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
    "<a:avLst/><a:gdLst/><a:ahLst/><a:cxnLst/>"
    '<a:rect l="l" t="t" r="r" b="b"/><a:pathLst>'
    '<a:path w="581025" h="644664">'
    '<a:moveTo><a:pt x="0" y="0"/></a:moveTo>'
    '<a:lnTo><a:pt x="581025" y="0"/></a:lnTo>'
    '<a:lnTo><a:pt x="581025" y="500198"/></a:lnTo>'
    '<a:cubicBezTo><a:pt x="581025" y="579984"/><a:pt x="516345" y="644664"/>'
    '<a:pt x="436559" y="644664"/></a:cubicBezTo>'
    '<a:lnTo><a:pt x="144466" y="644664"/></a:lnTo>'
    '<a:cubicBezTo><a:pt x="64680" y="644664"/><a:pt x="0" y="579984"/>'
    '<a:pt x="0" y="500198"/></a:cubicBezTo>'
    "<a:close/></a:path></a:pathLst></a:custGeom>"
)


# ─────────────────────────────────────────────────────────────────────
# 2. 저수준 유틸
# ─────────────────────────────────────────────────────────────────────


def _frag(xml: str):
    from pptx.oxml import parse_xml

    return parse_xml(xml)


def _em_width(text: str) -> float:
    """한글/한자/전각 = 1.0em, 그 외 = 0.5em 로 환산한 문자열 폭."""
    w = 0.0
    for ch in text:
        w += 1.0 if unicodedata.east_asian_width(ch) in ("W", "F") else 0.5
    return w


LINE_FACTOR = 1.07  # PowerPoint 실측 행높이 / (글자크기 × 행간비율)


def est_height(text: str, width_in: float, size_pt: float, line_ratio: float = 1.35,
               hang_in: float = 0.0) -> float:
    """텍스트가 차지할 높이(인치) 추정. 자동 레이아웃 판단에 사용."""
    usable = max(width_in - hang_in, 0.6) * 72.0
    per_line = max(usable / size_pt, 1.0)
    lines = 0
    for seg in text.split("\n"):
        lines += max(1, math.ceil(_em_width(seg) / per_line))
    return lines * size_pt * line_ratio * LINE_FACTOR / 72.0


def solid(shape, rgb):
    shape.fill.solid()
    shape.fill.fore_color.rgb = rgb


def noline(shape):
    shape.line.fill.background()


def _clear_text(shape):
    tf = shape.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.paragraphs[0].runs and None
    return tf


def add_text(slide, x, y, w, h, anchor=MSO_ANCHOR.TOP, wrap=True):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = wrap
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    return box


def put_run(p, text, font, size, color, bold=False, spc=None):
    r = p.add_run()
    r.text = text
    # 앞뒤 공백이 PowerPoint에서 사라지지 않도록 보존
    r._r.find(qn("a:t")).set(
        "{http://www.w3.org/XML/1998/namespace}space", "preserve")
    f = r.font
    f.name = font
    f.size = Pt(size)
    f.bold = bold
    f.color.rgb = color
    # 한글 글꼴(ea)까지 동일 서체로 강제
    rPr = r._r.get_or_add_rPr()
    for tag in ("a:ea", "a:cs"):
        el = rPr.find(qn(tag))
        if el is None:
            el = rPr.makeelement(qn(tag), {})
            rPr.append(el)
        el.set("typeface", font)
    if spc is not None:
        rPr.set("spc", str(int(spc * 100)))
    return r


def line_spacing(p, ratio):
    pPr = p._p.get_or_add_pPr()
    ln = pPr.find(qn("a:lnSpc"))
    if ln is None:
        ln = pPr.makeelement(qn("a:lnSpc"), {})
        pPr.insert(0, ln)
    for c in list(ln):
        ln.remove(c)
    pct = ln.makeelement(qn("a:spcPct"), {"val": str(int(ratio * 100000))})
    ln.append(pct)


def set_bullet(p, char, bufont, color, mar_in, ind_in):
    """행잉 인덴트 + 불릿 문자 지정."""
    pPr = p._p.get_or_add_pPr()
    pPr.set("marL", str(int(mar_in * 914400)))
    pPr.set("indent", str(int(-ind_in * 914400)))
    for tag in ("a:buClr", "a:buFont", "a:buChar", "a:buNone", "a:buSzPct"):
        el = pPr.find(qn(tag))
        if el is not None:
            pPr.remove(el)
    if not char:
        pPr.append(pPr.makeelement(qn("a:buNone"), {}))
        return
    clr = pPr.makeelement(qn("a:buClr"), {})
    srgb = clr.makeelement(qn("a:srgbClr"), {"val": str(color)})
    clr.append(srgb)
    pPr.append(clr)
    pPr.append(pPr.makeelement(qn("a:buFont"), {"typeface": bufont}))
    pPr.append(pPr.makeelement(qn("a:buChar"), {"char": char}))


def space_before(p, pts):
    pPr = p._p.get_or_add_pPr()
    el = pPr.find(qn("a:spcBef"))
    if el is None:
        el = pPr.makeelement(qn("a:spcBef"), {})
        pPr.append(el)
    for c in list(el):
        el.remove(c)
    el.append(el.makeelement(qn("a:spcPts"), {"val": str(int(pts * 100))}))


_EMPH = re.compile(r"\*\*(.+?)\*\*")
_LEAD_PAREN = re.compile(r"^\s*(\([^)]{1,40}\))\s*")


def rich_runs(p, text, font, size, color, emph_color=NAVY):
    """
    본문 문장을 런으로 분해한다.
      · 문두 괄호 리드 "(청렴 문화 확산)" → 남색 강조
      · **텍스트**            → 남색 강조
    """
    rest = text
    m = _LEAD_PAREN.match(rest)
    if m:
        put_run(p, m.group(1), font, size, emph_color, bold=True)
        put_run(p, " ", font, size, color)
        rest = rest[m.end():]
    pos = 0
    for mm in _EMPH.finditer(rest):
        if mm.start() > pos:
            put_run(p, rest[pos:mm.start()], font, size, color)
        put_run(p, mm.group(1), font, size, emph_color, bold=True)
        pos = mm.end()
    if pos < len(rest):
        put_run(p, rest[pos:], font, size, color)


def plain_text(text):
    """rich 마크업을 제거한 순수 텍스트 (높이 추정용)."""
    return _EMPH.sub(r"\1", text)


# ─────────────────────────────────────────────────────────────────────
# 3. 배경 / 장식 프리미티브
# ─────────────────────────────────────────────────────────────────────


def set_bg_solid(slide, rgb):
    xml = (
        '<p:bg xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
        f'<p:bgPr><a:solidFill><a:srgbClr val="{rgb}"/></a:solidFill>'
        "<a:effectLst/></p:bgPr></p:bg>"
    )
    cSld = slide._element.find(qn("p:cSld"))
    old = cSld.find(qn("p:bg"))
    if old is not None:
        cSld.remove(old)
    cSld.insert(0, _frag(xml))


def set_bg_navy_gradient(slide):
    """간지·마무리 슬라이드의 45° 남색 그라데이션 (원본 slide3 동일)."""
    xml = (
        '<p:bg xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
        '<p:bgPr><a:gradFill flip="none" rotWithShape="1"><a:gsLst>'
        '<a:gs pos="0"><a:srgbClr val="1C4FA1"/></a:gs>'
        '<a:gs pos="60000"><a:srgbClr val="1C4FA1"><a:alpha val="85000"/></a:srgbClr></a:gs>'
        '<a:gs pos="100000"><a:srgbClr val="1C4FA1"><a:alpha val="70000"/></a:srgbClr></a:gs>'
        '</a:gsLst><a:lin ang="2700000" scaled="1"/><a:tileRect/></a:gradFill>'
        "<a:effectLst/></p:bgPr></p:bg>"
    )
    cSld = slide._element.find(qn("p:cSld"))
    old = cSld.find(qn("p:bg"))
    if old is not None:
        cSld.remove(old)
    cSld.insert(0, _frag(xml))


def add_veil(slide, x, y, w, h, stops):
    """
    사진 위에 얹는 남색 그라데이션 베일.
    stops: [(pos‰, alpha‰), ...]  가로(왼→오) 방향.
    """
    sp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y),
                                Inches(w), Inches(h))
    noline(sp)
    gs = "".join(
        f'<a:gs pos="{p}"><a:srgbClr val="1C4FA1"><a:alpha val="{a}"/></a:srgbClr></a:gs>'
        for p, a in stops
    )
    xml = (
        '<a:gradFill xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'flip="none" rotWithShape="1">'
        f"<a:gsLst>{gs}</a:gsLst>"
        '<a:lin ang="0" scaled="1"/><a:tileRect/></a:gradFill>'
    )
    spPr = sp._element.spPr
    for tag in ("a:solidFill", "a:noFill", "a:gradFill", "a:blipFill"):
        el = spPr.find(qn(tag))
        if el is not None:
            spPr.remove(el)
    spPr.insert(list(spPr).index(spPr.find(qn("a:prstGeom"))) + 1, _frag(xml))
    return sp


def add_pic_alpha(slide, path, x, y, w, h, alpha_pct=100):
    pic = slide.shapes.add_picture(path, Inches(x), Inches(y), Inches(w), Inches(h))
    if alpha_pct < 100:
        blip = pic._element.blipFill.find(qn("a:blip"))
        blip.insert(0, _frag(
            '<a:alphaModFix xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            f'amt="{int(alpha_pct * 1000)}"/>'
        ))
    return pic


def add_line(slide, x1, y1, x2, y2, rgb, width_pt=0.75, dash=None):
    from pptx.util import Emu as _E

    ln = slide.shapes.add_connector(1, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    ln.line.color.rgb = rgb
    ln.line.width = Pt(width_pt)
    if dash:
        lnEl = ln.line._get_or_add_ln()
        lnEl.append(_frag(
            '<a:prstDash xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            f'val="{dash}"/>'
        ))
    return ln


def add_dot(slide, x, y, d, rgb):
    sp = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x), Inches(y), Inches(d), Inches(d))
    solid(sp, rgb)
    noline(sp)
    sp.text_frame.text = ""
    return sp


def add_circle_num(slide, cx, cy, d, text, fill, fg, size=16, font=F_BLACK):
    sp = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(cx - d / 2), Inches(cy - d / 2),
                                Inches(d), Inches(d))
    solid(sp, fill)
    noline(sp)
    tf = sp.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    put_run(p, text, font, size, fg)
    return sp


def add_marker(slide, x, y, size=0.155):
    """□ 섹션 헤딩 앞의 이중 사각형 마커 (원본 재현)."""
    off = size * 0.23
    back = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x + off), Inches(y + off),
                                  Inches(size), Inches(size))
    back.fill.background()
    back.line.color.rgb = NAVY
    back.line.width = Pt(0.75)
    front = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y),
                                   Inches(size), Inches(size))
    solid(front, NAVY)
    front.line.color.rgb = NAVY
    front.line.width = Pt(0.75)
    return front


_A_NS = 'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'


def _cell_borders(cell, rgb="BFD0E8", w=9525):
    """표 셀 4면 괘선. tcPr 자식 순서(lnL·lnR·lnT·lnB가 맨 앞)를 지켜야 한다."""
    tcPr = cell._tc.get_or_add_tcPr()
    for tag in ("a:lnBlToTr", "a:lnTlToBr", "a:lnB", "a:lnT", "a:lnR", "a:lnL"):
        old = tcPr.find(qn(tag))
        if old is not None:
            tcPr.remove(old)
    for i, tag in enumerate(("a:lnL", "a:lnR", "a:lnT", "a:lnB")):
        el = _frag(
            f'<{tag} {_A_NS} w="{w}" cap="flat" cmpd="sng" algn="ctr">'
            f'<a:solidFill><a:srgbClr val="{rgb}"/></a:solidFill>'
            f'<a:prstDash val="solid"/></{tag}>'
        )
        tcPr.insert(i, el)


def add_round(slide, x, y, w, h, fill=None, line=None, radius=0.08, line_w=1.0):
    sp = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y),
                                Inches(w), Inches(h))
    adj = min(0.5, radius / min(w, h)) if min(w, h) else 0.1
    sp.adjustments[0] = adj
    if fill is None:
        sp.fill.background()
    else:
        solid(sp, fill)
    if line is None:
        noline(sp)
    else:
        sp.line.color.rgb = line
        sp.line.width = Pt(line_w)
    sp.text_frame.text = ""
    return sp


# ─────────────────────────────────────────────────────────────────────
# 4. 콘텐츠 슬라이드 (흐름 커서 기반)
# ─────────────────────────────────────────────────────────────────────


class ContentSlide:
    """
    본문 슬라이드. `y` 커서를 위에서 아래로 내리며 블록을 쌓는다.
    좌우 2단으로 쓸 때는 `column(...)` 컨텍스트를 사용한다.
    """

    def __init__(self, deck, slide, no, title):
        self.deck = deck
        self.slide = slide
        self.y = BODY_T
        self.x = BODY_L
        self.w = BODY_W
        self._stack = []
        deck._header(slide, no, title)

    # ── 영역 제어 ────────────────────────────────────────────────
    def push(self, x, w, y=None):
        """작업 영역을 좁힌다 (좌우 분할 등)."""
        self._stack.append((self.x, self.w, self.y))
        self.x, self.w = x, w
        if y is not None:
            self.y = y
        return self

    def pop(self, keep_y=False):
        x, w, y = self._stack.pop()
        self.x, self.w = x, w
        if not keep_y:
            self.y = y
        return self

    def gap(self, inches=0.12):
        self.y += inches
        return self

    def at(self, y):
        self.y = y
        return self

    @property
    def remaining(self):
        return BODY_B - self.y

    # ── 블록 ─────────────────────────────────────────────────────
    def section(self, title, size=24, gap_before=0.0, color=NAVY):
        """□ 대분류 헤딩 + 이중 사각형 마커."""
        self.y += gap_before
        h = size * 1.45 / 72.0
        add_marker(self.slide, self.x, self.y + h * 0.30, size=size / 190.0)
        box = add_text(self.slide, self.x + 0.24, self.y, self.w - 0.24, h,
                       anchor=MSO_ANCHOR.MIDDLE)
        p = box.text_frame.paragraphs[0]
        line_spacing(p, 1.0)
        put_run(p, title, F_BLACK, size, color, spc=-0.5)
        self.y += h + 0.07
        return self

    def eyebrow(self, text, size=11.5, color=SKY):
        h = size * 1.5 / 72.0
        box = add_text(self.slide, self.x, self.y, self.w, h)
        p = box.text_frame.paragraphs[0]
        line_spacing(p, 1.0)
        put_run(p, text, F_SEMI, size, color, spc=0.4)
        self.y += h
        return self

    def bullets(self, items, base_x=None, width=None, spacing=1.35, gap=0.05,
                sizes=None):
        """
        items: [(level, text), ...]  또는 "•/-/※" 접두 문자열 리스트
        level 1/2/3 = ◦ / － / ※
        """
        x = self.x + 0.30 if base_x is None else base_x
        w = (self.w - 0.30) if width is None else width
        norm = []
        for it in items:
            if isinstance(it, (tuple, list)):
                norm.append((int(it[0]), str(it[1])))
            else:
                s = str(it)
                lv = 3 if s.startswith("※") else 2 if s.startswith(("-", "－")) else 1
                norm.append((lv, s.lstrip("-－※ ").strip() if lv != 1 else s))
        # 높이 계산
        total = 0.0
        for lv, t in norm:
            L = LEVELS[lv]
            sz = (sizes or {}).get(lv, L["size"])
            total += est_height(plain_text(t), w - L["mar"], sz, spacing,
                                hang_in=0.0) + gap
        box = add_text(self.slide, x, self.y, w, total + 0.1)
        tf = box.text_frame
        first = True
        for lv, t in norm:
            L = LEVELS[lv]
            sz = (sizes or {}).get(lv, L["size"])
            p = tf.paragraphs[0] if first else tf.add_paragraph()
            first = False
            line_spacing(p, spacing)
            space_before(p, 0 if lv == 1 else 2)
            set_bullet(p, L["bu"], L["bufont"], NAVY, L["mar"], L["ind"])
            rich_runs(p, t, L["font"], sz, INK)
        self.y += total + 0.06
        return self

    def note(self, text, size=12.0, indent=0.30, pad=0.09):
        """※ 근거·수치 노트를 옅은 하늘색 밴드로 강조 (원본 slide7 스타일)."""
        x = self.x + indent
        w = self.w - indent
        th = est_height("※ " + plain_text(text), w - 2 * pad, size, 1.30)
        h = th + pad * 2
        bg = self.slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(self.y),
                                         Inches(w), Inches(h))
        solid(bg, BAND)
        noline(bg)
        box = add_text(self.slide, x + pad, self.y + pad, w - 2 * pad, th)
        p = box.text_frame.paragraphs[0]
        line_spacing(p, 1.30)
        put_run(p, "※ ", F_REG, size, NAVY, bold=True)
        rich_runs(p, text, F_REG, size, INK)
        self.y += h + 0.08
        return self

    def para(self, text, size=13.5, font=F_MED, color=INK, spacing=1.35, align=None):
        h = est_height(plain_text(text), self.w, size, spacing)
        box = add_text(self.slide, self.x, self.y, self.w, h)
        p = box.text_frame.paragraphs[0]
        line_spacing(p, spacing)
        if align:
            p.alignment = align
        rich_runs(p, text, font, size, color)
        self.y += h + 0.06
        return self

    # ── 표 ───────────────────────────────────────────────────────
    def table(self, headers, rows, widths=None, height=None, size=11.5,
              head_size=11.5, align=None, first_col_left=True, row_h=0.30):
        """
        headers: [str, ...]        (None 이면 머리행 없음)
        rows:    [[str, ...], ...]
        widths:  열 비율 리스트 (합 1.0 기준) 또는 인치 리스트
        align:   열별 PP_ALIGN 리스트
        """
        ncol = len(headers) if headers else len(rows[0])
        nrow = len(rows) + (1 if headers else 0)
        h = height or (row_h * nrow)
        gf = self.slide.shapes.add_table(nrow, ncol, Inches(self.x), Inches(self.y),
                                         Inches(self.w), Inches(h))
        tbl = gf.table
        # 기본 표 스타일(줄무늬) 제거
        tblPr = tbl._tbl.find(qn("a:tblPr"))
        tblPr.set("firstRow", "0")
        tblPr.set("bandRow", "0")

        if widths:
            tot = sum(widths)
            unit = self.w if tot <= 1.001 else 1.0
            for i, ww in enumerate(widths):
                tbl.columns[i].width = Inches(ww / tot * self.w if tot <= 1.001 else ww)

        def style_cell(cell, text, bold, fg, bg, sz, font, al):
            cell.fill.solid()
            cell.fill.fore_color.rgb = bg
            cell.margin_left = cell.margin_right = Inches(0.08)
            cell.margin_top = cell.margin_bottom = Inches(0.04)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            tf = cell.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            p.alignment = al
            line_spacing(p, 1.20)
            rich_runs(p, text, font, sz, fg, emph_color=fg)
            if bold:
                for r in p.runs:
                    r.font.bold = True
            _cell_borders(cell)

        r0 = 0
        if headers:
            for c, htxt in enumerate(headers):
                style_cell(tbl.cell(0, c), htxt, True, WHITE, NAVY, head_size, F_SEMI,
                           PP_ALIGN.CENTER)
            tbl.rows[0].height = Inches(row_h)
            r0 = 1
        for ri, row in enumerate(rows):
            bg = WHITE if ri % 2 == 0 else PALE
            for c, txt in enumerate(row):
                al = (align[c] if align else
                      (PP_ALIGN.LEFT if (c == 0 and first_col_left) or c > 0 and not align
                       else PP_ALIGN.CENTER))
                if align is None:
                    al = PP_ALIGN.CENTER if c == 0 and not first_col_left else (
                        PP_ALIGN.LEFT if c == ncol - 1 else PP_ALIGN.CENTER)
                style_cell(tbl.cell(ri + r0, c), str(txt), False, INK, bg, size, F_REG, al)
            tbl.rows[ri + r0].height = Inches(row_h)
        self.y += h + 0.10
        return self

    # ── 인포그래픽 ────────────────────────────────────────────────
    def kpi(self, cards, h=0.92, gapx=0.14, value_size=25, label_size=10.5,
            unit_size=12.5):
        """
        수치 카드 행.  cards: [(값, 단위, 라벨), ...]
        """
        n = len(cards)
        w = (self.w - gapx * (n - 1)) / n
        for i, (val, unit, label) in enumerate(cards):
            x = self.x + i * (w + gapx)
            add_round(self.slide, x, self.y, w, h, fill=PALE, line=LINE, radius=0.07,
                      line_w=0.75)
            add_round(self.slide, x, self.y, 0.055, h, fill=NAVY, radius=0.02)
            vb = add_text(self.slide, x + 0.20, self.y + 0.11, w - 0.30,
                          value_size * 1.3 / 72.0)
            p = vb.text_frame.paragraphs[0]
            line_spacing(p, 1.0)
            put_run(p, str(val), F_BLACK, value_size, NAVY, spc=-0.6)
            if unit:
                put_run(p, " " + unit, F_SEMI, unit_size, SKY)
            lh = est_height(label, w - 0.34, label_size, 1.20)
            lb = add_text(self.slide, x + 0.20, self.y + h - 0.13 - lh, w - 0.30, lh)
            lp = lb.text_frame.paragraphs[0]
            line_spacing(lp, 1.20)
            put_run(lp, label, F_MED, label_size, GRAY)
        self.y += h + 0.12
        return self

    def steps(self, items, h=0.86, gapx=0.10, title_size=13, desc_size=10.5):
        """
        단계 다이어그램(쉐브론).
        items: [(제목, 설명), ...] 또는 [(라벨, 제목, 설명), ...]
        쉐브론 안쪽 폭에 맞춰 글자 크기를 자동으로 줄인다.
        """
        n = len(items)
        w = (self.w - gapx * (n - 1)) / n
        inner = w - 1.05          # 화살표 노치를 제외한 실제 글자 영역
        norm = []
        for it in items:
            norm.append((it[0], it[1], it[2]) if len(it) > 2 else (None, it[0], it[1]))
        while title_size > 9 and max(
                _em_width(t) for _, t, _ in norm) * title_size / 72.0 > inner:
            title_size -= 0.5
        for i, (lab, ttl, desc) in enumerate(norm):
            x = self.x + i * (w + gapx)
            shape = MSO_SHAPE.PENTAGON if i == 0 else MSO_SHAPE.CHEVRON
            sp = self.slide.shapes.add_shape(shape, Inches(x), Inches(self.y),
                                             Inches(w), Inches(h))
            # 진행에 따라 남색 → 하늘색
            t = i / max(n - 1, 1)
            rgb = RGBColor(
                int(0x1C + (0x2D - 0x1C) * t),
                int(0x4F + (0xA7 - 0x4F) * t),
                int(0xA1 + (0xE0 - 0xA1) * t),
            )
            solid(sp, rgb)
            noline(sp)
            tf = sp.text_frame
            tf.word_wrap = True
            tf.margin_left = Inches(0.12)
            tf.margin_right = Inches(0.12)
            tf.margin_top = tf.margin_bottom = 0
            tf.vertical_anchor = MSO_ANCHOR.MIDDLE
            first = True
            if lab:
                p0 = tf.paragraphs[0]
                p0.alignment = PP_ALIGN.CENTER
                line_spacing(p0, 1.05)
                put_run(p0, lab, F_SEMI, desc_size, RGBColor(0xCF, 0xE7, 0xFA), spc=0.5)
                first = False
            p = tf.paragraphs[0] if first else tf.add_paragraph()
            p.alignment = PP_ALIGN.CENTER
            line_spacing(p, 1.15)
            if not first:
                space_before(p, 2)
            put_run(p, ttl, F_BOLD, title_size, WHITE)
            if desc:
                p2 = tf.add_paragraph()
                p2.alignment = PP_ALIGN.CENTER
                line_spacing(p2, 1.18)
                space_before(p2, 3)
                put_run(p2, desc, F_REG, desc_size, WHITE)
        self.y += h + 0.14
        return self

    def compare(self, left, right, h=1.55, arrow_w=0.52, size=11.5):
        """
        Before ➡ After 비교 패널.
        left/right = dict(tag=..., value=..., items=[...])
        """
        pw = (self.w - arrow_w - 0.24) / 2
        for i, (side, accent) in enumerate(((left, GRAY), (right, NAVY))):
            x = self.x + i * (pw + arrow_w + 0.24)
            fill = PALE if i == 0 else BAND
            add_round(self.slide, x, self.y, pw, h, fill=fill, line=LINE, radius=0.08,
                      line_w=0.75)
            tb = add_text(self.slide, x + 0.18, self.y + 0.13, pw - 0.36, 0.30)
            p = tb.text_frame.paragraphs[0]
            line_spacing(p, 1.0)
            put_run(p, side["tag"], F_SEMI, 11, accent, spc=0.3)
            if side.get("value"):
                vb = add_text(self.slide, x + 0.18, self.y + 0.36, pw - 0.36, 0.40)
                vp = vb.text_frame.paragraphs[0]
                line_spacing(vp, 1.0)
                put_run(vp, side["value"], F_BLACK, 22, NAVY if i else GRAY, spc=-0.5)
            ib = add_text(self.slide, x + 0.18, self.y + 0.80, pw - 0.36, h - 0.92)
            tf = ib.text_frame
            for j, it in enumerate(side.get("items", [])):
                p = tf.paragraphs[0] if j == 0 else tf.add_paragraph()
                line_spacing(p, 1.28)
                space_before(p, 2)
                set_bullet(p, "•", "Arial", NAVY if i else GRAY, 0.16, 0.16)
                rich_runs(p, it, F_REG, size, INK)
        ax = self.x + pw + 0.12
        ar = self.slide.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, Inches(ax),
                                         Inches(self.y + h / 2 - 0.16),
                                         Inches(arrow_w), Inches(0.32))
        solid(ar, SKY)
        noline(ar)
        self.y += h + 0.12
        return self

    def panel(self, x, y, w, h, title=None, body=None, fill=NAVY, fg=WHITE,
              title_size=17, body_size=12.5, items=None, pad=0.26):
        """좌/우 분할용 색 패널 (개요 설명 영역)."""
        add_round(self.slide, x, y, w, h, fill=fill, radius=0.10)
        cy = y + pad
        if title:
            th = est_height(title, w - 2 * pad, title_size, 1.25)
            tb = add_text(self.slide, x + pad, cy, w - 2 * pad, th)
            p = tb.text_frame.paragraphs[0]
            line_spacing(p, 1.25)
            put_run(p, title, F_BLACK, title_size, fg, spc=-0.3)
            cy += th + 0.10
            add_line(self.slide, x + pad, cy, x + pad + 0.62, cy,
                     SKY if fill == NAVY else NAVY, 2.0)
            cy += 0.14
        if body:
            bh = est_height(plain_text(body), w - 2 * pad, body_size, 1.45)
            bb = add_text(self.slide, x + pad, cy, w - 2 * pad, bh)
            p = bb.text_frame.paragraphs[0]
            line_spacing(p, 1.45)
            rich_runs(p, body, F_REG, body_size, fg,
                      emph_color=SKY_L if fill == NAVY else NAVY)
            cy += bh + 0.10
        if items:
            ib = add_text(self.slide, x + pad, cy, w - 2 * pad, h - (cy - y) - pad)
            tf = ib.text_frame
            for j, it in enumerate(items):
                p = tf.paragraphs[0] if j == 0 else tf.add_paragraph()
                line_spacing(p, 1.35)
                space_before(p, 4)
                set_bullet(p, "•", "Arial", SKY_L if fill == NAVY else NAVY, 0.17, 0.17)
                rich_runs(p, it, F_REG, body_size, fg,
                          emph_color=SKY_L if fill == NAVY else NAVY)
        return self

    def cards(self, items, cols=2, h=None, gapx=0.16, gapy=0.14, title_size=13.5,
              body_size=11.5, pad=0.18):
        """
        항목 카드 격자.  items: [(제목, 본문|[불릿...]), ...]
        """
        n = len(items)
        rows = math.ceil(n / cols)
        w = (self.w - gapx * (cols - 1)) / cols
        if h is None:  # 남은 세로 공간을 균등 분배 (하단 여백 0.12 확보)
            h = max(0.72, (BODY_B - self.y - gapy * (rows - 1) - 0.12) / rows)
        for i, (ttl, body) in enumerate(items):
            r, c = divmod(i, cols)
            x = self.x + c * (w + gapx)
            y = self.y + r * (h + gapy)
            add_round(self.slide, x, y, w, h, fill=WHITE, line=LINE, radius=0.07,
                      line_w=0.75)
            add_round(self.slide, x, y, 0.05, h, fill=NAVY, radius=0.02)
            tb = add_text(self.slide, x + pad, y + pad * 0.72, w - pad * 1.6, 0.26)
            p = tb.text_frame.paragraphs[0]
            line_spacing(p, 1.05)
            put_run(p, ttl, F_BOLD, title_size, NAVY, spc=-0.3)
            bb = add_text(self.slide, x + pad, y + pad * 0.72 + 0.28, w - pad * 1.6,
                          h - pad * 1.4 - 0.28)
            tf = bb.text_frame
            blist = body if isinstance(body, (list, tuple)) else [body]
            for j, it in enumerate(blist):
                p = tf.paragraphs[0] if j == 0 else tf.add_paragraph()
                line_spacing(p, 1.30)
                space_before(p, 2)
                if len(blist) > 1:
                    set_bullet(p, "•", "Arial", SKY, 0.15, 0.15)
                else:
                    set_bullet(p, "", "Arial", SKY, 0, 0)
                rich_runs(p, it, F_REG, body_size, INK)
        self.y += rows * h + (rows - 1) * gapy + 0.12
        return self

    def check(self, tag=""):
        """본문이 하단 안전선을 넘었는지 점검 (넘치면 경고 출력)."""
        if self.y > BODY_B + 0.02:
            print(f"  ⚠ 본문 넘침 {self.y:.2f}in > {BODY_B}in  {tag}")
        return self

    def footnote(self, text, size=10.5):
        h = est_height(plain_text(text), self.w, size, 1.25)
        y = min(self.y, BODY_B - h)
        box = add_text(self.slide, self.x, y, self.w, h)
        p = box.text_frame.paragraphs[0]
        line_spacing(p, 1.25)
        rich_runs(p, text, F_REG, size, GRAY, emph_color=NAVY)
        self.y = y + h + 0.05
        return self


# ─────────────────────────────────────────────────────────────────────
# 5. 덱
# ─────────────────────────────────────────────────────────────────────

_HERE = os.path.dirname(os.path.abspath(__file__))
_ASSETS = os.path.normpath(os.path.join(_HERE, "..", "assets"))


class PnuDeck:
    def __init__(self, base=None, assets=None):
        self.assets = assets or _ASSETS
        self.prs = Presentation(base or os.path.join(self.assets, "base.pptx"))
        self._blank = self.prs.slide_masters[0].slide_layouts[6]  # 빈 화면

    # ── 내부 ─────────────────────────────────────────────────────
    def _new(self):
        s = self.prs.slides.add_slide(self._blank)
        for shp in list(s.shapes):
            shp._element.getparent().remove(shp._element)
        return s

    def _asset(self, name):
        return os.path.join(self.assets, name)

    def _tab(self, slide, x, filled):
        sp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(-0.0),
                                    Emu(541881), Emu(707886))
        spPr = sp._element.spPr
        geom = spPr.find(qn("a:prstGeom"))
        spPr.remove(geom)
        spPr.insert(1, _frag(_HEADER_TAB_PATH))
        if filled:
            solid(sp, NAVY)
        else:
            sp.fill.background()
        sp.line.color.rgb = NAVY
        sp.line.width = Pt(0.75)
        sp.text_frame.text = ""
        return sp

    def _logo_lockup(self, slide):
        """헤더 우측 : 부산대 엠블럼 + 국·영문 표기 (80주년 로고 대체)."""
        add_line(slide, 10.62, 0.20, 10.62, 0.80, LINE, 1.0)
        box = add_text(slide, 10.76, 0.20, 1.62, 0.60)
        tf = box.text_frame
        p = tf.paragraphs[0]
        line_spacing(p, 1.0)
        put_run(p, "부산대학교", F_BLACK, 13, NAVY, spc=-0.3)
        p2 = tf.add_paragraph()
        line_spacing(p2, 1.0)
        space_before(p2, 2)
        put_run(p2, "PUSAN NATIONAL", F_SEMI, 7.5, SKY, spc=0.3)
        p3 = tf.add_paragraph()
        line_spacing(p3, 1.0)
        put_run(p3, "UNIVERSITY", F_SEMI, 7.5, SKY, spc=0.3)
        slide.shapes.add_picture(self._asset("pnu_emblem.png"), Inches(12.44),
                                 Inches(0.17), Inches(0.68), Inches(0.68))

    def _header(self, slide, no, title, title_size=22):
        set_bg_solid(slide, "FFFFFF")
        self._tab(slide, 407364 / 914400, filled=False)
        self._tab(slide, 323685 / 914400, filled=True)
        nb = add_text(slide, 323685 / 914400, 0.17, 541881 / 914400, 0.40,
                      anchor=MSO_ANCHOR.MIDDLE)
        p = nb.text_frame.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        line_spacing(p, 1.0)
        put_run(p, str(no), F_BLACK, 15, WHITE)
        tw = 9.16
        size = title_size
        while size > 14 and _em_width(title) * size / 72.0 > tw:
            size -= 0.5
        tb = add_text(slide, 1.24, 0.10, tw, 0.58, anchor=MSO_ANCHOR.MIDDLE, wrap=False)
        tp = tb.text_frame.paragraphs[0]
        line_spacing(tp, 1.05)
        put_run(tp, title, F_BLACK, size, NAVY, spc=-0.6)
        self._logo_lockup(slide)

    # ── 공개 레이아웃 ─────────────────────────────────────────────
    def cover(self, year, title, dept, date, subtitle=None,
              label_dept="발표 부서", label_date="보고 일자"):
        """L1 표지."""
        s = self._new()
        set_bg_solid(s, "1C4FA1")
        px, pw = 7.32, 6.03
        pic = s.shapes.add_picture(self._asset("campus.png"), Inches(px), Inches(0),
                                   Inches(pw), Inches(SLIDE_H))
        pic.crop_left, pic.crop_right, pic.crop_bottom = 0.18595, 0.27766, 0.00002
        add_veil(s, px, 0, pw, SLIDE_H, [(0, 100000), (55000, 80000), (100000, 40000)])
        e = 3.30
        add_pic_alpha(s, self._asset("pnu_emblem_white.png"),
                      px + pw / 2 - e / 2, (SLIDE_H - e) / 2 - 0.24, e, e, alpha_pct=52)
        # 좌측 타이틀 블록
        add_dot(s, 1.05, 2.49, 0.17, SKY)
        yb = add_text(s, 1.26, 2.36, 3.0, 0.60)
        put_run(yb.text_frame.paragraphs[0], year, F_BLACK, 32, SKY, spc=-0.5)
        tb = add_text(s, 1.18, 2.87, 9.0, 1.21)
        tp = tb.text_frame.paragraphs[0]
        line_spacing(tp, 1.05)
        put_run(tp, title, F_BLACK, 60, WHITE, spc=-1.2)
        add_line(s, 1.26, 4.24, 7.97, 4.24, WHITE, 0.75)
        if subtitle:
            sb = add_text(s, 1.26, 4.36, 6.7, 0.34)
            put_run(sb.text_frame.paragraphs[0], subtitle, F_SEMI, 14,
                    RGBColor(0xC9, 0xDD, 0xF2))
        for i, (lab, val) in enumerate(((label_dept, dept), (label_date, date))):
            y = 4.92 + i * 0.42
            lb = add_text(s, 1.26, y + 0.04, 0.95, 0.30)
            put_run(lb.text_frame.paragraphs[0], lab, F_SEMI, 12,
                    RGBColor(0x9F, 0xC4, 0xE8), spc=0.3)
            vb = add_text(s, 2.24, y, 4.2, 0.37)
            put_run(vb.text_frame.paragraphs[0], val, F_SEMI, 16, WHITE)
        return s

    def toc(self, items, title="목 차", eng="Table of Contents"):
        """
        L2 목차.  items: [(아이브로우, 제목) 또는 (아이브로우, 제목, 설명), ...]
        2~4개 권장.
        """
        s = self._new()
        set_bg_solid(s, "1C4FA1")
        strip_h = 1.42
        band = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0),
                                  Inches(SLIDE_W), Inches(strip_h))
        solid(band, WHITE)
        noline(band)
        pic = add_pic_alpha(s, self._asset("campus_gray.png"), 0, 0, SLIDE_W, strip_h,
                            alpha_pct=15)
        pic.crop_top, pic.crop_bottom = 0.33915, 0.50083
        add_dot(s, 0.55, 0.36, 0.17, NAVY)
        tb = add_text(s, 0.71, 0.30, 3.84, 0.77, anchor=MSO_ANCHOR.MIDDLE)
        put_run(tb.text_frame.paragraphs[0], title, F_BLACK, 38, NAVY, spc=1.0)
        eb = add_text(s, 2.12, 0.70, 3.0, 0.34)
        put_run(eb.text_frame.paragraphs[0], eng, F_SEMI, 14, SKY, spc=0.3)
        add_line(s, 10.62, 0.22, 10.62, 1.14, RGBColor(0x9F, 0xC4, 0xE8), 1.0)
        nb = add_text(s, 10.76, 0.26, 1.7, 0.60)
        tf = nb.text_frame
        p = tf.paragraphs[0]
        line_spacing(p, 1.0)
        put_run(p, "부산대학교", F_BLACK, 14, NAVY, spc=-0.3)
        p2 = tf.add_paragraph()
        line_spacing(p2, 1.05)
        space_before(p2, 2)
        put_run(p2, "PUSAN NATIONAL\nUNIVERSITY", F_SEMI, 8, SKY, spc=0.3)
        s.shapes.add_picture(self._asset("pnu_emblem.png"), Inches(12.36), Inches(0.30),
                             Inches(0.74), Inches(0.74))

        n = len(items)
        cy = 3.30
        d = 0.58
        span = SLIDE_W - 2 * 1.55
        step = span / max(n - 1, 1) if n > 1 else 0
        x0 = SLIDE_W / 2 - span / 2 if n > 1 else SLIDE_W / 2
        centers = [x0 + i * step for i in range(n)]
        for a, b in zip(centers, centers[1:]):
            add_line(s, a + d / 2 + 0.07, cy, b - d / 2 - 0.07, cy, WHITE, 1.25, "dash")
        cw = (step if n > 1 else 6.0) - 0.34
        for i, it in enumerate(items):
            eyebrow, name = it[0], it[1]
            desc = it[2] if len(it) > 2 else None
            cx = centers[i]
            add_circle_num(s, cx, cy, d, str(i + 1), WHITE, NAVY, size=17)
            eb = add_text(s, cx - cw / 2, cy + 0.48, cw, 0.34)
            ep = eb.text_frame.paragraphs[0]
            ep.alignment = PP_ALIGN.CENTER
            put_run(ep, eyebrow, F_SEMI, 14, SKY, spc=0.4)
            tb2 = add_text(s, cx - cw / 2, cy + 0.84, cw, 1.00)
            tp = tb2.text_frame.paragraphs[0]
            tp.alignment = PP_ALIGN.CENTER
            line_spacing(tp, 1.20)
            put_run(tp, name, F_BOLD, 24, WHITE, spc=-0.5)
            if desc:
                add_line(s, cx - 0.28, cy + 1.98, cx + 0.28, cy + 1.98,
                         RGBColor(0x7F, 0xAE, 0xE0), 1.25)
                db = add_text(s, cx - cw / 2, cy + 2.14, cw, 0.70)
                dp = db.text_frame.paragraphs[0]
                dp.alignment = PP_ALIGN.CENTER
                line_spacing(dp, 1.35)
                put_run(dp, desc, F_REG, 12.5, RGBColor(0xBF, 0xDA, 0xF3))
        return s

    def divider(self, no, title, subtitle=None):
        """L3 간지."""
        s = self._new()
        set_bg_navy_gradient(s)
        add_circle_num(s, SLIDE_W / 2, 3.37, 0.45, str(no), WHITE, NAVY, size=13)
        tb = add_text(s, 1.0, 3.72, SLIDE_W - 2.0, 0.95)
        p = tb.text_frame.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        line_spacing(p, 1.1)
        put_run(p, title, F_BOLD, 44, WHITE, spc=-1.0)
        if subtitle:
            sb = add_text(s, 1.0, 4.70, SLIDE_W - 2.0, 0.40)
            sp = sb.text_frame.paragraphs[0]
            sp.alignment = PP_ALIGN.CENTER
            put_run(sp, subtitle, F_SEMI, 14, RGBColor(0xBF, 0xDA, 0xF3), spc=0.3)
        return s

    def content(self, no, title, title_size=22) -> ContentSlide:
        """L4~L8 본문 슬라이드. 반환된 객체에 블록을 쌓는다."""
        s = self._new()
        cs = ContentSlide.__new__(ContentSlide)
        cs.deck, cs.slide = self, s
        cs.y, cs.x, cs.w, cs._stack = BODY_T, BODY_L, BODY_W, []
        self._header(s, no, title, title_size=title_size)
        return cs

    def closing(self, text="경청해주셔서 감사합니다.", sub=None):
        """L9 마무리."""
        s = self._new()
        set_bg_navy_gradient(s)
        tb = add_text(s, 1.0, 3.15, SLIDE_W - 2.0, 0.95)
        p = tb.text_frame.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        line_spacing(p, 1.1)
        put_run(p, text, F_BOLD, 44, WHITE, spc=-1.0)
        if sub:
            sb = add_text(s, 1.0, 4.16, SLIDE_W - 2.0, 0.40)
            sp = sb.text_frame.paragraphs[0]
            sp.alignment = PP_ALIGN.CENTER
            put_run(sp, sub, F_SEMI, 14, RGBColor(0xBF, 0xDA, 0xF3), spc=0.3)
        e = 0.86
        s.shapes.add_picture(self._asset("pnu_emblem_white.png"),
                             Inches(SLIDE_W / 2 - e / 2), Inches(2.10), Inches(e), Inches(e))
        return s

    # ── 저장 ─────────────────────────────────────────────────────
    def save(self, path, verbose=True):
        self.prs.save(path)
        if verbose:
            n = len(self.prs.slides)
            print(f"[pnu_deck] {n}매 저장 → {path}")
        return path
