"""Yorum/DM → panel (insan onaylı cevap + müşteri adayı → Gelenler/CRM) — TÜM sosyal hatların ORTAK çekirdeği.

KAYNAK: ~/Documents/mcht-etkilesim/etkilesim_ortak.py. Kopyalar (DEĞİŞİNCE `kopyala.sh` ile güncelle, elle düzenleme yapma):
  IG Otopilot  otopilot/etkilesim_ortak.py   (4 marka; GitHub Actions, OIDC kanal ig_otopilot)
  Yorumdan     hat/etkilesim_ortak.py        (Kartvizitçi, Siteci Abi, Cüzdan Hocası; panel.yml, HMAC kanal yorumdan)
  Dijital Çırak dc/etkilesim_ortak.py        (bolum-uret; etkilesim.yml, OIDC kanal dijital_cirak)
  mcht-sosyal  VDS /opt/mcht/mcht-sosyal/hat/etkilesim_ortak.py (HMAC kanal mcht)
  Muhit        VDS /opt/mcht/muhit/hat/etkilesim_ortak.py        (HMAC kanal muhit; CRM KAPALI — şehir medyası)

Akış (her hat kendi zamanlayıcısıyla, 15-60 dk'da bir):
  1) her hesabın son gönderilerindeki yorumları (+ izin varsa Instagram DM'lerini) toplar,
  2) panele kimlik listesini sorar → yalnız panelin bilmediklerine yapay zekâ (ücretsiz: Gemini → Groq) cevap TASLAĞI + sınıf yazar,
  3) panele bırakır: satin_alma → Gelenler (CRM) + bildirim, sikayet → uyarı; kaynak içerik (medya kimliği + link) her kayıtta durur,
  4) panelde "Gönder" denmiş cevapları gönderir, sonucu bildirir. Panel onayı olmadan HİÇBİR cevap gitmez (spam/platform riski).
GİZLİLİK: Bazı depolar herkese açık → yorum/mesaj içeriği ve kullanıcı adları loga/dosyaya YAZILMAZ; yalnız sayılar.
Bağımlılık yok (yalnız stdlib); hatın Graph isteği, yapay zekâ ve panel çağrısı parametre olarak verilir.
"""
from __future__ import annotations

import datetime as dt
import re

SURUM = "2026-11-27"
SINIFLAR = ("satin_alma", "soru", "sikayet", "ovgu", "oneri", "spam", "diger")
GUN = 3          # son 3 günün yorum/mesajı (panel kimliğe göre ayıklar)
EN_COK_GONDERI = 12


