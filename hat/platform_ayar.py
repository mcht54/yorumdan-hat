"""Panel "hesap başına platform ayarları" (2026-11-27): panelde bir hesabın bir platformu kapatılınca hat o platforma paylaşmaz.

Panel senkron yanıtı: {"platform_ayarlari": {"hesaplar": {"<hesap>": {"<platform>": true|false}}}}
Panel hesap kodları ↔ hat: kartvizit → kartvizitci, web → siteciabi, para → cuzdan.
Bu hattın platformları: instagram (Reels + ilk yorum/yanıt), facebook (Facebook Reels), youtube (YouTube Shorts).
Kural: alan yoksa / hesap ya da platform yoksa AÇIK. Yalnız açıkça false olan kapalıdır.
Önbellek: durum/platform_ayarlari.json (özel durum deposu mcht54/yorumdan-durum; Mac ve Actions arasında eşitlenir).
Panel ulaşılamazsa son bilinen ayar; dosya yoksa/bozuksa hepsi açık.
"""
from __future__ import annotations

import datetime as dt
import json

import ortak

PANEL_HESAP = {"kartvizit": "kartvizitci", "web": "siteciabi", "para": "cuzdan"}
PLATFORMLAR = ("instagram", "facebook", "youtube")
NOT = "atlandı: panelde kapalı"
DOSYA = "platform_ayarlari.json"


def dosya():
    return ortak.DURUM / DOSYA


def kaydet(yanit) -> bool:
    """Senkron yanıtındaki platform_ayarlari'nı önbelleğe yazar. Alan yoksa (panelin eski sürümü) önbelleğe dokunmaz."""
    if not isinstance(yanit, dict):
        return False
    pa = yanit.get("platform_ayarlari")
    if not isinstance(pa, dict) or not isinstance(pa.get("hesaplar"), dict):
        return False
    hesaplar = {str(h): {str(p): v for p, v in d.items() if isinstance(v, bool)}
                for h, d in pa["hesaplar"].items() if isinstance(d, dict)}
    if not dosya().exists() or oku() != hesaplar:   # değişmediyse yazılmaz (durum deposunda boş commit olmasın)
        dosya().write_text(json.dumps({"hesaplar": hesaplar, "zaman": dt.datetime.now().isoformat(timespec="seconds")},
                                      ensure_ascii=False, indent=1))
        kapali = sorted(f"{h}/{p}" for h, d in hesaplar.items() if h in PANEL_HESAP.values() for p, v in d.items() if v is False)
        ortak.gunluk(f"panel: platform ayarları güncellendi; kapalı: {', '.join(kapali) or 'yok'}")
    return True


def oku() -> dict:
    try:
        h = json.loads(dosya().read_text()).get("hesaplar")
        return h if isinstance(h, dict) else {}
    except Exception:  # noqa: BLE001  (dosya yok/bozuk → hepsi açık)
        return {}


def acik(tur: str, platform: str) -> bool:
    """tur: hattın hesap kodu (kartvizit / web / para)."""
    d = oku().get(PANEL_HESAP.get(tur, tur))
    return not isinstance(d, dict) or d.get(platform) is not False


def kapalilar(tur: str) -> list[str]:
    return [p for p in PLATFORMLAR if not acik(tur, p)]


def paylasildi(k: dict) -> bool:
    """"Bugün zaten paylaşıldı" kapısı, bölüm numarası ve Düzelt için: Instagram'a gitti ya da (Instagram panelde kapalıyken)
    Facebook/YouTube'a gönderim denendi. Denenmiş ama hata almış Facebook/YouTube'u yalnız Düzelt yeniden dener (kayıttaki *_hata);
    günlük çalışma aynı gün ikinci bölüm üretip yeniden paylaşmaz."""
    return bool(k.get("medya_id") or k.get("fb_link") or k.get("yt_link") or k.get("yayin_denendi"))


def yayinda(k: dict) -> bool:
    """Panel tablosu için: en az bir platformda bağlantısı olan bölüm."""
    return bool(k.get("medya_id") or k.get("fb_link") or k.get("yt_link"))
