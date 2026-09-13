# -*- coding: utf-8 -*-
"""
직장교육 안내 포스터 렌더러 (PIL)

설계 원칙 — 기존 포스터에서 문제였던 네 가지를 뒤집는다.
  1. 정보 위계 : '무슨 교육인가' 를 가장 크게. 기존은 4줄이 전부 같은 크기였다.
  2. 읽는 사람 관점 : 제목이 '2026년 9월 직장교육 안내'(행정 용어)가 아니라
     교육 주제 자체. 구성원이 궁금한 건 "무슨 교육이고 내가 가야 하나" 다.
  3. 실질 정보 : 상시학습 인정시간·비대면 이수기준·캠퍼스 특례를 하단 띠에 싣는다.
     기존 포스터에 없어서 문의가 반복됐다.
  4. 주제와 톤 일치 : 배경이 주제와 무관하면 쓰지 않는다.

글꼴은 본고딕(Noto Sans KR, OFL) 을 쓴다. 가변 폰트라 Thin~Black 을 한 파일로 쓴다.
"""
import os
import re
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

FONT_VF = "C:/Windows/Fonts/NotoSansKR-VF.ttf"
FONT_FALLBACK = "C:/Windows/Fonts/malgunbd.ttf"

# 부산대 계열 색 (1회차 PPT 스킬과 동일 계열)
NAVY = (28, 79, 161)
NAVY_DEEP = (12, 31, 66)
SKY = (45, 167, 224)
INK = (17, 24, 39)
WHITE = (255, 255, 255)
WARM = (232, 113, 10)


# ------------------------------------------------------------------ 글꼴
_font_cache = {}


def font(size, weight="Bold"):
    key = (size, weight)
    if key in _font_cache:
        return _font_cache[key]
    try:
        f = ImageFont.truetype(FONT_VF, size)
        f.set_variation_by_name(weight)
    except Exception:
        f = ImageFont.truetype(FONT_FALLBACK, size)
    _font_cache[key] = f
    return f


def measure(draw, text, f):
    b = draw.textbbox((0, 0), text, font=f)
    return b[2] - b[0], b[3] - b[1]


def fit_font(draw, text, max_w, start, weight="Bold", min_size=20):
    """max_w 안에 들어갈 때까지 글자 크기를 줄인다 (한 줄 기준)"""
    s = start
    while s > min_size:
        f = font(s, weight)
        if measure(draw, text, f)[0] <= max_w:
            return f
        s -= 2
    return font(min_size, weight)


