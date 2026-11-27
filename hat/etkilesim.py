"""Yorumdan hesapları (Kartvizitçi, Siteci Abi, Cüzdan Hocası) yorum/DM → MCHT panel köprüsü (insan onaylı cevap; müşteri adayı → Gelenler).
Ortak çekirdek: hat/etkilesim_ortak.py (kaynak ~/Documents/mcht-etkilesim; elle düzenleme, kopyala.sh ile güncelle).
Panel ucu: /api/icerik-takvimi/senkron/yorumdan/etkilesim (aynı HMAC sırrı, hat/.panel_anahtari).
Depo HERKESE AÇIK: yorum/mesaj içeriği ve kullanıcı adları loga/dosyaya yazılmaz; yalnız sayılar (gunluk → özel durum deposu).
DM: bu hesapların anahtarlarında instagram_manage_messages izni yok (2026-11-27 ölçüldü: #230) → yalnız yorumlar; izin gelince dm açılır.

  python hat/etkilesim.py          # bir tur (panel.yml her 15 dk)
  python hat/etkilesim.py deneme   # yazmadan: okur + sınıflar, yalnız sayıları yazar
"""
from __future__ import annotations

import json
import sys

import etkilesim_ortak as ortak
from guvenlik import uygunsuz
from instagram import Instagram
from ortak import ayarlar, groq_json, gunluk, json_sor

YORUMCU = ("Bu hesabın videolarında izleyiciler yorumda kendi işletmesi/verisi için ÜCRETSİZ video isteği yazar (ör. 'benim kartvizitimi yap', "
           "'maaşım 30 bin'); bu istekler satin_alma DEĞİL, 'oneri' sınıfıdır. satin_alma yalnız gerçek ücretli iş isteği: baskı/sipariş, fiyat sorma, "
           "'site/kartvizit yaptırmak istiyorum', iletişim/telefon bırakma.")
HESAPLAR = {
    "kartvizit": {"ad": "Kartvizitçi", "site": "mchttasarim.com.tr", "crm": True,
                  "bilgiler": ["Kartvizitçi, Mchttasarım Reklam Ajansı'nın (Sakarya) yorumdan kartvizit tasarlayan hesabıdır",
                               "Baskılı kartvizit ve kurumsal kimlik işleri Mchttasarım tarafından yapılır; fiyat için DM/WhatsApp", YORUMCU]},
    "web": {"ad": "Siteci Abi", "site": "sitemucidi.com.tr", "crm": True,
            "bilgiler": ["Siteci Abi, yorumdan işletmeye örnek web sitesi çıkaran hesaptır; siteler Site Mucidi ile yapılır",
                         "Site Mucidi'nde site oluşturmak ücretsizdir, yayına almak ücretlidir (7 gün deneme)",
                         "Özel web sitesi işleri Mchttasarım Reklam Ajansı tarafından yapılır", YORUMCU]},
    # Cüzdan Hocası bütçe/eğitim hesabıdır, satılacak hizmeti yok → CRM kapalı (yalnız soru/şikâyet/öneri ve cevap taslağı)
    "para": {"ad": "Cüzdan Hocası", "site": "", "crm": False, "rol": "samimi, yatırım tavsiyesi vermeyen bir bütçe anlatıcısısın",
             "bilgiler": ["Cüzdan Hocası yorumdaki maaş/kira bilgisinden örnek bütçe planı çıkarır", "Yatırım tavsiyesi verilmez", YORUMCU]},
}


def _yz(sistem: str, istem: str) -> dict | None:
    """Önce ücretsiz Groq: Gemini'nin günlük metin bütçesi (hesaplar ortak) içerik üretimine kalsın; Groq düşerse Gemini."""
    return groq_json(sistem, istem, 0.3) or json_sor(sistem, istem, 0.3)


def _panel(yuk: dict) -> dict | None:
    from panel import ANAHTAR, _istek
    if not ANAHTAR.exists():
        return None
    try:
        return _istek("/etkilesim", yuk)
    except Exception as e:  # noqa: BLE001
        gunluk(f"etkileşim: panel {type(e).__name__} {getattr(e, 'code', '')}")
        return None


def hesaplar() -> list[dict]:
    ay = (ayarlar() or {}).get("hesaplar", {})
    out = []
    for kod, h in HESAPLAR.items():
        ig = Instagram(kod)
        if not ig.hazir or not (ay.get(kod) or {}).get("aktif", True):
            continue
        out.append({**h, "kod": kod, "istek": ig._istek, "ig_id": ig.kimlik, "kendi": (ay.get(kod) or {}).get("ig_kullanici", ""), "dm": None})
    return out


def calistir(deneme: bool = False) -> dict:
    hs = hesaplar()
    if not hs:
        gunluk("etkileşim: bağlı hesap yok")
        return {}
    sonuc = ortak.tur(hs, _panel, _yz, uygunsuz, log=gunluk, yalniz_oku=deneme, gun=30 if deneme else ortak.GUN)
    if deneme:
        o = ortak.ozet_say(sonuc)
        o["kaynakli"] = sum(1 for a in sonuc["adaylar"] if a.get("medya"))
        print(json.dumps(o, ensure_ascii=False))
    return sonuc


if __name__ == "__main__":
    calistir(deneme=len(sys.argv) > 1 and sys.argv[1] == "deneme")
