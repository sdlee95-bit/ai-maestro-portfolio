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
    ap.add_argument("--styles", default="A,B,C")
    ap.add_argument("--max-kb", type=int, default=None, help="용량 상한(KB). 넘으면 JPEG 로 저장")
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
    if c.get("미지원"):
        print("  ※ 이러닝 달입니다. 강좌명·인정시간·진도율 이수기준은 아직 포스터에")
        print("     싣지 않습니다. 집합교육용 레이아웃이라 별도 서식이 필요합니다.")
    print()

    made = []
    for s in a.styles.split(","):
        s = s.strip().upper()
        fn = poster.STYLES.get(s)
        if not fn:
            print("  알 수 없는 스타일:", s)
            continue
        img = fn(c, (W, H), a.illust if s == "D" else a.bg)
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
