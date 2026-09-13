# -*- coding: utf-8 -*-
"""
포스터 배경 이미지 수집 (Wikimedia Commons)

공공기관 배포물이므로 **라이선스가 명시되고 출처를 남길 수 있는 곳**만 쓴다.
Unsplash·Pexels 는 API 키가 필요하고 이용약관이 기관 배포에 애매해 쓰지 않는다.

받은 이미지마다 `_출처.md` 에 파일명·저작자·라이선스·원본 URL 을 적는다.
"""
import argparse
import json
import os
import re
import urllib.parse
import urllib.request

UA = "PNU-training-poster/1.0 (Pusan National University; educational use)"
API = "https://commons.wikimedia.org/w/api.php"

# 허용 라이선스 (공공 배포 가능)
OK_LICENSE = re.compile(r"public domain|cc0|cc[ -]?by(?![ -]?nc)|attribution", re.I)


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read()


def search(query, limit=12):
    q = urllib.parse.urlencode({
        "action": "query", "format": "json", "generator": "search",
        "gsrsearch": "filetype:bitmap " + query, "gsrnamespace": "6",
        "gsrlimit": str(limit), "prop": "imageinfo",
        "iiprop": "url|size|extmetadata", "iiurlwidth": "1920",
    })
    data = json.loads(get(API + "?" + q))
    pages = (data.get("query") or {}).get("pages") or {}
    out = []
    for p in pages.values():
        ii = (p.get("imageinfo") or [{}])[0]
        meta = ii.get("extmetadata") or {}
        lic = (meta.get("LicenseShortName") or {}).get("value", "")
        author = re.sub(r"<[^>]+>", "", (meta.get("Artist") or {}).get("value", "")).strip()
        if not OK_LICENSE.search(lic):
            continue
        if (ii.get("width") or 0) < 1600:
            continue
        out.append({
            "제목": p.get("title", ""),
            "url": ii.get("thumburl") or ii.get("url"),
            "원본페이지": ii.get("descriptionurl", ""),
            "라이선스": lic,
            "저작자": author or "(표기 없음)",
            "크기": "%sx%s" % (ii.get("width"), ii.get("height")),
        })
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Wikimedia Commons 에서 포스터 배경 후보 수집")
    ap.add_argument("--q", required=True, help="검색어 (영문)")
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--n", type=int, default=3, help="내려받을 개수")
    a = ap.parse_args(argv)
    os.makedirs(a.outdir, exist_ok=True)

    hits = search(a.q)
    print("검색 '%s' → 라이선스 통과 %d건" % (a.q, len(hits)))
    saved = []
    for i, h in enumerate(hits[:a.n], 1):
        ext = os.path.splitext(urllib.parse.urlparse(h["url"]).path)[1] or ".jpg"
        name = "bg_%s_%02d%s" % (re.sub(r"\W+", "_", a.q)[:20], i, ext)
        path = os.path.join(a.outdir, name)
        try:
            with open(path, "wb") as f:
                f.write(get(h["url"]))
            h["파일"] = name
            h["용량KB"] = round(os.path.getsize(path) / 1024)
            saved.append(h)
            print("  받음 %-30s %-10s %s" % (name, h["크기"], h["라이선스"]))
        except Exception as e:
            print("  실패 %s: %s" % (h["제목"][:40], str(e)[:50]))

    if saved:
        md = os.path.join(a.outdir, "_출처.md")
        exists = os.path.exists(md)
        with open(md, "a", encoding="utf-8") as f:
            if not exists:
                f.write("# 배경 이미지 출처\n\n"
                        "공공 배포물이므로 라이선스가 명시된 것만 사용한다.\n"
                        "포스터를 외부에 배포할 때 CC BY 계열은 저작자 표기가 필요하다.\n\n")
            f.write("## 검색어: %s\n\n" % a.q)
            f.write("| 파일 | 저작자 | 라이선스 | 크기 | 원본 |\n|---|---|---|---|---|\n")
            for h in saved:
                f.write("| `%s` | %s | %s | %s | %s |\n" %
                        (h["파일"], h["저작자"][:40], h["라이선스"], h["크기"], h["원본페이지"]))
            f.write("\n")
        print("출처 기록:", md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
