# -*- coding: utf-8 -*-
"""요구 건별 자료의 **「5년간 요구이력」** 칸을 자동으로 채운다.

왜 이 도구가 있는가
-------------------
교육부는 정기직제 요구 건마다 자료를 따로 요구하고, 그 작성 항목에
**「4) 5년간 요구이력」**이 들어 있다.

    ○ 요구목록별로 1)요구명, 2)부서별 업무수행현황, 3)부서 정·현원,
      4) 5년간 요구이력, 5)부서별 업무분장 작성

이 칸을 채우려면 과거 요구서를 전부 뒤져야 한다. 2027년도 자료만 639건이고,
그중 522건(82%)이 제출 이후 대응이었다. **이 도구는 그 칸만 겨냥한다.**

무엇을 하지 않는가
------------------
**요구 사유를 쓰지 않는다.** 증원 논리는 담당자의 판단이다.
이 도구는 **「과거에 무엇을 요구했는가」라는 사실**만 모아 준다.

추출하지 못한 것은 **지어내지 않고 「원문 확인」으로 표시**한다.
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

# 실제 요구서에서 쓰이는 표기 — 색인 전수로 확인한 패턴만 넣었다
PATS = [
    ("정원", re.compile(r"정원\s*\(?\s*증원\s*\)?\s*[:：]?\s*([+±]?\s*\d+\s*명)")),
    ("정원", re.compile(r"정원\s*[:：]\s*([+±]?\s*\d+\s*명)")),
    ("정원", re.compile(r"(?<!직급)증원\s*\(\s*(\d+\s*명)\s*\)")),
    ("기구", re.compile(r"기구\s*\(?\s*신설\s*\)?\s*[:：]?\s*([+]?\s*\d+\s*[과국부실원처단])")),
    ("직급조정", re.compile(r"직급\s*조정\s*[:：]?\s*([±+]?\s*\d+\s*명)")),
]


def tidy(s):
    return re.sub(r"\s+", "", s)


def extract(text):
    """요구 수치를 뽑는다. 같은 값이 여러 번 나오면 한 번만."""
    found = {}
    for label, rx in PATS:
        for m in rx.finditer(text):
            v = tidy(m.group(1))
            found.setdefault(label, [])
            if v not in found[label]:
                found[label].append(v)
    out = []
    for label in ("기구", "정원", "직급조정"):
        if label in found:
            out.append("%s %s" % (label, "·".join(found[label][:3])))
    return " / ".join(out)


def context(text, words, width=70):
    for m in re.finditer("|".join(re.escape(w) for w in words), text):
        s = max(0, m.start() - width // 3)
        return re.sub(r"\s+", " ", text[s:s + width].replace("\n", " ")).strip()
    return ""


def collect(idx, words, kinds=("요구서", "보고"), max_years=5, this_year=None):
    rows = []
    for r in idx["files"]:
        if not r["text"] or r["dup_of"]:
            continue
        if r["kind"] not in kinds:
            continue
        if not all(w in r["text"] for w in words):
            continue
        rows.append(r)

    by_year = {}
    for r in rows:
        y = r["req_year"] or 0
        by_year.setdefault(y, []).append(r)

    years = sorted((y for y in by_year if y), reverse=True)
    if this_year:
        years = [y for y in years if y <= this_year]
    years = years[:max_years]

    out = []
    for y in years:
        # 한 해에 여러 건이면 **요구서를 먼저** 고른다.
        # 보고 문서는 그 해 요구를 통째로 담고 있어, 찾는 건과 무관한 수치까지 섞인다.
        cands = sorted(by_year[y],
                       key=lambda r: (0 if r["kind"] == "요구서" else 1,
                                      -len(extract(r["text"]))))
        best = cands[0]
        out.append({
            "year": y,
            "detail": extract(best["text"]),
            "source": best["name"],
            "id": best["id"],
            "others": len(by_year[y]) - 1,
            "context": context(best["text"], words),
        })
    return out, len(rows)


def render_md(words, rows, total):
    print("# 5년간 요구이력 — 「%s」\n" % " ".join(words))
    if not rows:
        print("해당하는 과거 요구가 색인에 없다. **이력 없음으로 적기 전에 "
              "키워드를 바꿔 다시 확인할 것.**")
        return
    print("| 요구 연도 | 요구 내용 | 출처 |")
    print("|---|---|---|")
    for r in rows:
        d = r["detail"] or "**원문 확인 필요**"
        src = r["source"][:40]
        if r["others"]:
            src += " 외 %d건" % r["others"]
        print("| %d년도 | %s | %s |" % (r["year"], d, src))
    print()
    print("- 색인에서 찾은 관련 자료 **%d건**, 그중 연도별 대표 %d건을 표로 정리함"
          % (total, len(rows)))
    nodet = [r for r in rows if not r["detail"]]
    if nodet:
        print("- **요구 수치를 뽑지 못한 해**: %s — 원문을 열어 확인할 것"
              % ", ".join("%d년도" % r["year"] for r in nodet))
    print()
    print("## 근거 문맥 — **반드시 읽고 거를 것**\n")
    for r in rows:
        if r["context"]:
            print("- **%d년도** `#%d` … %s …" % (r["year"], r["id"], r["context"]))
    print()
    print("> **같은 낱말이 다른 뜻으로 쓰인 해가 섞인다.** 예를 들어 「전산」으로 찾으면")
    print("> 전산 **인력** 요구가 아니라 업무 **전산화**를 말한 문서까지 걸린다.")
    print("> 표를 그대로 옮기지 말고 **위 문맥을 보고 해당 없는 해를 지울 것.**")
    print(">")
    print("> 키워드를 좁히면 줄어든다 — `전산 증원`, `전산6급` 처럼 두 낱말 이상으로.")
    print(">")
    print("> 요구 **사유**는 담당자가 쓴다. 이 표는 「과거에 무엇을 요구했는가」만 모은 것이다.")


def write_hwpx(words, rows, total, out_path):
    """표준일반보고서 서식으로 — 서식에 그대로 붙일 수 있게."""
    # 보고서 서식 스킬 경로 — 환경에 맞게 지정한다.
    # 서식 스킬이 없으면 `--hwpx` 를 쓰지 않아도 된다(표는 화면으로 나온다).
    SK = os.environ.get(
        "GENERAL_REPORT_SKILL",
        os.path.expanduser(os.path.join("~", ".claude", "skills",
                                        "pnu-standard-general-report")))
    if not os.path.isdir(SK):
        raise SystemExit(
            "보고서 서식 스킬을 찾지 못했다: %s\n"
            "환경변수 GENERAL_REPORT_SKILL 로 경로를 지정하거나 --hwpx 를 빼고 실행할 것" % SK)
    sys.path.insert(0, os.path.join(SK, "scripts"))
    from hwpx_builder import Builder
    b = Builder(os.path.join(SK, "assets", "template.hwpx"))
    b.title_box("5년간 요구이력")
    b.p("meta", "<%s>" % (os.environ.get("REPORT_DEPT") or "부서명"))
    b.intro_box(" ○ 「%s」 관련 최근 5개년 정기·수시직제 요구 이력을 정리함"
                % " ".join(words))
    b.p("h1", "□ 요구 이력")
    tbl = [["요구 연도", "요구 내용", "출처"]]
    for r in rows:
        src = r["source"][:34] + (" 외 %d건" % r["others"] if r["others"] else "")
        tbl.append(["%d년도" % r["year"], r["detail"] or "원문 확인 필요", src])
    if len(tbl) == 1:
        tbl.append(["－", "해당 이력 없음", "－"])
    b.table(tbl, widths=[16, 44, 40], aligns=["c", "l", "l"])
    b.p("star", "   * 색인 자료 %d건에서 연도별 대표 건을 정리함" % total)
    nodet = [r for r in rows if not r["detail"]]
    if nodet:
        b.p("star", "   * 요구 수치 미추출: %s (원문 확인 필요)"
            % ", ".join("%d년도" % r["year"] for r in nodet))
    b.p("note", "   ※ 요구 사유는 별도로 작성하여야 함")
    b.save(out_path)
    print("\n서식 파일 생성: %s" % os.path.basename(out_path))


def main():
    p = argparse.ArgumentParser(
        prog="history.py", description="요구 건별 자료의 「5년간 요구이력」을 채운다")
    p.add_argument("words", nargs="+", help="요구명 키워드 (여러 개면 모두 든 자료만)")
    p.add_argument("--index", default=DEFAULT_INDEX)
    p.add_argument("--years", type=int, default=5)
    p.add_argument("--upto", type=int, help="이 연도까지만 (예: 2027)")
    p.add_argument("--hwpx", help="표준일반보고서 서식으로 저장할 경로")
    a = p.parse_args()

    if not os.path.exists(a.index):
        raise SystemExit("색인이 없다. build_index.py 를 먼저 돌릴 것")
    idx = json.loads(io.open(a.index, encoding="utf-8").read())

    rows, total = collect(idx, a.words, max_years=a.years, this_year=a.upto)
    render_md(a.words, rows, total)
    if a.hwpx:
        write_hwpx(a.words, rows, total, a.hwpx)
    return 0


if __name__ == "__main__":
    sys.exit(main())
