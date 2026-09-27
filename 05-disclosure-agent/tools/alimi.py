# -*- coding: utf-8 -*-
"""대학알리미 공시자료 추출 JS 생성기.

대학알리미는 화면 텍스트로 안 긁힌다. 두 겹이다.
  1) 공시항목 목록  → RealGrid (캔버스). dataProvider 를 직접 읽는다.
  2) 공시 데이터 표 → UBIReport 뷰어. 스크롤해야 DOM 에 그려진다.

이 파일은 브라우저에 넣을 JS 를 찍어 준다. 직접 실행하지 않는다.

    python alimi.py items                   # 공시항목 122건 목록
    python alimi.py open  <연도> <항목id>    # 보고서 페이지 열기 (POST)
    python alimi.py grab                    # 현재 페이지에서 표 추출
    python alimi.py parse <출력> [저장.tsv]  # grab 결과를 풀어 TSV 로. 불완전하면 exit 3

    # agent-browser 와 함께 쓰는 법
    agent-browser --session sd --args "--no-sandbox" open https://www.academyinfo.go.kr/index.do
    python alimi.py open 2026 195 | agent-browser --session sd --args "--no-sandbox" eval --stdin
    agent-browser --session sd --args "--no-sandbox" wait --load networkidle
    python alimi.py grab | agent-browser --session sd --args "--no-sandbox" eval --stdin > raw.json
    python alimi.py parse raw.json 직원현황_2026.tsv   # exit 3 이면 다시 뽑는다

JS 안에 한글 주석이 들어 있다. 윈도우 콘솔이 cp949 라 그냥 찍으면 주석이 깨지고,
깨진 바이트가 다음 줄까지 먹어 `const KEYS = ...` 같은 선언이 통째로 사라진다
(실제로 `ReferenceError: KEYS is not defined` 로 터졌다).
→ 아래에서 stdout 을 UTF-8 로 못박는다. 파이프로 바로 넘겨도 안전하다.
"""
import sys

# 콘솔 코드페이지와 무관하게 UTF-8 로 내보낸다. 이 두 줄이 위 사고를 막는다.
try:
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
except AttributeError:      # py3.6 이하
    import codecs
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())

# ── 공시항목 목록 ────────────────────────────────────────────────
# fn_category_open 은 어느 분야를 눌러도 전체(122건)를 싣는다. 분야는 뒤에서 거른다.
ITEMS = r"""
(async () => {
  if (typeof fn_category_open !== 'function') return 'ERR: run this on /index.do';
  fn_category_open('04');
  for (let i = 0; i < 20; i++) {
    await new Promise(r => setTimeout(r, 400));
    if (window.dataProvider2 && dataProvider2.getRowCount() > 0) break;
  }
  const dp = window.dataProvider2;
  if (!dp || dp.getRowCount() === 0) return 'ERR: item grid empty';
  const rows = dp.getJsonRows(0, dp.getRowCount() - 1);
  return rows.map(r => [
    r.item_id,
    r.item_6_ldiv_nm,
    (r.v_shrt_pgm_nm2 || '').trim(),
    (r.v_shrt_pgm_nm3 || '').trim(),
    (r.v_shrt_pgm_nm4 || '').trim()
  ].join('\t')).join('\n');
})()
"""

# ── 보고서 열기 ──────────────────────────────────────────────────
# fetch 로 POST 하면 껍데기만 온다. 데이터는 뷰어가 /NewAcInfo.do 로 따로 받아 그린다.
# 반드시 form 을 실제로 submit 해서 그 페이지를 띄워야 한다.
OPEN = r"""
(() => {
  const P = {
    paramSvyYr: '%(year)s',
    paramItemId: '%(item)s',
    paramSchlDivCd: '%(div)s',
    paramFormClftCd: '30', paramDiv: 'A', paramItemDivCd: '01',
    paramMjrCd: '00', paramMjrItem1: '00', paramMjrItem2: '00',
    paramMjrItem3: '00', paramMjrItem4: '00',
    paramMjrItem1Act: 'N', paramMjrItem4Act: 'N', paramMjrUsStp: '0',
    paramSchlKindCd: '99', paramSchlEstabCd: '99', paramZoneCd: '99',
    paramSortItem: 'SCHL_NM', paramSortMethod: 'ASC',
    paramSearchItem: 'SEARCH_SCHL_NM'
  };
  const f = document.createElement('form');
  f.method = 'POST';
  f.action = '/uipnh/unt/unmcom/RdViewer.do';
  f.target = '_self';
  for (const k in P) {
    const i = document.createElement('input');
    i.type = 'hidden'; i.name = k; i.value = P[k];
    f.appendChild(i);
  }
  document.body.appendChild(f);
  f.submit();
  return 'submitted year=%(year)s item=%(item)s div=%(div)s';
})()
"""

