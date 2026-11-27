"""Ortak üretim: şablonu iş klasörüne kopyala/doldur, HyperFrames check + render, ses miksi (ducking, -14 LUFS, kuyruk sessiz)."""
from __future__ import annotations

import html
import json
import os
import pathlib
import random
import shutil
import subprocess

from ortak import ICERIK, SABLON, ff, gunluk, sure

HF = pathlib.Path(os.environ.get("HYPERFRAMES_CLI", str(pathlib.Path.home() / "Documents/mcht-hareket/node_modules/.bin/hyperframes")))


def e(s) -> str:
    return html.escape(str(s), quote=True)


def hazirla(tur: str, is_dir: pathlib.Path, alanlar: dict, ek_varlik: dict | None = None) -> pathlib.Path:
    proje = is_dir / "proje"
    if proje.exists():
        shutil.rmtree(proje)
    shutil.copytree(SABLON / tur, proje)
    shutil.copytree(SABLON / "ortak", proje / "assets", dirs_exist_ok=True)
    for ad, kaynak in (ek_varlik or {}).items():
        shutil.copy(kaynak, proje / "assets" / ad)
    f = proje / "index.html"
    t = f.read_text()
    for k, v in alanlar.items():
        t = t.replace("{{" + k + "}}", v)
    if "{{" in t:
        raise RuntimeError("şablonda doldurulmamış alan: " + t[t.index("{{"):t.index("{{") + 30])
    f.write_text(t)
    return proje


def render(proje: pathlib.Path, cikti: pathlib.Path, zaman_asimi: int = 2400) -> pathlib.Path:
    env = {**os.environ, "HYPERFRAMES_NO_TELEMETRY": "1", "DO_NOT_TRACK": "1"}
    k = subprocess.run([str(HF), "check", "--json"], cwd=proje, env=env, capture_output=True, text=True, timeout=600)
    try:
        ok = json.loads(k.stdout).get("ok")
    except Exception:  # noqa: BLE001
        ok = False
    if not ok:
        raise RuntimeError("hyperframes check hata: " + k.stdout[-1200:])
    r = subprocess.run([str(HF), "render", "--resolution", "portrait", "-q", "delivery", "-o", str(cikti)], cwd=proje, env=env,
                       capture_output=True, text=True, timeout=zaman_asimi)
    if r.returncode or not cikti.exists():
        raise RuntimeError("render olmadı: " + (r.stderr or r.stdout)[-1200:])
    return cikti


def miks(ham_video: pathlib.Path, ses: pathlib.Path, sfx: list[tuple[str, float, float]], sure_sn: float, cikti: pathlib.Path,
         varlik: pathlib.Path) -> pathlib.Path:
    sure_sn = min(sure_sn, sure(ham_video))   # sönüş gerçek video sonuna otursun (şablon süresi kare yuvarlamasıyla uzun kalabiliyor)
    muzikler = sorted((ICERIK / "muzik").glob("*.mp3"))
    muzik = random.choice(muzikler)
    bas = random.uniform(0, max(0, sure(muzik) - sure_sn - 2))
    gir = ["-i", str(ses), "-ss", f"{bas:.2f}", "-i", str(muzik)] + sum([["-i", str(varlik / f"{s[0]}.wav")] for s in sfx], [])
    fc = [f"[0]aresample=48000,pan=stereo|c0=c0|c1=c0,apad=whole_dur={sure_sn}[v0]", "[v0]asplit=2[v][vsc]",
          "[1]aresample=48000,volume=0.17[m0]", "[m0][vsc]sidechaincompress=threshold=0.04:ratio=5:attack=25:release=350[m]"]
    etk = []
    for i, (_, t, v) in enumerate(sfx):
        ms = int(t * 1000); fc.append(f"[{i + 2}]aresample=48000,volume={v},adelay={ms}|{ms}[s{i}]"); etk.append(f"[s{i}]")
    fc.append(f"[v][m]{''.join(etk)}amix=inputs={2 + len(sfx)}:normalize=0:duration=longest,atrim=0:{sure_sn}[mx]")

    def calis(son, ek):
        return subprocess.run(["ffmpeg", "-hide_banner", "-y"] + gir + ["-filter_complex", ";".join(fc) + ";" + son] + ek, capture_output=True, text=True)
    r = calis("[mx]loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json[o]", ["-map", "[o]", "-f", "null", "-"])
    o = json.loads(r.stderr[r.stderr.rindex("{"):r.stderr.rindex("}") + 1])
    ln = (f"loudnorm=I=-14:TP=-1.5:LRA=11:measured_I={o['input_i']}:measured_TP={o['input_tp']}:measured_LRA={o['input_lra']}"
          f":measured_thresh={o['input_thresh']}:offset={o['target_offset']}:linear=true")
    r = calis(f"[mx]{ln},alimiter=limit=0.6:level=false,aresample=48000,alimiter=limit=0.6:level=false,afade=t=out:st={sure_sn - 1.0}:d=1.0:curve=exp,apad=pad_dur=0.5[o]", ["-i", str(ham_video), "-map", f"{2 + len(sfx)}:v", "-map", "[o]", "-t", f"{sure_sn:.3f}",
                                                               "-c:v", "copy", "-c:a", "aac", "-ar", "48000", "-b:a", "192k", "-shortest", str(cikti)])
    if r.returncode:
        raise RuntimeError("miks: " + r.stderr[-800:])
    tepe_duzelt(cikti)
    gunluk(f"miks tamam ({muzik.name}) → {cikti.name}")
    return cikti


def tepe_duzelt(video: pathlib.Path, hedef: float = -1.5) -> None:
    """AAC kodlaması sonrası gerçek tepe -1 dBFS'i aşarsa sesi o kadar kıs (GitHub'daki ffmpeg 6.1'de limiter sonrası +1,2 dBFS görüldü)."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(video), "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True).stderr
    try:
        tp = float(r.split("Peak:")[-1].split("dBFS")[0])
    except Exception:  # noqa: BLE001
        return
    if tp <= -1.0:
        return
    gecici = video.with_suffix(".tepe.mp4")
    k = subprocess.run(["ffmpeg", "-hide_banner", "-y", "-i", str(video), "-map", "0", "-c:v", "copy", "-af", f"volume={hedef - tp:.2f}dB",
                        "-c:a", "aac", "-ar", "48000", "-b:a", "192k", str(gecici)], capture_output=True, text=True)
    if k.returncode == 0:
        gecici.replace(video)
        gunluk(f"ses tepesi {tp:.1f} dBFS → {hedef - tp:.1f} dB kısıldı")
