# -*- coding: utf-8 -*-
"""생성 AI 워터마크(반투명 도형) 제거 — 덧칠이 아니라 역합성.

워터마크는 원본 위에 흰색을 일정 비율로 덮은 것이다.

    관측 = (1-a)·원본 + 255·a        ->        원본 = (관측 - 255a) / (1-a)

역산은 선형 연산이라 인물 윤곽·경계도 그대로 살아난다. 덧칠·번지기와 달리
모양이 뭉개지지 않는다.

기본값은 **Gemini 의 마름모(sparkle) 표식**을 1376x768 출력에서 맞춘 값이다.
이미지가 바뀌면 위치·크기는 반드시 다시 확인한다 — `--probe` 로 후보를 찾고
`--center/--radius` 로 지정한다. 불투명도 `a` 는 도구가 같으면 대개 그대로 쓴다.

    python unwatermark.py 원본.png 결과.png --probe
    python unwatermark.py 원본.png 결과.png --center 1256,648 --radius 26.7,27.1

가장 좋은 방법은 애초에 워터마크가 안 찍히게 하는 것이다.
표식이 들어갈 자리에 여백을 두고 생성한 뒤 잘라내면 된다.
"""
import argparse
import numpy as np
from PIL import Image

# Gemini sparkle 기준값 (1376x768 출력에서 측정)
D_CENTER = (1256.009, 647.996)
D_RADIUS = (26.688, 27.074)
D_P = 0.6453      # p<1 이라 변이 오목하다 = 4각 별
D_ALPHA = 0.312   # 별 바깥에서 보간한 원래 밝기로 직접 측정, R·G·B 일치
D_FEATHER = 0.709


def alpha_map(shape_yx, cx, cy, rx, ry, p, a, fw, x0, y0):
    gy, gx = np.mgrid[y0:y0 + shape_yx[0], x0:x0 + shape_yx[1]]
    ux, uy = (gx + 0.5 - cx) / rx, (gy + 0.5 - cy) / ry
    n = np.maximum((np.abs(ux) ** p + np.abs(uy) ** p) ** (1.0 / p), 1e-9)
    d = (n - 1.0) * (np.hypot(gx + 0.5 - cx, gy + 0.5 - cy) / n)  # 경계까지 거리
    t = np.clip(0.5 - d / (2.0 * fw), 0.0, 1.0)
    return a * t * t * (3.0 - 2.0 * t)      # smoothstep 으로 가장자리 번짐 재현


def probe(im):
    """밝기 이상이 몰린 자리를 찾아 후보를 알려 준다(대충의 위치만)."""
    g = np.asarray(Image.fromarray(im.astype("uint8")).convert("L"), float)
    h, w = g.shape
    blocks = []
    for by in range(0, h - 48, 24):
        for bx in range(0, w - 48, 24):
            b = g[by:by + 48, bx:bx + 48]
            ring = np.concatenate([b[0], b[-1], b[:, 0], b[:, -1]])
            blocks.append((float(b.mean() - ring.mean()), bx + 24, by + 24))
    blocks.sort(reverse=True)
    print("밝기가 주변보다 튀는 자리 (워터마크 후보):")
    for v, x, y in blocks[:6]:
        print("  중심 %4d,%-4d  주변보다 +%.1f" % (x, y, v))
    print("\n확대해 눈으로 확인한 뒤 --center / --radius 로 지정할 것.")


def main():
    ap = argparse.ArgumentParser(description="생성 AI 워터마크 역합성 제거")
    ap.add_argument("src")
    ap.add_argument("dst", nargs="?")
    ap.add_argument("--probe", action="store_true", help="위치 후보만 찾고 끝낸다")
    ap.add_argument("--center", default="%f,%f" % D_CENTER, help="cx,cy")
    ap.add_argument("--radius", default="%f,%f" % D_RADIUS, help="rx,ry")
    ap.add_argument("--p", type=float, default=D_P, help="모양 지수(<1 이면 오목)")
    ap.add_argument("--alpha", type=float, default=D_ALPHA, help="불투명도")
    ap.add_argument("--feather", type=float, default=D_FEATHER, help="가장자리 번짐(px)")
    a = ap.parse_args()

    im = np.asarray(Image.open(a.src).convert("RGB"), dtype=np.float64)
    if a.probe:
        probe(im)
        return 0
    if not a.dst:
        ap.error("결과 파일 경로가 필요합니다 (--probe 가 아니면)")

    cx, cy = (float(v) for v in a.center.split(","))
    rx, ry = (float(v) for v in a.radius.split(","))
    x0, x1 = max(0, int(cx - rx) - 8), min(im.shape[1], int(cx + rx) + 9)
    y0, y1 = max(0, int(cy - ry) - 8), min(im.shape[0], int(cy + ry) + 9)
    al = alpha_map((y1 - y0, x1 - x0), cx, cy, rx, ry, a.p, a.alpha,
                   a.feather, x0, y0)[:, :, None]
    im[y0:y1, x0:x1, :] = (im[y0:y1, x0:x1, :] - 255.0 * al) / (1.0 - al)
    Image.fromarray(np.clip(im, 0, 255).round().astype("uint8"), "RGB").save(a.dst)
    print("영역 x %d~%d / y %d~%d · 최대 알파 %.3f" % (x0, x1, y0, y1, al.max()))
    print("저장:", a.dst)
    print("※ 결과를 반드시 확대해 볼 것. 테두리가 남으면 --center 를 0.5px 씩 옮겨 본다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