# ── 표 추출 ──────────────────────────────────────────────────────
#  * 뷰어가 scrollpage 모드라 보이는 쪽만 그린다. NextButton.click() 도 gopage(n) 도
#    쪽 번호만 올리고 내용은 안 바뀐다. 반드시 스크롤해야 한다.
#  * 칸이 tr 하나에 하나씩 들어간 절대좌표 레이아웃이다. y 로 묶고 x 로 정렬해야 행이 된다.
#  * 위 행과 같은 값은 비워 두므로(기준연도·학교종류·설립구분·지역·상태) 뒤에서부터 채운다.
#  * 숫자 열 개수는 연도마다 다르다. 절대 상수로 박지 말고 세어서 정한다.
GRAB = r"""
(async () => {
  const v = window.htmlViewer;
  if (!v || !v.divPreviewFrame) return 'ERR: not a UBI report page';
  const pf = v.divPreviewFrame;

  // 전 쪽 그리기.
  //  뷰어가 scrollpage 모드라 '보이는 쪽'만 그린다. 안 보이는 쪽은 DOM 에 아예 없다.
  //  NextButton.click() 도 gopage(n) 도 쪽 번호만 올리고 내용은 안 바뀐다.
  //  스크롤로도 되긴 하지만 창이 숨어 있으면(window.innerHeight === 0)
  //  clientHeight 가 scrollHeight 와 같아져 스크롤 자체가 성립하지 않는다.
  //  → 13쪽 중 2쪽만 그려진 채로 조용히 넘어간다.
  //  그래서 뷰어 내부 함수를 직접 불러 쪽마다 그리게 한다. 창 상태와 무관하다.
  const pageIds = () => Array.from(document.querySelectorAll('[id^="UbiHTMLViewer_previewpage_"]'))
    .filter(e => /previewpage_\d+$/.test(e.id));
  const has = n => !!document.getElementById('UbiHTMLViewer_previewpage_' + n);
  const want = v.totalPage || 1;
  const failed = [];
  for (let n = 1; n <= want; n++) {
    if (has(n)) continue;
    try {
      if (!document.getElementById('UbiHTMLViewer_preview_' + n) && v._createPreview) v._createPreview(n);
      v._requestReportPage(n);
    } catch (e) { failed.push(n); continue; }
    let ok = false;
    for (let i = 0; i < 40; i++) {
      await new Promise(r => setTimeout(r, 250));
      if (has(n)) { ok = true; break; }
    }
    if (!ok) failed.push(n);
  }
  // 그래도 빠진 쪽이 있으면 스크롤로 한 번 더 시도한다 (창이 보일 때만 먹는다)
  if (failed.length) {
    for (let y = 0; y <= pf.scrollHeight; y += 300) {
      pf.scrollTop = y;
      pf.dispatchEvent(new Event('scroll', { bubbles: true }));
      await new Promise(r => setTimeout(r, 150));
    }
    await new Promise(r => setTimeout(r, 2000));
  }

  const roots = pageIds()
    .sort((a, b) => (+a.id.match(/_(\d+)$/)[1]) - (+b.id.match(/_(\d+)$/)[1]));
  if (!roots.length) return 'ERR: no pages drawn';

  const drawn = roots.map(e => +e.id.match(/_(\d+)$/)[1]);
  const totalPage = v.totalPage || drawn.length;

  function grabPage(root) {
    const cells = Array.from(root.querySelectorAll('td'))
      .filter(c => c.children.length === 0 && c.innerText.trim() !== '');
    const byY = {}, rb = root.getBoundingClientRect();
    for (const c of cells) {
      const r = c.getBoundingClientRect();
      if (r.width === 0) continue;
      const y = Math.round((r.top - rb.top) / 4) * 4;
      (byY[y] = byY[y] || []).push({ x: r.left - rb.left, t: c.innerText.trim() });
    }
    return Object.keys(byY).map(Number).sort((a, b) => a - b)
      .map(y => byY[y].sort((a, b) => a.x - b.x).map(o => o.t));
  }

  const pages = roots.map(grabPage);
  const isNum = s => /^-?[\d,]+(\.\d+)?$/.test(s);

  // 숫자 열 개수를 센다 - 행 끝에서 이어지는 숫자의 길이를 모아 최빈값을 쓴다.
  // 앞쪽 '기준연도'(2026)도 숫자지만 학교명이 끊어 주므로 끝에서 세면 안 걸린다.
  const runs = {};
  for (const rows of pages) for (const r of rows) {
    let n = 0;
    while (n < r.length && isNum(r[r.length - 1 - n])) n++;
    if (n >= 2) runs[n] = (runs[n] || 0) + 1;
  }
  const NUM = +Object.keys(runs).sort((a, b) => runs[b] - runs[a] || b - a)[0];
  if (!NUM) return 'ERR: no numeric columns found';

  // 머리글 줄을 그대로 돌려준다. 항목마다 층이 다르므로 해석은 사람이 한다.
  // 14-사 직원 현황은 2022년까지 직종이 10개, 2023년부터 8개다. 머리글을 안 보면 모른다.
  const headerRows = pages[0].filter(r => !r.some(isNum)).slice(0, 6);

  const KEYS = ['status', 'region', 'estab', 'schoolType', 'year'];  // 뒤에서부터 채운다
  const out = [];
  for (const rows of pages) {
    const carry = { year: '', schoolType: '', estab: '', region: '', status: '' };
    for (const r of rows) {
      if (r.length < NUM + 1) continue;
      const nums = r.slice(-NUM);
      if (!nums.every(isNum)) continue;
      const pre = r.slice(0, r.length - NUM);
      const school = pre[pre.length - 1];
      const meta = pre.slice(0, -1);
      const got = {};
      for (let i = 0; i < KEYS.length && meta.length; i++) got[KEYS[i]] = meta.pop();
      for (const k of KEYS) if (got[k] !== undefined) carry[k] = got[k];
      out.push([carry.year, carry.schoolType, carry.estab, carry.region, carry.status, school]
        .concat(nums.map(x => x.replace(/,/g, ''))).join('\t'));
    }
  }

  return JSON.stringify({
    title: document.title,
    totalPage: totalPage,
    pagesDrawn: drawn.length,
    pagesFailed: failed,
    complete: drawn.length === totalPage && failed.length === 0,
    numCols: NUM,
    headerRows: headerRows,
    rowCount: out.length,
    tsv: 'year\tschoolType\testab\tregion\tstatus\tschool\t' +
         Array.from({ length: NUM }, (_, i) => 'n' + (i + 1)).join('\t') + '\n' + out.join('\n')
  });
})()
"""