def _zaman(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00").replace("+0000", "+00:00"))


def yorumlar(istek, ig_id: str, kod: str, sinir: dt.datetime, kendi: str = "", en_cok: int = EN_COK_GONDERI) -> list[dict]:
    """istek(yontem, yol, **params) -> dict (graph.facebook.com ya da graph.instagram.com, hattın anahtarıyla).
    Her öğede kaynak içerik: medya (gönderi/Reels kimliği), link (permalink), baglam (açıklamanın başı)."""
    medya = istek("GET", f"{ig_id}/media", fields="id,caption,permalink,timestamp,comments_count", limit=en_cok).get("data", [])
    out = []
    for md in medya:
        if md.get("comments_count") == 0:
            continue  # boş gönderi için istek atma (oran sınırı)
        for y in istek("GET", f"{md['id']}/comments", fields="id,text,username,timestamp", limit=50).get("data", []):
            if (kendi and y.get("username") == kendi) or _zaman(y["timestamp"]) < sinir:
                continue
            out.append({"id": f"ig-yorum:{y['id']}", "kod": kod, "tur": "yorum", "hedef": y["id"], "kullanici": y.get("username", ""),
                        "metin": y.get("text", ""), "zaman": y["timestamp"], "link": md.get("permalink"), "medya": md["id"],
                        "baglam": (md.get("caption") or "")[:200]})
    return out


def mesajlar(istek_sayfa, yol: str, kendi_id: str, kod: str, sinir: dt.datetime) -> list[dict]:
    """Instagram DM. istek_sayfa(yontem, yol, **params): sayfa anahtarlı Graph isteği. yol: '<sayfa>/conversations' (Facebook
    sayfası üzerinden) ya da 'me/conversations' (Instagram ile Giriş). instagram_manage_messages izni gerekir."""
    v = istek_sayfa("GET", yol, platform="instagram", fields="updated_time,messages.limit(5){id,message,from,created_time}", limit=20)
    out = []
    for k in v.get("data", []):
        for msj in (k.get("messages") or {}).get("data", []):
            kim = msj.get("from") or {}
            if kim.get("id") == kendi_id or not msj.get("message") or _zaman(msj["created_time"]) < sinir:
                continue
            out.append({"id": f"ig-dm:{msj['id']}", "kod": kod, "tur": "dm", "hedef": kim.get("id", ""), "kullanici": kim.get("username", ""),
                        "metin": msj["message"], "zaman": msj["created_time"], "link": None, "medya": None, "baglam": ""})
    return out


def taslak(oge: dict, hesap: dict, json_sor, uygunsuz=None) -> dict:
    """Cevap taslağı + sınıf + konu + (yalnız kişinin yazdığı) müşteri bilgisi.
    hesap: {ad, site, bilgiler: [doğru bilgi], rol (isteğe bağlı), crm (False → satın alma sınıfı yok, ör. şehir medyası)}.
    json_sor(sistem, istem) -> dict|None (hattın ücretsiz yapay zekâsı). uygunsuz(*metin) -> kategori|None (kural katmanı)."""
    kat = uygunsuz(oge.get("metin", ""), oge.get("kullanici", "")) if uygunsuz else None
    if kat:  # bahis/kumar/+18/argo: cevap yazılmaz, müşteri adayı sayılmaz, yapay zekâya gitmez
        return {"taslak": "", "not": f"Uygunsuz içerik ({kat}); cevap yazılmadı.", "oncelik": "dusuk", "sinif": "spam", "konu": "", "musteri": None}
    crm = hesap.get("crm", True)
    rol = hesap.get("rol") or "sıcak ve yardımsever bir müşteri temsilcisisin"
    sistem = (f"Sen {hesap['ad']} Instagram hesabını yöneten, {rol}. Türkçe, 'siz' diye, kısa (en çok 2-3 cümle) "
              "ve doğal yaz; robot gibi değil. Soruyu doğrudan cevapla. Yalnız aşağıdaki DOĞRU BİLGİLERE dayan; fiyat, stok, süre, kampanya gibi "
              f"bilmediğin bir şeyi uydurma, onun yerine {('siteye (' + hesap['site'] + ') ya da ') if hesap.get('site') else ''}DM/WhatsApp'a yönlendir. "
              "Emoji en çok 1. Spam, reklam, hakaret ya da alakasız ise taslak boş olsun ve 'not' alanına nedenini yaz. Kişisel veri isteme.\n"
              f"DOĞRU BİLGİLER: {' | '.join(map(str, hesap.get('bilgiler') or []))}")
    sinif_tarif = ("satin_alma = almak, yaptırmak, fiyat/rezervasyon/teklif istemek; " if crm else
                   "satin_alma KULLANMA (bu hesap satış yapmaz; işbirliği/reklam sorusu = soru); ")
    istem = (f"{'Gönderi altına yorum' if oge['tur'] == 'yorum' else 'Instagram DM'}: \"{oge['metin'][:800]}\"\n"
             + (f"Gönderinin konusu: {oge['baglam'][:200]}\n" if oge.get("baglam") else "")
             + 'JSON: {"taslak": "", "not": "", "oncelik": "yuksek|normal|dusuk", "sinif": "satin_alma|soru|sikayet|ovgu|oneri|spam|diger", '
               '"konu": "", "musteri": {"ad": "", "telefon": "", "ihtiyac": "", "hizmet": ""}}\n'
               f"oncelik: satın alma/fiyat/rezervasyon sorusu = yuksek. sinif: {sinif_tarif}"
               "sikayet = memnuniyetsizlik, olumsuz deneyim, kızgınlık (cevabı özür + çözüm + DM/WhatsApp'a davet; savunma yok); "
               "oneri = öneri, istek, haber/konu ihbarı. "
               "konu: yorumun konusu 1-3 kelime, küçük harf (ör. 'fiyat', 'teslim süresi', 'tasarım beğenisi'). "
               "musteri: YALNIZ kişinin kendisinin yazdığı bilgiler (ad, telefon, ne istediği, hangi hizmet); yazmadıysa boş bırak, ASLA tahmin etme.")
    try:
        v = json_sor(sistem, istem) or {}
    except Exception:  # noqa: BLE001 — yapay zekâ düşerse taslaksız kayıt (insan yazar)
        v = {}
    sinif = v.get("sinif") if v.get("sinif") in SINIFLAR else None
    if sinif == "satin_alma" and not crm:
        sinif = "soru"
    m = v.get("musteri") if isinstance(v.get("musteri"), dict) and crm else {}
    musteri = {k: str(m.get(k) or "")[:200] for k in ("ad", "telefon", "ihtiyac", "hizmet") if str(m.get(k) or "").strip()}
    return {"taslak": str(v.get("taslak") or "")[:900], "not": str(v.get("not") or ("" if v else "Yapay zekâ yanıt vermedi; cevabı sen yaz."))[:200],
            "oncelik": "yuksek" if sinif in ("satin_alma", "sikayet") else (v.get("oncelik") if v.get("oncelik") in ("yuksek", "normal", "dusuk") else "normal"),
            "sinif": sinif, "konu": re.sub(r"\s+", " ", str(v.get("konu") or "")).strip().lower()[:40], "musteri": musteri or None}


def gonder(oge: dict, hesap: dict) -> None:
    """Panelde onaylanmış cevabı gönderir. Yorum: POST {yorum}/replies; DM: hesap['dm_gonder'](alici, metin)."""
    if oge["tur"] == "yorum":
        hesap["istek"]("POST", f"{oge['hedef']}/replies", message=oge["metin"])
    elif oge["tur"] == "dm" and hesap.get("dm_gonder"):
        hesap["dm_gonder"](oge["hedef"], oge["metin"])
    else:
        raise RuntimeError("bu hesapta bu tür gönderilemez")


def tur(hesaplar: list[dict], panel, json_sor, uygunsuz=None, log=print, gun: int = GUN, simdi: dt.datetime | None = None,
        yalniz_oku: bool = False) -> dict:
    """Bir tur. hesaplar: [{kod, ad, site, bilgiler, crm, istek, ig_id, kendi (kullanıcı adı), dm: callable()->list|None, dm_gonder}].
    panel(yuk) -> dict|None (hattın kanal köprüsü). yalniz_oku=True: panele yazmaz/göndermez, sınıflandırmayı döndürür (deneme)."""
    sinir = (simdi or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc) - dt.timedelta(days=gun)
    adaylar, durumlar, idx = [], {}, {h["kod"]: h for h in hesaplar}
    for h in hesaplar:
        d = {}
        try:
            adaylar += yorumlar(h["istek"], h["ig_id"], h["kod"], sinir, h.get("kendi", ""))
            d["yorum"] = "ok"
        except Exception as e:  # noqa: BLE001
            d["yorum"] = f"hata: {str(e)[:160]}"
        if h.get("dm"):
            try:
                adaylar += h["dm"](sinir)
                d["dm"] = "ok"
            except Exception as e:  # noqa: BLE001
                d["dm"] = f"hata: {str(e)[:160]}"
        else:
            d["dm"] = "kapalı: bu hesabın anahtarında Instagram mesaj izni yok"
        durumlar[h["kod"]] = d
    if yalniz_oku:
        for a in adaylar:
            a.update(taslak(a, idx[a["kod"]], json_sor, uygunsuz))
        return {"adaylar": adaylar, "durumlar": durumlar}
    yanit = panel({"adaylar": [a["id"] for a in adaylar], "durumlar": durumlar})
    if yanit is None:
        log("etkileşim: panele ulaşılamadı; sonraki turda yeniden denenecek")
        return {"panel": False}
    bilinmeyen = set(yanit.get("bilinmeyen", []))
    yeni = []
    for a in adaylar:
        if a["id"] in bilinmeyen:
            a.update(taslak(a, idx[a["kod"]], json_sor, uygunsuz))
            yeni.append(a)
    sonuc = []
    for g in yanit.get("gonderilecek", []):
        try:
            if g.get("kod") not in idx:
                raise RuntimeError("hesap bu hatta değil")
            gonder(g, idx[g["kod"]])
            sonuc.append({"id": g["id"], "durum": "gonderildi"})
        except Exception as e:  # noqa: BLE001
            sonuc.append({"id": g["id"], "durum": "hata", "neden": str(e)[:200]})
    if yeni or sonuc:
        for i in range(0, max(len(yeni), 1), 100):  # panel sınırı 100 öğe
            panel({"yeni": yeni[i:i + 100], "sonuc": sonuc if i == 0 else []})
    log(f"etkileşim: {len(adaylar)} aday, {len(yeni)} yeni ({sum(1 for a in yeni if a.get('sinif') == 'satin_alma')} müşteri adayı, "
        f"{sum(1 for a in yeni if a.get('sinif') == 'sikayet')} şikâyet), {sum(1 for s in sonuc if s['durum'] == 'gonderildi')} cevap gönderildi, "
        f"{sum(1 for s in sonuc if s['durum'] == 'hata')} hata; durum: "
        + ", ".join(f"{k} yorum={v.get('yorum', '-')[:4]} dm={v.get('dm', '-')[:4]}" for k, v in durumlar.items()))
    return {"panel": True, "aday": len(adaylar), "yeni": len(yeni), "gonderildi": sum(1 for s in sonuc if s["durum"] == "gonderildi")}


def ozet_say(sonuc: dict) -> dict:
    """Deneme çıktısı için içeriksiz özet (sınıf sayıları + hesap durumları)."""
    s: dict = {}
    for a in sonuc.get("adaylar", []):
        s.setdefault(a["kod"], {}).setdefault(a.get("sinif") or "yok", 0)
        s[a["kod"]][a.get("sinif") or "yok"] += 1
    return {"siniflar": s, "durumlar": sonuc.get("durumlar", {})}
