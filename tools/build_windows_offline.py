"""Build a self-contained, offline Windows (x64) package of the program.

The result is one ZIP: unzip anywhere on a Windows 10/11 x64 PC without Python or internet
and double-click ``Baslat.bat``. Contents:

  o-ring/
    python/            Python embeddable distribution (python.org) + Lib/site-packages
    src/ data/ app/    the program, its data files and the Streamlit app
    .streamlit/        Streamlit config (no usage statistics, no e-mail prompt)
    O-Ring.exe         starts the app in its own window (Edge/Chrome app mode), see tools/launcher
    Baslat.bat         fallback: starts the app and opens the default browser
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
chcp 65001 >nul
cd /d "%~dp0"
title O-Ring Yuva Tasarim Programi
echo O-Ring Yuva Tasarim Programi baslatiliyor...
echo Tarayici birkac saniye icinde acilacak: http://127.0.0.1:8501
echo Programi kapatmak icin bu pencereyi kapatin.
start "" cmd /c "timeout /t 6 >nul & start http://127.0.0.1:8501"
"%~dp0python\python.exe" -m streamlit run "%~dp0app\streamlit_app.py" --server.address 127.0.0.1 --server.port 8501 --server.headless true
pause
"""

CONFIG = """[browser]
gatherUsageStats = false

[server]
address = "127.0.0.1"
headless = true
fileWatcherType = "none"

[client]
toolbarMode = "minimal"

[global]
developmentMode = false
"""

README = r"""O-Ring Yuva Tasarim Programi - internetsiz Windows paketi
==========================================================

Kurulum gerekmez, Python gerekmez, internet gerekmez, YONETICI YETKISI GEREKMEZ.
Program hicbir sey kurmaz ve kayit defterine yazmaz; her sey bu klasorun icinden calisir.

1. (Onerilir) ZIP dosyasina sag tiklayin > Ozellikler > alttaki "Engellemeyi kaldir"
   kutusunu isaretleyin > Tamam. Bu, Windows'un "internetten gelen dosya" uyarisini
   onler ve yonetici yetkisi istemez.
2. ZIP dosyasini KENDI kullanici klasorunuzde yazma izniniz olan bir yere cikarin,
   ornegin Belgeler veya C:\Users\<adiniz>\o-ring. (C:\Program Files gibi yonetici
   isteyen klasorlere cikarmayin.) Yol cok uzun olmamali.
3. o-ring klasorundeki "O-Ring.exe" dosyasina cift tiklayin. Isterseniz sag tik >
   "Gonder" > "Masaustu (kisayol olustur)" ile masaustune kisayol koyabilirsiniz.
4. Kendi penceresinde "Baslatiliyor" ekrani acilir; birkac saniye sonra program gelir.
   Pencere Microsoft Edge (yoksa Chrome) ile cizilir ama adres cubugu/sekme yoktur ve
   internete baglanmaz.
5. Programi kapatmak icin pencereyi kapatin; arka plandaki hesap sunucusu da kapanir.

Notlar
- O-Ring.exe calismazsa (ornegin kurum politikasi .exe'yi engelliyorsa) "Baslat.bat"
  ayni programi varsayilan tarayicida acar; kapatmak icin siyah pencereyi kapatin.
- Edge/Chrome bulunamazsa program varsayilan tarayicida acilir ve bir bilgi kutusu
  cikar; programi kapatmak icin o kutuda Tamam'a basin.
- Hata olursa kayit dosyasi: %LOCALAPPDATA%\o-ring\son_calisma.log
- Program yalnizca bu bilgisayardan erisilebilir (127.0.0.1); bu nedenle Windows
  Guvenlik Duvari izin sormamalidir. Sorarsa "Iptal" demeniz yeterlidir.
- Windows SmartScreen "bilinmeyen yayinci" uyarisi verirse: "Ek bilgi" > "Yine de calistir".
- Kurumunuzun BT politikasi (AppLocker vb.) kullanici klasorlerinden program
  calistirmayi tamamen engelliyorsa paket calismaz; bu durumda BT birimine danisin.
- Veri dosyalari (malzemeler, kurallar, standart olculer) "data" klasorundedir.

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
    for name in ("src", "data", "app"):
        shutil.copytree(ROOT / name, stage / name,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".gitkeep"))
    (stage / ".streamlit").mkdir()
    (stage / ".streamlit" / "config.toml").write_text(CONFIG, encoding="utf-8")
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
