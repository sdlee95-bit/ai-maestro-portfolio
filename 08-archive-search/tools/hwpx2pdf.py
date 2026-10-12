# -*- coding: utf-8 -*-
"""생성한 .hwpx 를 한글로 열어 .hwp 와 .pdf 로 저장한다."""
import os, sys, subprocess
sys.stdout.reconfigure(encoding="utf-8")
import win32com.client as win32

def kill_headless():
    subprocess.run(["powershell","-NoProfile","-Command",
        "Get-Process Hwp -EA SilentlyContinue | Where-Object { $_.MainWindowHandle -eq 0 } | Stop-Process -Force"],
        capture_output=True, timeout=30)

def windows_open():
    r = subprocess.run(["powershell","-NoProfile","-Command",
        "(Get-Process Hwp -EA SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Measure-Object).Count"],
        capture_output=True, text=True, timeout=30)
    return int((r.stdout or "0").strip() or 0)

def convert(src):
    if windows_open() != 0:
        raise SystemExit("한글 창이 열려 있다. 닫고 다시 실행할 것")
    kill_headless()
    base = os.path.splitext(os.path.abspath(src))[0]
    hwp = win32.gencache.EnsureDispatch("HWPFrame.HwpObject")
    try:
        try: hwp.XHwpWindows.Item(0).Visible = False
        except Exception: pass
        try: hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")
        except Exception: pass
        if not hwp.Open(os.path.abspath(src), "HWPX", "forceopen:true"):
            raise SystemExit("열지 못했다: %s" % src)
        for ext, fmt in ((".hwp","HWP"), (".pdf","PDF")):
            p = base + ext
            if os.path.exists(p): os.remove(p)
            hwp.SaveAs(p, fmt, "")
            print("  %s  %s bytes" % (os.path.basename(p), os.path.getsize(p)))
    finally:
        try:
            hwp.Clear(1); hwp.Quit()
        except Exception: pass
        del hwp
        kill_headless()

if __name__ == "__main__":
    convert(sys.argv[1])
