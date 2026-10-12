# -*- coding: utf-8 -*-
"""구형 한글(.hwp) 본문을 **한글 프로그램 없이** 뽑는다.

왜 필요한가
-----------
7회차까지는 `.hwp` 를 읽으려면 한글(COM)을 띄워야 했다. 느리고,
사용자가 열어 둔 문서를 건드릴 위험이 있고, 창 없는 프로세스가 남는다.
**파일이 수백 개면 쓸 수 없는 방법이다.**

`.hwp` 5.0 은 **OLE 복합문서**다. 구조만 알면 파이썬으로 바로 읽힌다.

    FileHeader              36번째 바이트의 flags — bit0 이 켜져 있으면 본문이 압축돼 있다
    BodyText/SectionN       본문. 압축돼 있으면 raw deflate (`zlib.decompress(d, -15)`)
    레코드 헤더 4바이트      tagID(10bit) | level(10bit) | size(12bit)
                            size 가 0xFFF 면 **다음 4바이트가 진짜 크기**다
    tagID 67                HWPTAG_PARA_TEXT — 본문 글자 (UTF-16LE)

글자 사이에 **제어 문자**가 섞여 있다. 그냥 디코딩하면 깨진 기호가 쏟아진다.
    0~31 중 inline·extended 제어는 **8워드(16바이트)를 차지**하므로 통째로 건너뛴다.
    나머지 제어 문자는 버리되, 문단 끝(13)·줄바꿈(10)은 개행으로 살린다.
"""

import re
import sys
import zlib

import olefile

try:
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
except AttributeError:
    pass

HWPTAG_PARA_TEXT = 67

# 8워드를 차지하는 제어 문자 (inline / extended)
WIDE_CTRL = {1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23}


def _records(buf):
    """레코드 스트림을 (tagID, level, payload) 로 끊어 준다."""
    i, n = 0, len(buf)
    while i + 4 <= n:
        head = int.from_bytes(buf[i:i + 4], "little")
        tag = head & 0x3FF
        lvl = (head >> 10) & 0x3FF
        size = (head >> 20) & 0xFFF
        i += 4
        if size == 0xFFF:                 # 크기가 넘치면 다음 4바이트가 진짜 크기
            if i + 4 > n:
                break
            size = int.from_bytes(buf[i:i + 4], "little")
            i += 4
        yield tag, lvl, buf[i:i + size]
        i += size


def _para_text(payload):
    """문단 레코드에서 글자만 추린다. 제어 문자는 폭을 알고 건너뛴다.

    **서로게이트 쌍을 결합해야 한다.** UTF-16LE 라 한 글자가 두 워드에
    걸치는 경우가 있는데, 그냥 `chr()` 로 넘기면 짝 없는 서로게이트가 남아
    나중에 `encode("utf-8")` 이 통째로 터진다 — 색인 전체가 멈춘다.
    """
    out = []
    i, n = 0, len(payload) // 2 * 2
    while i < n:
        c = int.from_bytes(payload[i:i + 2], "little")
        if c in WIDE_CTRL:
            i += 16                        # 8워드
            continue
        if 0xD800 <= c <= 0xDBFF:          # 상위 서로게이트 — 짝을 찾는다
            if i + 4 <= n:
                c2 = int.from_bytes(payload[i + 2:i + 4], "little")
                if 0xDC00 <= c2 <= 0xDFFF:
                    out.append(chr(0x10000 + ((c - 0xD800) << 10) + (c2 - 0xDC00)))
                    i += 4
                    continue
            i += 2                         # 짝이 없으면 버린다
            continue
        if 0xDC00 <= c <= 0xDFFF:          # 짝 없는 하위 서로게이트
            i += 2
            continue
        if c in (10, 13):
            out.append("\n")
        elif c >= 32:
            out.append(chr(c))
        i += 2
    return "".join(out)


def read_hwp(path):
    """`.hwp` 본문 텍스트. 한글 프로그램을 띄우지 않는다."""
    if not olefile.isOleFile(path):
        raise ValueError("OLE 파일이 아니다 — .hwpx 이거나 손상된 파일일 수 있다")
    ole = olefile.OleFileIO(path)
    try:
        names = ["/".join(p) for p in ole.listdir()]
        if "FileHeader" not in names:
            raise ValueError("FileHeader 가 없다 — .hwp 5.0 이 아니다")
        head = ole.openstream("FileHeader").read()
        compressed = bool(head[36] & 1)

        secs = sorted((s for s in names if re.match(r"BodyText/Section\d+$", s)),
                      key=lambda s: int(s.rsplit("Section", 1)[1]))
        if not secs:
            raise ValueError("BodyText/Section 이 없다")

        chunks = []
        for s in secs:
            data = ole.openstream(s).read()
            if compressed:
                data = zlib.decompress(data, -15)   # raw deflate
            for tag, _lvl, payload in _records(data):
                if tag == HWPTAG_PARA_TEXT:
                    chunks.append(_para_text(payload))
        return "\n".join(chunks)
    finally:
        ole.close()


if __name__ == "__main__":
    t = read_hwp(sys.argv[1])
    lines = [l.strip() for l in t.split("\n") if l.strip()]
    print("문단 %d개 · %d자" % (len(lines), len(t)))
    for l in lines[:int(sys.argv[2]) if len(sys.argv) > 2 else 20]:
        print(" |", l[:76])
