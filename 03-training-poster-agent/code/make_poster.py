# -*- coding: utf-8 -*-
"""계획(안) → 안내 포스터 시안 생성 (A/B/C 3종)"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import plan_extract
import poster


def main(argv=None):
    ap = argparse.ArgumentParser(description="직장교육 계획(안) → 안내 포스터 시안")
    ap.add_argument("--plan", required=True, help="계획(안) PDF/HWPX, 또는 추출 JSON")
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--bg", default=None, help="B안 배경 사진 경로")
    ap.add_argument("--illust", default=None,
                    help="D안 일러스트 경로(글자 없는 생성 이미지)")
    ap.add_argument("--size", default="1920x1080", help="예: 1920x1080 / 1080x1350")
    ap.add_argument("--styles", default="auto",
                    help="A/B/C/D/E 쉼표 구분. auto 면 유형에 맞춰 고른다 "
                         "(이러닝 → E, 그 밖 → D)")
    ap.add_argument("--max-kb", type=int, default=None, help="용량 상한(KB). 넘으면 JPEG 로 저장")
    ap.add_argument("--ignore-warning", action="store_true",
                    help="원자료가 서로 어긋나도 포스터를 만든다(확인용)")
    a = ap.parse_args(argv)

    if a.plan.lower().endswith(".json"):
        plan = json.load(open(a.plan, encoding="utf-8"))
    else:
        plan = plan_extract.parse(a.plan)

    c = poster.build_content(plan)
    W, H = (int(x) for x in a.size.lower().split("x"))
    os.makedirs(a.outdir, exist_ok=True)

    print("■ %s년 %s월 · %s" % (c["연"], c["월"], c["주제"] +
                               ("(%s)" % c["부제"] if c["부제"] else "")))
    기간 = c["날짜"] + (" ~ " + c["종료"] if c["종료"] else "")
    print("  %s %s" % (기간, c["시간"]))
    print("  참여: %s" % (" / ".join("%s %s" % kv for kv in c["참여"]) or "(없음)"))
    print("  안내 %d줄: %s" % (len(c["안내"]), " / ".join(c["안내"])))
    for i, co in enumerate(c.get("강좌") or [], 1):
        print("  강좌%d: %s · %s · %s" % (i, co["구분"], co["강좌명"], co["인정시간"]))
    if c.get("표경고"):
        print("  ⚠ 원자료 확인 필요 : %s" % c["표경고"])
        print("    임의로 고치지 않았습니다. 계획안을 확인하신 뒤 다시 돌려 주십시오.")
        if not a.ignore_warning:
            # 서로 어긋나는 정보가 실린 포스터를 전 구성원에게 뿌리는 일은
            # 막는다. 그래도 뽑아 봐야 한다면 --ignore-warning 을 준다.
            print("    → 포스터를 만들지 않았습니다. 그래도 확인용으로 뽑으려면")
            print("       --ignore-warning 을 붙여 주십시오.")
            return 2
    print()

    styles = a.styles
    if styles.strip().lower() == "auto":
        styles = "E" if c.get("이러닝") else "D"
        print("  유형에 맞춰 %s안으로 만듭니다 (%s)" % (styles, poster.STYLE_NAME[styles]))
    elif c.get("이러닝") and "E" not in styles.upper():
        print("  ※ 이러닝 달인데 E안이 빠져 있습니다. 강좌명·인정시간·진도율이")
        print("     포스터에 실리지 않습니다. --styles E 를 권합니다.")

    made = []
    for s in styles.split(","):
        s = s.strip().upper()
        fn = poster.STYLES.get(s)
        if not fn:
            print("  알 수 없는 스타일:", s)
            continue
        # E안(이러닝)은 그림을 쓰지 않는다. 강좌 2개·인정시간·주소·수강 절차까지
        # 실어야 해서 그림이 들어갈 자리가 없다. 장식보다 절차가 쓸모 있다고 봤다.
        if s == "E" and a.illust:
            print("  (E안은 그림 대신 수강 절차를 싣습니다 — --illust 는 D안에만 쓰입니다)")
        img = fn(c, (W, H), None if s == "E" else (a.illust if s == "D" else a.bg))
        # 크기를 파일명에 넣는다. 없으면 가로형·세로형이 서로를 덮어쓴다.
        shape = "가로" if W >= H else ("정사각" if W == H else "세로")
        name = "%d년%02d월_직장교육_포스터_%s안_%s%dx%d.png" % (
            c["연"], c["월"], s, shape, W, H)
        path, kb = poster.save(img, os.path.join(a.outdir, name), a.max_kb)
        made.append((s, path, kb))
        print("  %s안 (%s)  %s  %.0fKB" % (s, poster.STYLE_NAME[s],
                                          os.path.basename(path), kb))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
