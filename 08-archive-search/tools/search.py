# -*- coding: utf-8 -*-
"""직제 요구 이력에서 **「작년엔 뭐라고 썼지」**를 찾는다.

왜 이 도구가 있는가
-------------------
정기직제는 제출이 끝이 아니다. 교육부·행안부·기재부가 **요구 건마다** 자료를
따로 요구하고, 그때마다 과거 자료를 뒤진다. 2027년도 한 해만 639개,
그중 **522개(82%)가 제출 이후 대응**이었다.

파일명만으로는 못 찾는다. 「전산인력 증원을 작년에 어떻게 썼더라」는
**본문을 열어 봐야** 알 수 있고, 그 본문이 수백 개다.

쓰는 법
-------
    python search.py <키워드...> [--year 2025] [--kind 요구서] [--max 8]
    python search.py --timeline <키워드>      연도별 등장 추이
    python search.py --doc <id|경로조각>       그 문서 전문

여러 키워드를 주면 **모두 든 문서**만 찾는다(AND).
"""

import argparse
import io
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_INDEX = os.path.join(HERE, "index.json")


def load(path):
    if not os.path.exists(path):
        raise SystemExit("색인이 없다. 먼저 build_index.py 를 돌릴 것: %s" % path)
    return json.loads(io.open(path, encoding="utf-8").read())


def snippets(text, words, width=90, limit=2):
    """매치 주변을 잘라 보여 준다. 첫 매치만 보면 맥락을 놓친다."""
    out, seen = [], set()
    for m in re.finditer("|".join(re.escape(w) for w in words), text):
        s = max(0, m.start() - width // 2)
        frag = re.sub(r"\s+", " ", text[s:s + width].replace("\n", " ")).strip()
        key = frag[:40]          # 같은 문단이 여러 번 나오면 한 번만 보여 준다
        if key in seen:
            continue
        seen.add(key)
        out.append(frag)
        if len(out) >= limit:
            break
    return out


def search(idx, words, year=None, kind=None, kmax=8, show_dup=False, per_year=2):
    hits = []
    for r in idx["files"]:
        if not r["text"]:
            continue
        if year and r["req_year"] != year:
            continue
        if kind and kind not in r["kind"]:
            continue
        if r["dup_of"] and not show_dup:
            continue
        t = r["text"]
        counts = [t.count(w) for w in words]
        if min(counts) == 0:               # AND — 하나라도 없으면 제외
            continue
        hits.append((sum(counts), r))
    hits.sort(key=lambda x: (-(x[1]["req_year"] or 0), -x[0]))
    if per_year:
        # 최신 연도만 가득 차면 **「작년엔 뭐라고 썼지」에 답을 못 한다.**
        # 연도마다 상위 몇 건씩만 뽑아 과거가 보이게 한다.
        picked, cnt = [], {}
        for sc, r in hits:
            y = r["req_year"] or 0
            if cnt.get(y, 0) >= per_year:
                continue
            cnt[y] = cnt.get(y, 0) + 1
            picked.append((sc, r))
            if len(picked) >= kmax:
                break
        return picked
    return hits[:kmax]


def cmd_search(a, idx):
    hits = search(idx, a.words, a.year, a.kind, a.max, per_year=a.per_year)
    if not hits:
        print("찾은 것 없음 — 키워드를 줄이거나 연도·종류 조건을 빼 볼 것")
        return 1
    print("# 「%s」 — %d건\n" % (" + ".join(a.words), len(hits)))
    cur = None
    for score, r in hits:
        y = r["req_year"]
        if y != cur:
            cur = y
            print("\n## %s년도 직제\n" % (y or "연도 미상"))
        print("**%s**  `#%d` · %s · %s · %s회" %
              (r["name"], r["id"], r["kind"], r["date"] or "날짜없음", score))
        print("  └ %s" % r["folder"][:88])
        for s in snippets(r["text"], a.words):
            print("  > …%s…" % s)
        print()
    print("\n전문을 보려면: `python search.py --doc <#번호>`")
    return 0


def cmd_timeline(a, idx):
    w = a.timeline
    rows = {}
    for r in idx["files"]:
        if not r["text"] or r["dup_of"]:
            continue
        c = r["text"].count(w)
        if c:
            y = r["req_year"] or 0
            d = rows.setdefault(y, {"건수": 0, "횟수": 0, "예": []})
            d["건수"] += 1
            d["횟수"] += c
            if len(d["예"]) < 2:
                d["예"].append(r["name"][:46])
    if not rows:
        print("「%s」 가 나오는 문서가 없다" % w)
        return 1
    print("# 「%s」 연도별 등장\n" % w)
    print("| 요구 연도 | 문서 | 언급 | 대표 문서 |")
    print("|---|---|---|---|")
    for y in sorted(rows):
        d = rows[y]
        print("| %s | %d건 | %d회 | %s |" %
              (("%d년도" % y) if y else "미상", d["건수"], d["횟수"], " / ".join(d["예"])))
    return 0


def cmd_doc(a, idx):
    key = a.doc.lstrip("#")
    cand = [r for r in idx["files"]
            if (key.isdigit() and r["id"] == int(key)) or key in r["path"]]
    if not cand:
        print("그런 문서가 없다:", a.doc)
        return 1
    r = cand[0]
    print("# %s\n" % r["name"])
    print("- 경로 : %s" % r["path"])
    print("- 종류 : %s · 요구연도 %s · 날짜 %s · %d자\n" %
          (r["kind"], r["req_year"], r["date"] or "-", r["chars"]))
    body = r["text"]
    if a.max and a.max > 0:
        lines = [l for l in body.split("\n") if l.strip()][:a.max * 20]
        body = "\n".join(lines)
    print(body)
    if len(cand) > 1:
        print("\n(같은 조건의 문서가 %d건 더 있다)" % (len(cand) - 1))
    return 0


def main():
    p = argparse.ArgumentParser(prog="search.py",
                                description="직제 요구 이력 검색 — 「작년엔 뭐라고 썼지」")
    p.add_argument("words", nargs="*", help="키워드 (여러 개면 모두 든 문서만)")
    p.add_argument("--index", default=DEFAULT_INDEX)
    p.add_argument("--year", type=int, help="요구 연도로 좁힌다 (예: 2025)")
    p.add_argument("--kind", help="자료 종류 (요구서·서식·배정결과·보고·업무분장)")
    p.add_argument("--max", type=int, default=8)
    p.add_argument("--per-year", type=int, default=2, dest="per_year",
                   help="연도마다 최대 몇 건 (0 = 제한 없음)")
    p.add_argument("--timeline", metavar="키워드", help="연도별 등장 추이")
    p.add_argument("--doc", metavar="번호|경로", help="그 문서 전문")
    a = p.parse_args()

    idx = load(a.index)
    if a.timeline:
        return cmd_timeline(a, idx)
    if a.doc:
        return cmd_doc(a, idx)
    if not a.words:
        p.print_help()
        return 2
    return cmd_search(a, idx)


if __name__ == "__main__":
    sys.exit(main())
