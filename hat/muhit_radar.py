"""Muhit Sakarya için rakip + trend radarı (Mac'te, Yorumdan hattının günlük çalışmasının sonunda; 3 günde bir).
Muhit'in sunucusundaki Instagram anahtarı (Instagram ile Giriş) başka hesapları okuyamadığı için radar burada çıkarılır ve YALNIZ sonuç
dosyası (anahtar değil) sunucuya gönderilir: /opt/mcht/muhit/is/durum/radar.json → Muhit senaryo yazarı okur."""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import subprocess

import radar
from ortak import DURUM, env, gunluk, json_sor, oku, yaz

HESAPLAR = ["pekiyasakarya", "adapazarihaber"]
YT = ["sakarya", "adapazarı", "sapanca", "sakaryalı"]
SUNUCU = "root@87.76.130.148"
ANAHTAR = pathlib.Path.home() / ".ssh" / "mcht_ajans_ops_ed25519"
HEDEF = "/opt/mcht/muhit/is/durum/radar.json"


def calistir(zorla: bool = False) -> None:
    o = oku("muhit-radar.json", {}) or {}
    if not zorla and o.get("tarih", "") >= (dt.date.today() - dt.timedelta(days=3)).isoformat():
        return
    try:
        hs = [h for h in (radar.hesap_oku(env("IG_KARTVIZIT_ID"), env("IG_KARTVIZIT_TOKEN"), u) for u in HESAPLAR) if h]
        yt = radar.yt_trend(radar.yt_erisim(env("YT_CLIENT_ID"), env("YT_CLIENT_SECRET"), env("YT_REFRESH_TOKEN")), YT)
        yeni = radar.ozet(lambda i: json_sor("Sadece JSON döndür.", i, 0.4), "Muhit Sakarya (Sakarya şehir medyası, sıcak ve esprili)",
                          "Sakaryalılar, Adapazarı'nda yaşayanlar, SAÜ öğrencileri, gurbetteki Sakaryalılar", radar.tutanlar(hs) + yt)
        if not yeni:
            gunluk("muhit radar: özet çıkmadı (sonra yeniden)"); return
        yaz("muhit-radar.json", yeni)
        yol = DURUM / "muhit-radar.json"
        r = subprocess.run(["scp", "-q", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "-i", str(ANAHTAR), str(yol), f"{SUNUCU}:{HEDEF}"],
                           capture_output=True, text=True, timeout=60)
        gunluk(f"muhit radar: {len(hs)} Instagram, {len(yt)} Shorts → sunucu {'tamam' if r.returncode == 0 else 'GÖNDERİLEMEDİ ' + r.stderr[:120]}")
    except Exception as e:  # noqa: BLE001
        gunluk(f"muhit radar yapılamadı: {e}")


if __name__ == "__main__":
    import sys
    calistir("--zorla" in sys.argv)