def wrap(draw, text, f, max_w):
    """공백 기준 줄바꿈. 한글은 어절 단위로 끊는다."""
    words = text.split()
    lines, cur = [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if measure(draw, t, f)[0] <= max_w or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


# ------------------------------------------------------------------ 그리기 도구
def vgradient(size, top, bottom):
    w, h = size
    g = Image.new("RGB", (1, h))
    d = ImageDraw.Draw(g)
    for y in range(h):
        t = y / max(1, h - 1)
        d.point((0, y), fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return g.resize((w, h))


def dgradient(size, c1, c2):
    """좌상 → 우하 대각 그라디언트"""
    w, h = size
    base = Image.new("RGB", (w, h), c1)
    top = Image.new("RGB", (w, h), c2)
    mask = Image.new("L", (w, h))
    md = ImageDraw.Draw(mask)
    for i in range(0, w + h, 4):
        v = int(255 * i / (w + h))
        md.line([(i, 0), (0, i)], fill=v, width=5)
    return Image.composite(top, base, mask)


def rrect(d, box, r, fill=None, outline=None, width=0):
    d.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)


def shadow_text(d, xy, text, f, fill, shadow=(0, 0, 0, 110), off=3):
    x, y = xy
    d.text((x + off, y + off), text, font=f, fill=shadow)
    d.text((x, y), text, font=f, fill=fill)


# ------------------------------------------------------------------ 내용 구성
def build_content(plan):
    """계획안 데이터 → 포스터에 실을 항목. 없는 값은 만들지 않는다."""
    ilsi = plan.get("일시") or {}
    gs = plan.get("강사") or {}
    주제 = plan.get("교육내용") or ""
    # '폭력예방교육(성매매, 가정폭력)' → 주제 / 부제 분리
    main, sub = 주제, ""
    if "(" in 주제 and 주제.endswith(")"):
        main = 주제[:주제.index("(")].strip()
        sub = 주제[주제.index("(") + 1:-1].strip()
        sub = "·".join(x.strip() for x in sub.replace(",", "·").split("·") if x.strip())

    c = {
        "연": plan.get("연도"), "월": plan.get("월"),
        "주제": main, "부제": sub,
        "날짜": ilsi.get("날짜표기", ""), "시간": ilsi.get("시간표기", ""),
        "장소": plan.get("장소") or "",
        "대상": plan.get("교육대상") or "",
        "강사": gs.get("성명", ""), "강사소속": gs.get("소속", ""),
        "유형": plan.get("유형", ""),
        "종료": ilsi.get("종료표기", ""),
    }

    # 참여 방법은 유형에서 만든다. 문구를 박아 두면 안 된다 —
    # 이러닝 달(5월)에 'ZOOM 실시간 참여' 가 찍히는 사고가 있었다.
    참여 = []
    유형 = plan.get("유형")
    if 유형 in ("집합", "혼합") and c["장소"]:
        참여.append(("대면", c["장소"]))
    if 유형 == "혼합":
        참여.append(("온라인", "ZOOM 실시간 참여"))
    if 유형 == "이러닝":
        참여.append(("수강", plan.get("운영방법") or "이러닝(e-learning) 교육"))
        if plan.get("수강처"):
            참여.append(("접속", plan["수강처"]))
    if not 참여 and plan.get("운영방법"):
        참여.append(("운영", plan["운영방법"]))
    c["참여"] = 참여
    c["이러닝"] = (유형 == "이러닝")

    # 이러닝은 실을 정보가 다르다 — 하루가 아니라 기간, 장소가 아니라 수강처,
    # 참여율이 아니라 진도율, 그리고 강좌가 2개다. E안이 이 항목들을 쓴다.
    if c["이러닝"]:
        c["과목"] = [s.strip() for s in re.split(r"\s*[,、]\s*", 주제) if s.strip()]
        c["강좌"] = plan.get("강좌") or []
        c["수강처"] = plan.get("수강처") or ""
        c["수강처URL"] = plan.get("수강처URL") or ""
        c["진도율"] = plan.get("진도율")
        c["준비"] = plan.get("준비사항") or ""
        c["흐름"] = plan.get("수강흐름") or []
        c["이수확인"] = plan.get("이수확인") or ""
        c["중복이수"] = plan.get("중복이수") or ""
        c["표경고"] = plan.get("표경고")
        # '2026. 5. 12.(화) ~ 2026. 5. 31.(일)' 처럼 연도가 두 번 나오지 않게.
        끝 = c["종료"]
        if 끝 and c["연"] and 끝.startswith("%d." % c["연"]):
            끝 = 끝[len("%d." % c["연"]):].strip()
        c["기간"] = c["날짜"] + (" ~ " + 끝 if 끝 else "")

    notes = []
    # 인정시간을 숫자로만 읽으면 '1시간 40분 인정'(2026-03) 같은 표기를 놓친다.
    # 원문의 '…으로 N 인정' 을 그대로 쓴다.
    base = plan.get("상시학습") or ""
    if base:
        if "으로" in base:
            head, rest = base.split("으로", 1)
            notes.append("상시학습 %s · %s" % (rest.strip(), head.strip()))
        else:
            notes.append("상시학습 %s" % base.strip())
    if plan.get("이수기준"):
        s = plan["이수기준"]
        s = s.replace("전체교육시간", "전체 교육시간 ").replace("이상이수", "이상 이수")
        s = s.split("(")[0].strip()
        notes.append("비대면 %s" % s if not s.startswith("비대면") else s)
    # 이 두 줄은 달마다 내용이 다르다. 문구를 박아 두면 안 된다.
    # (2026-03 은 '전달교육 참여 인정' 인데 9월 기준 'ZOOM 참여 인정' 을 박아
    #  공식 안내문에 틀린 정보가 실렸다. 반드시 추출한 원문을 쓴다.)
    if plan.get("캠퍼스특례"):
        s = re.sub(r"\s+", " ", plan["캠퍼스특례"]).replace("· ", "·").strip()
        notes.append(s)
    if plan.get("참석예외"):
        s = re.sub(r"\s+", " ", plan["참석예외"]).replace("· ", "·").strip()
        # 뒷부분이 캠퍼스특례와 겹치므로 '…하되,' 앞에서 끊는다
        s = re.split(r"\s*하되[,，]", s)[0].strip()
        if not s.endswith("참석"):
            s += " 참석"
        notes.append(s)
    # 이러닝은 캠퍼스 특례·참석 예외가 없는 대신 수강 전 준비와 이수 확인이 있다.
    if c["이러닝"]:
        if c.get("준비"):
            notes.append("수강 전 %s" % c["준비"])
        if c.get("이수확인"):
            # PDF 에서 공백이 다 사라져 붙어 나온다 → 읽을 수 있게 띄운다
            s = c["이수확인"]
            s = re.sub(r"모든과목이수후반드시화면상단의이수여부를확인",
                       "모든 과목 이수 후 화면 상단에서 이수 여부 확인", s)
            notes.append(s)
        if c.get("중복이수"):
            notes.append(c["중복이수"].rstrip("."))
    c["안내"] = notes
    return c


# ------------------------------------------------------------------ 공통 레이아웃
def layout_blocks(d, c, colw, scale=1.0):
    """본문 블록을 (그리기함수, 높이) 목록으로 만든다.
    위에서부터 쌓기만 하면 아래가 비므로, 전체 높이를 먼저 재서 세로로 배분한다."""
    S = lambda v: max(12, int(v * scale))
    blocks = []

    f_lab = font(S(30), "Medium")
    blocks.append(("label", f_lab, measure(d, "가", f_lab)[1] + S(16)))

    f_main = fit_font(d, c["주제"], colw, S(126), "Black")
    blocks.append(("main", f_main, measure(d, c["주제"], f_main)[1] + S(26)))

    if c["부제"]:
        f_sub = fit_font(d, c["부제"], colw, S(60), "Medium")
        blocks.append(("sub", f_sub, measure(d, c["부제"], f_sub)[1] + S(40)))

    # 날짜+시간을 한 줄에 쓰므로 칸 너비에 맞춰 줄인다.
    # 고정 크기로 두면 세로형처럼 칸이 좁을 때 글자가 칸 밖으로 삐져나간다.
    date_line = (c["날짜"] + "  " + c["시간"]).strip()
    f_date = fit_font(d, date_line, colw, S(64), "Bold", 28)
    blocks.append(("date", f_date, measure(d, "2026", f_date)[1] + S(34)))

    blocks.append(("how", font(S(32), "Bold"), S(112) + S(30)))

    if c["강사"]:
        blocks.append(("lect", font(S(29), "Medium"), S(40)))
    return blocks


# ------------------------------------------------------------------ 스타일 A
def style_a(c, size=(1920, 1080), bg_photo=None):
    """차분한 공문 정제형 — 딥네이비. 우측 여백에는 날짜를 큰 워터마크로 앉힌다."""
    W, H = size
    img = dgradient((W, H), NAVY_DEEP, (24, 58, 118)).convert("RGB")
    d = ImageDraw.Draw(img, "RGBA")

    for i in range(-H, W, 150):
        d.line([(i, H), (i + H, 0)], fill=(255, 255, 255, 7), width=34)

    band_h = int(H * 0.135)
    M = int(W * 0.058)
    colw = int(W * 0.50)          # 우측 날짜 카드 자리를 비워 둔다
    tx = M + int(W * 0.026)

    # 우측 날짜 카드.
    # (워터마크로 크게 깔아 봤더니 본문을 덮었다 — PIL 의 text() 는 도형과 달리
    #  fill 의 알파를 무시하고 불투명하게 그린다. 반투명이 필요하면 별도 RGBA
    #  레이어에 그려 alpha_composite 해야 한다. 카드 방식이 더 읽히기도 한다.)
    date_main = c["날짜"].split("(")[0].strip().rstrip(".")
    parts = [x.strip() for x in date_main.split(".")]
    if len(parts) >= 3:
        cx0, cx1 = int(W * 0.615), W - M
        cy0, cy1 = int(H * 0.205), int(H - band_h - H * 0.10)
        rrect(d, [cx0, cy0, cx1, cy1], 22, fill=(255, 255, 255, 30),
              outline=(255, 255, 255, 70), width=2)
        d.rectangle([cx0, cy0, cx1, cy0 + 8], fill=SKY)
        cw, ch = cx1 - cx0, cy1 - cy0
        big = "%s.%s" % (parts[1], parts[2])
        f_big = fit_font(d, big, int(cw * 0.80), int(H * 0.26), "Black", 60)
        wd = c["날짜"][c["날짜"].find("("):] if "(" in c["날짜"] else ""
        f_wd = font(int(H * 0.050), "Bold")
        f_tm = font(int(H * 0.044), "Medium")

        # measure() 는 잉크 박스만 재서 큰 글자의 실제 차지 높이를 과소평가한다.
        # 겹침을 막으려면 글자 크기(= 줄 높이)를 기준으로 쌓는다.
        h_big = int(f_big.size * 1.02)
        h_wd = int(f_wd.size * 1.45) if wd else 0
        h_tm = int(f_tm.size * 1.35)
        stack = h_big + h_wd + h_tm
        y0 = cy0 + (ch - stack) // 2

        def center(text, f, yy, fill):
            w = measure(d, text, f)[0]
            d.text((cx0 + (cw - w) // 2, yy), text, font=f, fill=fill)

        center(big, f_big, y0, WHITE)
        yy = y0 + h_big
        if wd:
            center(wd, f_wd, yy, SKY)
            yy += h_wd
        center(c["시간"], f_tm, yy, (206, 228, 250))

    # 날짜는 우측 카드가 크게 보여 주므로 좌측에서는 뺀다 (같은 값을 두 번 쓰지 않는다)
    blocks = [b for b in layout_blocks(d, c, colw) if b[0] != "date"]
    total = sum(b[2] for b in blocks)
    top = int((H - band_h - total) / 2) + int(H * 0.02)
    d.rectangle([M, top, M + 11, top + total - 20], fill=SKY)

    y = top
    for kind, f, h in blocks:
        if kind == "label":
            d.text((tx, y), "부산대학교 · %d년 %d월 직장교육" % (c["연"], c["월"]),
                   font=f, fill=(152, 192, 236))
        elif kind == "main":
            d.text((tx, y), c["주제"], font=f, fill=WHITE)
        elif kind == "sub":
            d.text((tx, y), c["부제"], font=f, fill=SKY)
        elif kind == "date":
            d.text((tx, y), c["날짜"], font=f, fill=WHITE)
            wd = measure(d, c["날짜"], f)[0]
            ft = font(int(f.size * 0.78), "Medium")
            d.text((tx + wd + 24, y + int(f.size * 0.18)), c["시간"], font=ft,
                   fill=(198, 224, 250))
        elif kind == "how":
            bw, bh, gap = int(colw * 0.47), int(h * 0.72), int(colw * 0.04)
            for i, (k, v) in enumerate(c["참여"]):
                if not v:
                    continue
                bx = tx + i * (bw + gap)
                rrect(d, [bx, y, bx + bw, y + bh], 14, fill=(255, 255, 255, 28),
                      outline=(255, 255, 255, 64), width=2)
                d.text((bx + 24, y + int(bh * 0.17)), k, font=font(26, "Medium"), fill=SKY)
                d.text((bx + 24, y + int(bh * 0.47)),
                       v, font=fit_font(d, v, bw - 48, 34, "Bold", 20), fill=WHITE)
        elif kind == "lect":
            line = "강사  %s" % c["강사"]
            d.text((tx, y), line, font=f, fill=(206, 226, 246))
            if c["강사소속"]:
                wl = measure(d, line, f)[0]
                aff = c["강사소속"]
                fa = font(23, "Regular")
                if measure(d, aff, fa)[0] > colw - wl - 30:
                    aff = aff.split(",")[0].strip()
                d.text((tx + wl + 20, y + 7), aff, font=fa, fill=(150, 178, 210))
        y += h

    _band(d, c, W, H, band_h, bg=(255, 255, 255, 244), dot=NAVY, fg=(38, 50, 70))
    return img


# ------------------------------------------------------------------ 스타일 B
def style_b(c, size=(1920, 1080), bg_photo=None):
    """사진 배경 + 어두운 오버레이. 주제 톤에 맞는 사진일 때만 쓴다."""
    W, H = size
    if bg_photo and os.path.exists(bg_photo):
        ph = Image.open(bg_photo).convert("RGB")
        r = max(W / ph.width, H / ph.height)
        ph = ph.resize((int(ph.width * r) + 1, int(ph.height * r) + 1), Image.LANCZOS)
        img = ph.crop(((ph.width - W) // 2, (ph.height - H) // 2,
                       (ph.width - W) // 2 + W, (ph.height - H) // 2 + H))
        # 대비가 센 사진은 오버레이만으로 안 눌린다. 사진 자체를 어둡게·부드럽게.
        img = img.filter(ImageFilter.GaussianBlur(5))
        img = ImageEnhance.Brightness(img).enhance(0.62)
        img = ImageEnhance.Color(img).enhance(0.72)
    else:
        img = dgradient((W, H), (30, 54, 74), (72, 96, 104)).convert("RGB")

    ov = Image.new("RGBA", (W, H))
    od = ImageDraw.Draw(ov)
    for x in range(W):
        a = int(240 * max(0.0, 1 - (x / (W * 0.86)) ** 1.5))
        od.line([(x, 0), (x, H)], fill=(6, 18, 30, a))
    od.rectangle([0, 0, W, H], fill=(6, 18, 30, 60))
    img = Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")
    d = ImageDraw.Draw(img, "RGBA")

    band_h = int(H * 0.13)
    M = int(W * 0.058)
    colw = int(W * 0.58)
    tx = M

    blocks = layout_blocks(d, c, colw)
    total = sum(b[2] for b in blocks)
    y = int((H - band_h - total) / 2) + int(H * 0.015)

    for kind, f, h in blocks:
        if kind == "label":
            d.text((tx, y), "부산대학교 · %d년 %d월 직장교육" % (c["연"], c["월"]),
                   font=f, fill=(214, 232, 242))
            d.line([(tx, y + f.size + 14), (tx + 86, y + f.size + 14)], fill=WARM, width=6)
        elif kind == "main":
            shadow_text(d, (tx, y), c["주제"], f, WHITE, (0, 0, 0, 150), 3)
        elif kind == "sub":
            shadow_text(d, (tx, y), c["부제"], f, (255, 216, 172), (0, 0, 0, 140), 2)
        elif kind == "date":
            shadow_text(d, (tx, y), "%s  %s" % (c["날짜"], c["시간"]), f, WHITE,
                        (0, 0, 0, 150), 2)
        elif kind == "how":
            parts = ["%s  %s" % (k, v) for k, v in c["참여"]]
            fp = font(31, "Medium")
            for i, s in enumerate(parts):
                d.ellipse([tx, y + 12 + i * 44, tx + 10, y + 22 + i * 44], fill=WARM)
                shadow_text(d, (tx + 22, y + i * 44), s, fp, (232, 242, 248),
                            (0, 0, 0, 120), 2)
        elif kind == "lect":
            t = "강사  %s" % c["강사"]
            if c["강사소속"]:
                t += "   " + c["강사소속"].split(",")[0].strip()
            shadow_text(d, (tx, y), t, font(27, "Regular"), (200, 218, 230),
                        (0, 0, 0, 120), 2)
        y += h

    _band(d, c, W, H, band_h, bg=(8, 20, 32, 238), dot=WARM, fg=(224, 236, 244))
    return img


# ------------------------------------------------------------------ 스타일 C
def style_c(c, size=(1920, 1080), bg_photo=None):
    """강한 타이포 + 색면 분할 — 멀리서도 읽힌다."""
    W, H = size
    img = Image.new("RGB", (W, H), (246, 248, 251))
    d = ImageDraw.Draw(img, "RGBA")
    d.polygon([(W * 0.575, 0), (W, 0), (W, H), (W * 0.435, H)], fill=NAVY)
    d.polygon([(W * 0.568, 0), (W * 0.589, 0), (W * 0.449, H), (W * 0.428, H)], fill=SKY)

    M = int(W * 0.05)
    colw = int(W * 0.42)
    tx = M

    f_lab = font(29, "Bold")
    f_main = fit_font(d, c["주제"], colw, 130, "Black")
    f_sub = fit_font(d, c["부제"], colw, 58, "Bold") if c["부제"] else None
    date_main = c["날짜"].split("(")[0].strip().rstrip(".")
    parts = [x.strip() for x in date_main.split(".")]
    big = "%s.%s" % (parts[1], parts[2]) if len(parts) >= 3 else ""
    f_big = fit_font(d, big, int(colw * 0.62), 168, "Black") if big else None

    h_lab = measure(d, "가", f_lab)[1] + 24
    h_main = measure(d, c["주제"], f_main)[1] + 20
    h_sub = (measure(d, c["부제"], f_sub)[1] + 44) if f_sub else 0
    h_big = (measure(d, big, f_big)[1] + 40) if f_big else 0
    h_how = 118
    total = h_lab + h_main + h_sub + h_big + h_how
    y = int((H - total) / 2)

    d.text((tx, y), "%d년 %d월 직장교육" % (c["연"], c["월"]), font=f_lab, fill=NAVY)
    y += h_lab
    d.text((tx, y), c["주제"], font=f_main, fill=INK)
    y += h_main
    if f_sub:
        d.text((tx, y), c["부제"], font=f_sub, fill=NAVY)
        y += h_sub
    if f_big:
        d.text((tx, y), big, font=f_big, fill=NAVY)
        wb = measure(d, big, f_big)[0]
        wd = c["날짜"][c["날짜"].find("("):] if "(" in c["날짜"] else ""
        d.text((tx + wb + 18, y + int(f_big.size * 0.18)), wd, font=font(52, "Bold"),
               fill=(124, 140, 164))
        d.text((tx + wb + 18, y + int(f_big.size * 0.56)), c["시간"],
               font=font(40, "Medium"), fill=(96, 110, 134))
        y += h_big
    fp = font(30, "Medium")
    for i, (k, v) in enumerate(c["참여"]):
        if not v:
            continue
        d.rectangle([tx, y + 8 + i * 48, tx + 6, y + 34 + i * 48], fill=SKY)
        d.text((tx + 20, y + i * 48), "%s   %s" % (k, v), font=fp, fill=(56, 68, 88))

    # 우측 패널
    rx = int(W * 0.625)
    rw = W - rx - M
    d.text((rx, int(H * 0.17)), "참여 전 확인", font=font(34, "Bold"), fill=(170, 210, 242))
    yy = int(H * 0.17) + 64
    fn = font(28, "Medium")
    for s in c["안내"][:4]:
        for li, line in enumerate(wrap(d, s, fn, rw)):
            if li == 0:
                d.ellipse([rx, yy + 11, rx + 11, yy + 22], fill=SKY)
            d.text((rx + 26, yy), line, font=fn, fill=WHITE)
            yy += 40
        yy += 14

    if c["강사"]:
        by = H - int(H * 0.20)
        d.line([(rx, by - 26), (rx + 70, by - 26)], fill=SKY, width=4)
        d.text((rx, by), "강사", font=font(23, "Medium"), fill=(160, 198, 236))
        d.text((rx, by + 32), c["강사"], font=font(36, "Bold"), fill=WHITE)
        if c["강사소속"]:
            fa = font(22, "Regular")
            for li, line in enumerate(wrap(d, c["강사소속"], fa, rw)[:2]):
                d.text((rx, by + 82 + li * 28), line, font=fa, fill=(182, 206, 230))
    return img


# ------------------------------------------------------------------ 스타일 D
CREAM = (245, 241, 232)


def style_d(c, size=(1920, 1080), bg_photo=None):
    """생성 AI 일러스트 + 코드 조판.

    일러스트는 글자 없이 받아 우측에 앉히고, 글자는 전부 여기서 그린다.
    생성 AI 가 한글을 틀리는 문제를 구조적으로 없애기 위한 방식이다.
    일러스트가 없으면 크림색 배경만으로도 성립하도록 해 둔다."""
    W, H = size
    img = Image.new("RGB", (W, H), CREAM)

    band_h = int(H * 0.135)

    if bg_photo and os.path.exists(bg_photo):
        il = Image.open(bg_photo).convert("RGB")
        # 일러스트는 '띠 위쪽'에만 앉힌다. 화면 전체에 깔면 하단 띠가 인물의
        # 발목을 자른다. 아래를 기준으로 맞춰(bottom-align) 발이 띠에 닿게 한다.
        area_h = H - band_h
        r = max(W / il.width, area_h / il.height)
        il = il.resize((int(il.width * r) + 1, int(il.height * r) + 1), Image.LANCZOS)
        left = (il.width - W) // 2
        il = il.crop((left, il.height - area_h, left + W, il.height))
        img.paste(il, (0, 0))

        # 좌측을 크림색으로 덮어 글자 자리를 만든다.
        # 프롬프트에서 '왼쪽 절반 비우기'를 요구했지만 그대로 오지 않을 수 있으므로,
        # 이 오버레이가 있으면 글자는 항상 읽힌다. 인물이 시작되는 지점(약 51%)
        # 앞에서 투명해지도록 해 그림을 흐리지 않는다.
        x0, x1 = W * 0.30, W * 0.50
        ov = Image.new("RGBA", (W, H))
        od = ImageDraw.Draw(ov)
        for x in range(W):
            t = (x - x0) / (x1 - x0)
            t = min(1.0, max(0.0, t))
            a = int(255 * (1 - (t * t * (3 - 2 * t))))      # smoothstep
            od.line([(x, 0), (x, area_h)], fill=CREAM + (a,))
        img = Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")

    d = ImageDraw.Draw(img, "RGBA")
    M = int(W * 0.058)
    colw = int(W * 0.40)          # 인물과 겹치지 않도록 글자 칸을 좁힌다
    tx = M + int(W * 0.022)

    blocks = layout_blocks(d, c, colw)
    # 강사 소속이 길면 한 줄에 안 들어가 잘린다. 이름 아래 두 줄로 풀어 쓰고
    # 그만큼 블록 높이를 늘려 세로 중앙 정렬이 어긋나지 않게 한다.
    aff_lines = []
    if c["강사"] and c["강사소속"]:
        aff_lines = wrap(d, c["강사소속"], font(22, "Regular"), colw)[:2]
        extra = len(aff_lines) * 28
        blocks = [(k, f, h + extra if k == "lect" else h) for k, f, h in blocks]

    total = sum(b[2] for b in blocks)
    top = int((H - band_h - total) / 2)
    d.rounded_rectangle([M, top + 6, M + 10, top + total - 24], radius=5, fill=SKY)

    y = top
    for kind, f, h in blocks:
        if kind == "label":
            d.text((tx, y), "부산대학교 · %d년 %d월 직장교육" % (c["연"], c["월"]),
                   font=f, fill=(96, 122, 158))
        elif kind == "main":
            d.text((tx, y), c["주제"], font=f, fill=(26, 38, 58))
        elif kind == "sub":
            d.text((tx, y), c["부제"], font=f, fill=NAVY)
        elif kind == "date":
            d.text((tx, y), c["날짜"], font=f, fill=NAVY)
            wd = measure(d, c["날짜"], f)[0]
            ft = font(int(f.size * 0.76), "Medium")
            d.text((tx + wd + 22, y + int(f.size * 0.20)), c["시간"], font=ft,
                   fill=(86, 104, 132))
        elif kind == "how":
            fk, fv = font(25, "Medium"), font(30, "Bold")
            for i, (k, v) in enumerate(c["참여"]):
                if not v:
                    continue
                yy = y + i * 52
                d.rounded_rectangle([tx, yy + 6, tx + 6, yy + 36], radius=3, fill=SKY)
                d.text((tx + 20, yy + 2), k, font=fk, fill=(120, 142, 172))
                d.text((tx + 20 + 78, yy), v, font=fv, fill=(38, 52, 74))
        elif kind == "lect":
            d.text((tx, y), "강사  %s" % c["강사"], font=f, fill=(74, 92, 120))
            fa = font(22, "Regular")
            for li, line in enumerate(aff_lines):
                d.text((tx, y + 40 + li * 28), line, font=fa, fill=(124, 142, 168))
        y += h

    _band(d, c, W, H, band_h, bg=(28, 44, 74, 246), dot=SKY, fg=(226, 236, 248))
    return img


def _band(d, c, W, H, band_h, bg, dot, fg):
    """하단 안내 띠 — 실질 정보(상시학습·이수기준·캠퍼스 특례)를 싣는다."""
    d.rectangle([0, H - band_h, W, H], fill=bg)
    M = int(W * 0.058)
    items = c["안내"][:4]
    if not items:
        return
    fn = font(25, "Medium")
    # 2열이 들어갈 만큼 넓은지 실제 글자 폭으로 판단한다.
    # 좁은 폭(세로형)에서 2열을 고집하면 왼쪽 항목이 오른쪽을 침범한다.
    half = (W - M * 2) // 2
    widest = max(measure(d, s, fn)[0] for s in items)
    two_col = widest + 30 <= half
    rows = (len(items) + 1) // 2 if two_col else len(items)
    lh = min(42, max(26, int((band_h * 0.72) / max(1, rows))))
    fn = font(min(25, int(lh * 0.62)), "Medium")
    top = H - band_h + max(8, int((band_h - rows * lh) / 2))
    for i, s in enumerate(items):
        cx = M + ((i % 2) * half if two_col else 0)
        cy = top + ((i // 2) if two_col else i) * lh
        d.ellipse([cx, cy + 9, cx + 9, cy + 18], fill=dot)
        d.text((cx + 20, cy), s, font=fn, fill=fg)


def style_e(c, size=(1920, 1080), bg_photo=None):
    """이러닝 전용 서식.

    집합교육과 실을 정보가 다르다. 하루가 아니라 **기간**, 장소가 아니라
    **수강처(URL)**, 참여율이 아니라 **진도율**, 그리고 **강좌가 2개**다.
    D안(집합교육용)에 이러닝을 넣으면 강좌명과 인정시간이 통째로 빠진다.

    그림은 쓰지 않는다. 실어야 할 정보가 많아 자리가 없고, 이 서식에서는
    장식보다 '내가 무엇을 해야 하나'(수강 절차)가 쓸모 있다고 봤다.
    그래서 세로형(메신저용)도 성립한다 — 잘릴 인물이 없다.

    가로 : 왼쪽 머리글 · 오른쪽 절차 · 아래 강좌 카드 2장 나란히
    세로 : 머리글 · 절차 · 강좌 카드 세로로 쌓기
    """
    W, H = size
    portrait = H > W * 1.1
    img = Image.new("RGB", (W, H), CREAM)
    # 세로형에서 가로 기준으로 크기를 재면 글자가 절반으로 줄어 안 읽힌다.
    S = lambda v: max(10, int(v * W / (1200.0 if portrait else 1920.0)))

    d = ImageDraw.Draw(img, "RGBA")
    M = int(W * (0.072 if portrait else 0.058))
    tx = M + S(42)
    강좌 = c.get("강좌") or []
    흐름 = c.get("흐름") or []
    과목 = c.get("과목") or ([c["주제"]] if c["주제"] else [])

    band_h = int(H * (0.135 if portrait else 0.155))
    cgap = S(20) if portrait else S(26)
    card_h = S(170) if not portrait else S(150)
    if 강좌:
        cards_h = (len(강좌) * card_h + (len(강좌) - 1) * cgap) if portrait else card_h
    else:
        cards_h = 0
    gap = S(34)
    head_h = H - band_h - (cards_h + gap if 강좌 else 0)

    colw = int(W - M * 2 - S(42)) if portrait else int(W * 0.44)

    # ---- 머리글
    f_lab = font(S(30), "Medium")
    f_sub = font(S(34), "Medium")
    f_key = font(S(25), "Medium")
    f_val = font(S(30), "Bold")
    f_main = [fit_font(d, s, colw, S(78), "Black", S(34)) for s in 과목]

    rows = []
    if c.get("기간"):
        rows.append(("수강기간", c["기간"]))
    if c.get("수강처"):
        쳐 = c["수강처"].replace(c.get("수강처URL", "") or "\x00", "").strip()
        rows.append(("수강처", 쳐 or c["수강처"]))
    # 주소는 이러닝 포스터에서 가장 실용적인 정보다. 빼면 안 된다.
    if c.get("수강처URL"):
        rows.append(("주소", c["수강처URL"]))
    if c.get("진도율"):
        rows.append(("이수기준", "진도율 %d%%" % c["진도율"]))

    h_lab = int(f_lab.size * 1.6)
    h_main = sum(int(f.size * 1.22) for f in f_main) + S(10)
    h_sub = int(f_sub.size * 1.9)
    h_rows = len(rows) * S(56)
    head_total = h_lab + h_main + h_sub + h_rows

    step_h = S(74)
    flow_h = (S(52) + len(흐름) * step_h) if 흐름 else 0
    flow_gap = S(46)

    if portrait:
        # 세로형은 머리글과 절차가 한 칸에 들어간다. 합이 칸보다 크면 절차가
        # 강좌 카드 위로 올라타므로, 넘치는 만큼 간격부터 줄인다.
        pad = S(26)
        total = head_total + (flow_gap + flow_h if 흐름 else 0)
        while 흐름 and total > head_h - pad * 2 and step_h > S(50):
            if flow_gap > S(24):
                flow_gap -= S(4)
            else:
                step_h -= S(4)
            flow_h = S(52) + len(흐름) * step_h
            total = head_total + flow_gap + flow_h
        y = max(pad, int((head_h - total) / 2))
    else:
        y = max(S(40), int((head_h - head_total) / 2))

    d.rounded_rectangle([M, y + S(8), M + S(10), y + head_total - S(16)],
                        radius=S(5), fill=SKY)
    d.text((tx, y), "부산대학교 · %d년 %d월 직장교육" % (c["연"], c["월"]),
           font=f_lab, fill=(96, 122, 158))
    y += h_lab
    yy = y
    for s, f in zip(과목, f_main):
        d.text((tx, yy), s, font=f, fill=(26, 38, 58))
        yy += int(f.size * 1.22)
    y += h_main
    온라인 = "나라배움터 온라인 수강"
    if len(과목) > 1:
        온라인 += " · %d과정" % len(과목)
    d.text((tx, y), 온라인, font=f_sub, fill=NAVY)
    y += h_sub
    for k, v in rows:
        d.rounded_rectangle([tx, y + S(7), tx + S(6), y + S(38)], radius=S(3), fill=SKY)
        d.text((tx + S(20), y + S(3)), k, font=f_key, fill=(120, 142, 172))
        fv = fit_font(d, v, colw - S(130), f_val.size, "Bold", S(20))
        d.text((tx + S(20) + S(104), y), v, font=fv, fill=(38, 52, 74))
        y += S(56)

    # ---- 수강 절차 (가로형은 오른쪽, 세로형은 머리글 아래)
    if 흐름:
        if portrait:
            px0, fy = tx, y + flow_gap
        else:
            px0 = int(W * 0.565)
            fy = max(S(40), int((head_h - flow_h) / 2))
        f_ft = font(S(28), "Bold")
        f_fs = font(S(31), "Medium")
        f_fn = font(S(23), "Black")
        d.text((px0, fy), "수강 절차", font=f_ft, fill=(120, 142, 172))
        fy += S(52)
        for i, s in enumerate(흐름):
            cyy = fy + i * step_h
            if i < len(흐름) - 1:          # 단계를 잇는 세로선
                d.line([(px0 + S(19), cyy + S(40)), (px0 + S(19), cyy + step_h)],
                       fill=(206, 216, 230), width=max(2, S(3)))
            d.ellipse([px0, cyy + S(4), px0 + S(38), cyy + S(42)], fill=NAVY)
            nw = measure(d, str(i + 1), f_fn)[0]
            d.text((px0 + S(19) - nw // 2, cyy + S(11)), str(i + 1), font=f_fn,
                   fill=(255, 255, 255))
            d.text((px0 + S(56), cyy + S(6)), s, font=f_fs, fill=(44, 58, 80))

    # ---- 강좌 카드
    if 강좌:
        n = len(강좌)
        if portrait:
            cw = W - M * 2
        else:
            cw = (W - M * 2 - cgap * (n - 1)) // n
        f_no = font(S(26), "Black")
        f_cat = font(S(29), "Bold")
        f_tag = font(S(21), "Regular")
        f_tit = font(S(31), "Medium")
        f_tm = font(S(26), "Bold")
        base_y = H - band_h - gap - cards_h
        for i, co in enumerate(강좌):
            if portrait:
                x, cy = M, base_y + i * (card_h + cgap)
            else:
                x, cy = M + i * (cw + cgap), base_y
            rrect(d, [x, cy, x + cw, cy + card_h], S(14), fill=(255, 255, 255, 232),
                  outline=(214, 222, 234), width=2)
            rrect(d, [x, cy, x + S(7), cy + card_h], S(4), fill=SKY)
            px = x + S(26)
            d.ellipse([px, cy + S(24), px + S(34), cy + S(58)], fill=NAVY)
            nw = measure(d, str(i + 1), f_no)[0]
            d.text((px + S(17) - nw // 2, cy + S(28)), str(i + 1), font=f_no,
                   fill=(255, 255, 255))
            d.text((px + S(48), cy + S(26)), co.get("구분") or "", font=f_cat, fill=NAVY)
            tm = co.get("인정시간")
            if tm:
                bw = measure(d, tm, f_tm)[0] + S(34)
                bx = x + cw - S(26) - bw
                rrect(d, [bx, cy + S(22), bx + bw, cy + S(62)], S(20), fill=(255, 240, 224))
                d.text((bx + S(17), cy + S(28)), tm, font=f_tm, fill=WARM)
            if co.get("태그"):
                d.text((px, cy + S(76)), "나라배움터 검색 %s" % co["태그"], font=f_tag,
                       fill=(140, 154, 176))
            tit = co.get("강좌명") or ""
            if tit:
                # 두 줄을 넘으면 잘라내지 않고 글자를 줄인다.
                # 강좌명이 말없이 잘리면 나라배움터에서 못 찾는다.
                ft, lines = f_tit, wrap(d, tit, f_tit, cw - S(52))
                while len(lines) > 2 and ft.size > S(20):
                    ft = font(ft.size - 2, "Medium")
                    lines = wrap(d, tit, ft, cw - S(52))
                for li, ln in enumerate(lines[:2]):
                    d.text((px, cy + S(106) + li * int(ft.size * 1.16)), ln, font=ft,
                           fill=(34, 46, 66))

    _band(d, c, W, H, band_h, bg=(28, 44, 74, 246), dot=SKY, fg=(226, 236, 248))
    return img


STYLES = {"A": style_a, "B": style_b, "C": style_c, "D": style_d, "E": style_e}
STYLE_NAME = {
    "A": "차분한 공문 정제형",
    "B": "사진 배경 + 오버레이",
    "C": "강한 타이포 + 색면 분할",
    "D": "일러스트 + 코드 조판",
    "E": "이러닝 전용 (강좌 카드)",
}


def save(img, path, max_kb=None):
    """PNG 로 저장하되, 용량 상한이 있으면 넘을 때 JPEG 로 품질을 낮춰 맞춘다."""
    img.save(path, "PNG", optimize=True)
    kb = os.path.getsize(path) / 1024
    if max_kb and kb > max_kb:
        jp = os.path.splitext(path)[0] + ".jpg"
        for q in (92, 86, 80, 74, 68):
            img.convert("RGB").save(jp, "JPEG", quality=q, optimize=True, progressive=True)
            if os.path.getsize(jp) / 1024 <= max_kb:
                break
        os.remove(path)          # PNG 로 먼저 쓴 뒤 JPEG 로 바꿨으면 PNG 는 지운다
        return jp, os.path.getsize(jp) / 1024
    return path, kb
