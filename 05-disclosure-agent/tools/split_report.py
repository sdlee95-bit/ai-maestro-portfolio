# -*- coding: utf-8 -*-
"""보고서 md 를 「결재본」과 「작업기록」으로 가른다.

개고 이력은 작업 기록이지 보고 문서가 아니다. 결재선에 올릴 문서에서 뺀다.
(4회차에서 붙임 2 를 「대외주의」로 분리한 것과 같은 취지다.)

    python split_report.py 보고서_v5.md

  → 보고서_v5_결재본.md   본문 §1~§8 + 각주. 개고 이력 없음
  → 보고서_v5_작업기록.md  개고 이력 전 판본 + 어디서 잘라냈는지

**본문은 한 글자도 고치지 않는다.** 자르기만 한다.
각주 정의(`[^n]: …`)가 개고 이력 뒤에 있으면 결재본으로 되돌려 붙인다 —
안 그러면 결재본의 각주 참조가 전부 깨진다.
"""
import io
import os
import re
import sys

MARK = re.compile(r"^##\s*개고\s*이력", re.M)
FOOT = re.compile(r"^\[\^[^\]]+\]:", re.M)


def split(path):
    src = io.open(path, encoding="utf-8").read()
    m = MARK.search(src)
    if not m:
        sys.stderr.write("개고 이력 절을 못 찾았다. 자르지 않는다.\n")
        return 2

    head, tail = src[:m.start()], src[m.start():]

    # 개고 이력 뒤에 남은 각주 정의를 본문 쪽으로 되돌린다
    moved = [ln for ln in tail.split("\n") if FOOT.match(ln)]
    if moved:
        tail = "\n".join(ln for ln in tail.split("\n") if not FOOT.match(ln))
        head = head.rstrip() + "\n\n" + "\n".join(moved) + "\n"

    base, ext = os.path.splitext(path)
    p_rep, p_log = base + "_결재본" + ext, base + "_작업기록" + ext
    name = os.path.basename(path)

    io.open(p_rep, "w", encoding="utf-8").write(
        head.rstrip() + "\n\n---\n\n"
        "*개고 이력(감사 ↔ 개고 왕복 기록)은 결재본에서 뺐다. "
        "`" + os.path.basename(p_log) + "` 에 있다.*\n")

    io.open(p_log, "w", encoding="utf-8").write(
        "# 작업 기록 — " + name + "\n\n"
        "이 문서는 **결재본에 편철하지 않는다.** 감사 ↔ 개고 왕복의 기록이다.\n"
        "본문은 `" + os.path.basename(p_rep) + "` 에 있고, 검토의견은 `검토의견_v1~v3.md` 다.\n\n"
        "---\n\n" + tail.lstrip())

    for p in (p_rep, p_log):
        n = len(io.open(p, encoding="utf-8").read())
        sys.stderr.write("%s  %d자\n" % (os.path.basename(p), n))
    if moved:
        sys.stderr.write("각주 정의 %d개를 결재본으로 되돌렸다\n" % len(moved))
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    if len(sys.argv) < 2:
        sys.stdout.write(__doc__)
        sys.exit(1)
    sys.exit(split(sys.argv[1]))
