"""Build a self-contained, offline Windows (x64) package of the program.

The result is one ZIP: unzip anywhere on a Windows 10/11 x64 PC without Python or internet
and double-click ``Baslat.bat``. Contents:

  o-ring/
    python/            Python embeddable distribution (python.org) + Lib/site-packages
    src/ data/         the calculation program and its data files
    desktop/           the desktop user interface (Qt / PySide6)
    O-Ring.exe         starts the desktop program without a console window (tools/launcher)
    Baslat.bat         fallback: the same with python\pythonw.exe
    BENIOKU.txt        short Turkish instructions

Dependencies are the exact versions pinned in uv.lock, installed as Windows wheels
(win_amd64, cp313) with ``uv pip install --target``. O-Ring.exe is cross-compiled from
tools/launcher with Go (GOOS=windows). Run from the repository root (needs internet, uv and go):

    uv run python tools/build_windows_offline.py [--python 3.13.17] [--out dist]
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

BAT = r"""@echo off
cd /d "%~dp0"
start "" "%~dp0python\pythonw.exe" "%~dp0desktop\main.py"
"""

README = r"""O-Ring Yuva Tasarim Programi - internetsiz Windows paketi
==========================================================

Kurulum gerekmez, Python gerekmez, internet gerekmez, YONETICI YETKISI GEREKMEZ.
Program hicbir sey kurmaz ve kayit defterine yazmaz; her sey bu klasorun icinden calisir.
Tarayici kullanmaz: kendi masaustu penceresinde acilir.

1. (Onerilir) ZIP dosyasina sag tiklayin > Ozellikler > alttaki "Engellemeyi kaldir"
   kutusunu isaretleyin > Tamam. Bu, Windows'un "internetten gelen dosya" uyarisini
   onler ve yonetici yetkisi istemez.
2. ZIP dosyasini KENDI kullanici klasorunuzde yazma izniniz olan bir yere cikarin,
   ornegin Belgeler veya C:\Users\<adiniz>\o-ring. (C:\Program Files gibi yonetici
   isteyen klasorlere cikarmayin.) Yol cok uzun olmamali.
3. o-ring klasorundeki "O-Ring.exe" dosyasina cift tiklayin. Isterseniz sag tik >
   "Gonder" > "Masaustu (kisayol olustur)" ile masaustune kisayol koyabilirsiniz.
4. Program penceresi birkac saniye icinde acilir. Kapatmak icin pencereyi kapatin.

Notlar
- O-Ring.exe calismazsa (ornegin kurum politikasi .exe'yi engelliyorsa) "Baslat.bat"
  ayni programi acar.
- Hata olursa kayit dosyasi: %LOCALAPPDATA%\o-ring\son_calisma.log
- Windows SmartScreen "bilinmeyen yayinci" uyarisi verirse: "Ek bilgi" > "Yine de calistir".
- Kurumunuzun BT politikasi (AppLocker vb.) kullanici klasorlerinden program
  calistirmayi tamamen engelliyorsa paket calismaz; bu durumda BT birimine danisin.
- Veri dosyalari (malzemeler, kurallar, standart olculer, ISO 286 toleranslari)
  "data" klasorundedir.

Python {py} (python.org embeddable, SHA-256 {sha}) ve uv.lock'taki surumler kullanilmistir.
"""


def run(cmd: list[str], **kw) -> str:
    print("+", " ".join(cmd))
    return subprocess.run(cmd, check=True, text=True, capture_output=True, **kw).stdout


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--python", default="3.13.17")
    ap.add_argument("--out", default="dist")
    args = ap.parse_args()
    py = args.python
    abi = "cp" + "".join(py.split(".")[:2])  # cp313
    out = ROOT / args.out
    stage = out / "o-ring"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)

    # 1. embeddable Python
    url = f"https://www.python.org/ftp/python/{py}/python-{py}-embed-amd64.zip"
    zpath = out / f"python-{py}-embed-amd64.zip"
    if not zpath.exists():
        print("download", url)
        urllib.request.urlretrieve(url, zpath)
    sha = hashlib.sha256(zpath.read_bytes()).hexdigest()
    with zipfile.ZipFile(zpath) as z:
        z.extractall(stage / "python")
    pth = next((stage / "python").glob("python*._pth"))
    zipname = pth.name.replace("._pth", ".zip")
    pth.write_text(f"{zipname}\n.\nLib\\site-packages\n..\\src\nimport site\n", encoding="ascii")

    # 2. Windows wheels for the pinned dependencies
    req = out / "requirements-win.txt"
    req.write_text(run(["uv", "export", "--no-dev", "--no-hashes", "--format", "requirements-txt",
                        "--no-emit-project"], cwd=ROOT))
    site = stage / "python" / "Lib" / "site-packages"
    run(["uv", "pip", "install", "--target", str(site), "--python-platform", "x86_64-pc-windows-msvc",
         "--python-version", ".".join(py.split(".")[:2]), "--only-binary", ":all:", "--no-deps",
         "-r", str(req)])

    # 3. program, data, app, config, launcher
    for name in ("src", "data", "desktop"):
        shutil.copytree(ROOT / name, stage / name,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".gitkeep"))
    (stage / "Baslat.bat").write_bytes(BAT.replace("\n", "\r\n").encode("ascii"))
    run(["go", "build", "-trimpath", "-ldflags", "-H=windowsgui -s -w", "-o", str(stage / "O-Ring.exe"), "."],
        cwd=ROOT / "tools" / "launcher", env={**os.environ, "GOOS": "windows", "GOARCH": "amd64",
                                              "CGO_ENABLED": "0"})
    (stage / "BENIOKU.txt").write_bytes(README.format(py=py, sha=sha).replace("\n", "\r\n").encode("utf-8"))
    for extra in ("SPEC.md", "README.md"):
        shutil.copy(ROOT / extra, stage / extra)
    shutil.copytree(ROOT / "docs", stage / "docs")

    # 4. sanity: only Windows / pure-python binaries
    bad = [p for p in site.rglob("*.so")]
    if bad:
        raise SystemExit(f"non-Windows binaries found: {bad[:5]}")
    pyds = list(site.rglob("*.pyd"))
    print(f"{len(pyds)} Windows extension modules (.pyd)")
    for need in ("PySide6", "shiboken6", "matplotlib", "reportlab", "ezdxf"):
        if not (site / need).is_dir():
            raise SystemExit(f"missing package in the bundle: {need}")
    for unwanted in ("streamlit", "plotly", "pyarrow"):
        if (site / unwanted).exists():
            raise SystemExit(f"browser-UI package should not be in the bundle: {unwanted}")

    # 5. zip
    final = out / f"o-ring-windows-x64-py{py}.zip"
    if final.exists():
        final.unlink()
    with zipfile.ZipFile(final, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in sorted(stage.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(out))
    print(f"wrote {final} ({final.stat().st_size / 1e6:.1f} MB); python sha256 {sha}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