def parse(path, out_prefix=None):
    """grab 출력을 읽어 요약을 찍고 TSV 를 저장한다.

    agent-browser 는 eval 결과를 JSON 문자열로 한 번 더 감싸서 준다.
    그대로 json.loads 하면 깨진다. 여기서 벗겨 준다.

    complete 가 false 면 0 이 아닌 값으로 끝낸다.
    「불완전한 데이터는 쓰지 않는다」를 글이 아니라 종료코드로 강제한다.
    """
    import io
    import json

    raw = io.open(path, encoding="utf-8").read().strip()
    obj = json.loads(raw)
    if isinstance(obj, str):          # 이중 인코딩을 한 겹 벗긴다
        obj = json.loads(obj)
    if isinstance(obj, str):          # 혹시 두 겹이면 한 번 더
        obj = json.loads(obj)

    ok = bool(obj.get("complete"))
    sys.stderr.write(
        "complete=%s  pages=%s/%s  failed=%s  numCols=%s  rows=%s\n" % (
            ok, obj.get("pagesDrawn"), obj.get("totalPage"),
            obj.get("pagesFailed"), obj.get("numCols"), obj.get("rowCount")))
    for h in obj.get("headerRows", []):
        sys.stderr.write("  header | %s\n" % " | ".join(h))

    tsv = obj.get("tsv", "")
    if out_prefix:
        dst = out_prefix if out_prefix.endswith(".tsv") else out_prefix + ".tsv"
        io.open(dst, "w", encoding="utf-8").write(tsv)
        sys.stderr.write("saved: %s\n" % dst)
    else:
        sys.stdout.write(tsv)

    if not ok:
        sys.stderr.write(
            "\n!! complete=false — 쪽이 덜 그려졌다. 이 데이터는 쓰지 마라. 다시 뽑아라.\n")
        return 3
    return 0


def main():
    if len(sys.argv) < 2:
        sys.stdout.write(__doc__)
        return 1
    mode = sys.argv[1]
    if mode == "items":
        sys.stdout.write(ITEMS)
    elif mode == "open":
        if len(sys.argv) < 4:
            sys.stderr.write("usage: alimi.py open <year> <itemId> [schlDivCd=02]\n")
            return 2
        sys.stdout.write(OPEN % {
            "year": sys.argv[2],
            "item": sys.argv[3],
            "div": sys.argv[4] if len(sys.argv) > 4 else "02",
        })
    elif mode == "grab":
        sys.stdout.write(GRAB)
    elif mode == "parse":
        if len(sys.argv) < 3:
            sys.stderr.write("usage: alimi.py parse <grab출력파일> [저장할.tsv]\n")
            return 2
        return parse(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    else:
        sys.stderr.write("unknown mode: %s\n" % mode)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
