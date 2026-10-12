# -*- coding: utf-8 -*-
"""자료 더미에서 .hwp 를 얼마나 읽어낼 수 있는지 실측한다.

「읽을 수 있다」를 짐작으로 말하지 않는다. 전수로 돌려 보고 숫자를 낸다.
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
from hwp_text import read_hwp

ROOT = sys.argv[1] if len(sys.argv) > 1 else "01.원본데이터"
LIMIT = int(sys.argv[2]) if len(sys.argv) > 2 else 0

DIST = "이 문서는 상위 버전의 배포용 문서입니다"   # 본문이 잠긴 배포용 파일

ok, dist, fail, empty = [], [], [], []
paths = []
for dp, _dn, fn in os.walk(ROOT):
    for f in fn:
        if f.lower().endswith(".hwp"):
            paths.append(os.path.join(dp, f))
paths.sort()
if LIMIT:
    paths = paths[:LIMIT]

for p in paths:
    try:
        t = read_hwp(p)
    except Exception as e:
        fail.append((p, str(e)[:60]))
        continue
    s = t.strip()
    if DIST in s[:200]:
        dist.append(p)
    elif len(s) < 30:
        empty.append(p)
    else:
        ok.append((p, len(s)))

n = len(paths)
print("== .hwp %d개 실측 ==" % n)
print("  읽힘        %4d  (%.0f%%)" % (len(ok), 100.0 * len(ok) / n if n else 0))
print("  배포용 잠김  %4d  (%.0f%%)" % (len(dist), 100.0 * len(dist) / n if n else 0))
print("  내용 거의 없음 %3d" % len(empty))
print("  실패        %4d" % len(fail))
if ok:
    avg = sum(c for _, c in ok) / len(ok)
    print("  읽힌 것 평균 %,d자".replace(",", "") % int(avg))
for p, e in fail[:5]:
    print("   실패:", os.path.basename(p)[:50], "|", e)
if dist[:3]:
    print("   잠김 예:", os.path.basename(dist[0])[:60])
