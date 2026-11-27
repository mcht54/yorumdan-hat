"""Hat ↔ MCHT panel senkronu (İçerik takvimi › Yorumdan Tasarım). Panel yoksa, anahtar yoksa ya da ağ düşerse hat DURMAZ: her hata
günlüğe yazılır, senkron sessizce atlanır.

Gönderir: iki hesabın bölüm kayıtları (durum/kartvizit-bolumler.json, durum/web-bolumler.json; firma, sektör, gün no, Instagram linki,
          video adı), bugünün/yarının sıradaki çalışması (launchd saati), bugünkü günlük hataları (uyarı), ayarlar (mod, hesaplar, duraklat).
Alır    : yalnız "duraklat" / "devam" iş emri → durum/panel.json'a yazılır; gunluk.py çalışmanın başında bakar.
Kimlik  : HMAC-SHA256(sır, "<ms>.<gövde>") hex → X-Muhit-Zaman / X-Muhit-Imza başlıkları (paneldeki diğer hatlarla aynı şema, AYRI sır).
          Sır hat/.panel_anahtari dosyasında (chmod 600, gitte YOK); ağda hiç dolaşmaz, yalnız imza gider (HTTPS).
          Panelde aynı sır: /data/keys/yorumdan_senkron (YORUMDAN_SENKRON_ANAHTAR_DOSYASI).

  .venv/bin/python hat/panel.py          # elle senkron
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import pathlib
import plistlib
import time
import urllib.error
import urllib.request

from ortak import DURUM, KOK, ayarlar, env, gunluk, oku, yaz

TR = dt.timezone(dt.timedelta(hours=3))
PANEL = env("PANEL_URL", "https://panel.mchttasarim.com.tr").rstrip("/") + "/api/icerik-takvimi/senkron/yorumdan"
ANAHTAR = KOK / "hat" / ".panel_anahtari"
HESAPLAR = ("kartvizit", "web", "para")
VARSAYILAN_SAAT = {"kartvizit": "12:15", "web": "19:15", "para": "20:30"}  # launchd okunamazsa
GECIKME_DK = 90  # çalışma saatinden bu kadar sonra hâlâ kayıt/sonuç yoksa "bölüm çıkmadı"
EN_COK = 55      # hesap başına gönderilen son bölüm (panel sınırı 120)
PANEL_DURUM = "panel.json"  # {"duraklat": bool, "uygulanan": [komut id]}
FIKIRLER = "panel-fikirler.json"  # panelin "İçerik fikri" kutusundan gelenler: {id: {metin, urun, durum, gun, not, bildirildi}}


def _fikir_al(cevap: dict) -> None:
    f = oku(FIKIRLER, {}) or {}
    for t in cevap.get("tanitimlar") or []:
        if t.get("id") and t["id"] not in f and t.get("urun") in HESAPLAR:
            f[t["id"]] = {"metin": str(t.get("metin") or "")[:300], "urun": t["urun"], "durum": "bekliyor", "gun": None, "not": None, "bildirildi": False}
            gunluk(f"panel: yeni içerik fikri ({t['urun']})")
    yaz(FIKIRLER, f)


def siradaki_fikir(tur: str) -> tuple[str, dict] | None:
    """Bu hesabın en eski bekleyen fikri (gunluk.bolum kullanır)."""
    for fid, x in (oku(FIKIRLER, {}) or {}).items():
        if x.get("urun") == tur and x.get("durum") == "bekliyor":
            return fid, x
    return None


def fikir_sonuc(fid: str, durum: str, gun: str | None = None, not_: str | None = None) -> None:
    f = oku(FIKIRLER, {}) or {}
    if fid in f:
        f[fid].update(durum=durum, gun=gun, **{"not": (not_ or "")[:300] or None}, bildirildi=False)
        yaz(FIKIRLER, f)


def _fikir_bildirimleri() -> list[dict]:
    out = []
    for fid, x in (oku(FIKIRLER, {}) or {}).items():
        if x.get("durum") in ("planlandi", "reddedildi") and not x.get("bildirildi"):
            out.append({"id": fid, "durum": x["durum"], "gun": x.get("gun"), "aciklama": x.get("not"), "neden": x.get("not")})
    return out
HATA_IZI = ("HATA", "kalite denetimi geçmedi", "firma bulunamadı", "yorum/yanıt yazılamadı", "metin üretilemedi")


def saat(tur: str) -> str:
    """Hesabın günlük çalışma saati: önce launchd plist'i, sonra ayarlar.json (hesaplar.<tur>.saat), sonra varsayılan."""
    try:
        with open(pathlib.Path.home() / "Library" / "LaunchAgents" / f"com.mcht.yorumdan-{tur}.plist", "rb") as f:
            c = plistlib.load(f)["StartCalendarInterval"]
        return f"{int(c['Hour']):02d}:{int(c.get('Minute', 0)):02d}"
    except Exception:  # noqa: BLE001
        return str(ayarlar().get("hesaplar", {}).get(tur, {}).get("saat") or VARSAYILAN_SAAT[tur])


def duraklatildi() -> bool:
    try:
        return bool((oku(PANEL_DURUM, {}) or {}).get("duraklat"))
    except Exception:  # noqa: BLE001  # bozuk dosya hattı durdurmasın
        return False


def _gun_saat(tarih: str) -> tuple[str, str]:
    """"20261125-1522" → ("2026-11-25", "15:22")."""
    g, s = tarih.split("-")
    return f"{g[:4]}-{g[4:6]}-{g[6:8]}", f"{s[:2]}:{s[2:4]}"


def _bugun_log(simdi: dt.datetime) -> list[str]:
    f = DURUM / "gunluk.log"
    if not f.exists():
        return []
    on = simdi.strftime("%Y-%m-%d ")
    with open(f, "rb") as h:
        h.seek(max(0, f.stat().st_size - 300_000))
        satirlar = h.read().decode("utf-8", "replace").splitlines()
    return [s for s in satirlar if s.startswith(on)]


def _son_hata(log: list[str], tur: str) -> str | None:
    """Bugün bu hesabın son çalışması bölümsüz bittiyse nedeni (yalnız ilk satır, iz yok)."""
    neden = None
    for s in log:
        m = s[20:]
        if m.startswith(f"{tur}: sonuç {{") or m.startswith(f"{tur}: bugün zaten paylaşıldı"):
            neden = None
        elif m.startswith(f"{tur}:") and any(x in m for x in HATA_IZI):
            neden = m[len(tur) + 2:].replace(str(KOK) + "/", "")[:280]
        elif m.startswith(f"{tur}: sonuç yok") and neden is None:
            neden = "bölüm çıkmadı (ayrıntı günlükte)"
    return neden


def _ek_platformlar(k: dict) -> list[dict]:
    """Aynı video Facebook Reels ve YouTube Shorts'a da gider. Yalnız sonucu KAYITLI olan gösterilir (bilinmeyen platform uydurulmaz)."""
    out = []
    for anahtar, ad, lk, hk in (("facebook", "Facebook Reels", "fb_link", "fb_hata"), ("youtube", "YouTube Shorts", "yt_link", "yt_hata")):
        if str(k.get(lk) or "").startswith("https://"):
            out.append({"anahtar": anahtar, "ad": ad, "durum": "paylasildi", "link": k[lk]})
        elif k.get(hk):
            out.append({"anahtar": anahtar, "ad": ad, "durum": "hata", "link": None, "not": _hata_sinifi(k[hk])})
    return out


def _hata_sinifi(m: str) -> str:
    m = (m or "").lower()
    if "(#200)" in m or "permission" in m:
        return "İzin eksik: sayfa anahtarında paylaşım izni yok"
    if "(#190)" in m or "access token" in m or "session has expired" in m:
        return "Meta anahtarı geçersiz ya da süresi dolmuş"
    if "invalid_grant" in m or "expired or revoked" in m:
        return "YouTube yetkisi iptal edilmiş ya da süresi dolmuş"
    if "anahtar" in m and "yok" in m:
        return "Anahtar tanımlı değil"
    return "Paylaşım başarısız (ayrıntı günlükte)"


DURUM_AD = {"iyi": "Bütçe rahat", "orta": "Bütçe dengede", "dar": "Bütçe dar", "acik": "Bütçe açık veriyor"}


def _bolum(tur: str, k: dict, ig: str) -> dict:
    if tur == "para" and k.get("bicim") == "kapisma":
        tl_ = lambda v: f"{int(v or 0):,}".replace(",", ".") + " ₺"  # noqa: E731
        k = {**k, "firma": f"{tl_(k.get('maas'))} vs {tl_(k.get('maas_b'))}", "sektor": "Maaş Kapışması", "_on": "para-k"}
    elif tur == "para" and k.get("bicim") == "aliskanlik":   # öğlen biçimi: alışkanlık + yıllık tutar
        k = {**k, "firma": f"{k.get('ne') or 'Alışkanlık'} · yılda " + f"{int(k.get('yil') or 0):,}".replace(",", ".") + " ₺", "sektor": "Yılda Kaça Patlıyor?",
             "_on": "para-a"}
    elif tur == "para":   # Cüzdan Hocası: "firma" yerine maaş, "sektör" yerine bütçe durumu gösterilir
        k = {**k, "firma": f"{int(k.get('maas') or 0):,}".replace(",", ".") + " ₺ maaş bütçesi", "sektor": DURUM_AD.get(k.get("durum"), "Bütçe")}
    gun, saat_ = _gun_saat(str(k.get("tarih") or "00000000-0000"))
    link = k.get("link") if str(k.get("link") or "").startswith("https://") else None
    yayinda = bool(k.get("medya_id"))
    return {
        "id": f"{k.get('_on') or tur}-{k.get('tarih')}", "gun": gun, "saat": saat_, "baslik": k.get("firma") or "?", "bolum_no": k.get("gun"),
        "sektor": str(k.get("sektor") or "")[:40], "konu": f"@{ig}", "durum": "yayinlandi" if yayinda else "uretildi",
        "platformlar": [{"anahtar": "instagram", "ad": "Instagram Reels", "durum": "paylasildi" if yayinda else "bekliyor", "link": link},
                        *_ek_platformlar(k)],
        "satirlar": [], "duzenlenebilir": False, "kilit_nedeni": "Bu hat panelden düzenlenmez.",
        "yorumdan": {"hesap": tur, "ig_kullanici": ig, "firma": k.get("firma"), "sektor": k.get("sektor"), "gun_no": k.get("gun"),
                     "yildiz": k.get("yildiz"), "video": pathlib.Path(str(k.get("video") or "")).name or None, "kaynak": k.get("kaynak"),
                     "kullanici": k.get("kullanici") or None, "medya_id": str(k["medya_id"]) if k.get("medya_id") else None,
                     "senaryo_kaynak": k.get("senaryo_kaynak")},
    }


def _plan(tur: str, ig: str, gun: dt.date, saat_: str, durum: str, hata: str | None = None) -> dict:
    return {
        "id": f"{tur}-{gun:%Y%m%d}-plan", "gun": gun.isoformat(), "saat": saat_, "baslik": "Yorumlardan seçilecek maaş" if tur == "para" else "Yorumlardan seçilecek firma", "bolum_no": None,
        "sektor": "", "konu": f"@{ig}", "durum": durum,
        "platformlar": [{"anahtar": "instagram", "ad": "Instagram Reels", "durum": "hata" if durum == "hata" else "bekliyor", "link": None},
                        *([{"anahtar": "facebook", "ad": "Facebook Reels", "durum": "bekliyor", "link": None}] if ayarlar().get("facebook_reels", True) else []),
                        *([{"anahtar": "youtube", "ad": "YouTube Shorts", "durum": "bekliyor", "link": None}] if ayarlar().get("youtube", True) else [])],
        "satirlar": [], "duzenlenebilir": False, "kilit_nedeni": "Bu hat panelden düzenlenmez.",
        "yorumdan": {"hesap": tur, "ig_kullanici": ig, "firma": "", "sektor": "", "hata": hata},
    }


def ozet(simdi: dt.datetime | None = None) -> dict:
    simdi = simdi or dt.datetime.now(TR)
    ay = ayarlar()
    canli = ay.get("mod") == "canli"
    durak = duraklatildi()
    log = _bugun_log(simdi)
    bolumler, hesaplar, uyarilar = [], {}, []
    for tur in HESAPLAR:
        h = ay.get("hesaplar", {}).get(tur, {})
        ig = h.get("ig_kullanici") or tur
        s = saat(tur)
        hesaplar[tur] = {"aktif": bool(h.get("aktif")), "ig_kullanici": ig, "saat": s}
        kayit = [k for k in (oku(f"{tur}-bolumler.json", []) or []) if isinstance(k, dict) and k.get("tarih")]
        bolumler += [_bolum(tur, k, ig) for k in kayit[-EN_COK:]]
        if not (h.get("aktif") and canli and not durak):
            continue
        bugun_var = any(str(k["tarih"]).startswith(f"{simdi:%Y%m%d}") and k.get("medya_id") for k in kayit)
        hh, mm = map(int, s.split(":"))
        calisma = simdi.replace(hour=hh, minute=mm, second=0, microsecond=0)
        hata = _son_hata(log, tur)
        if not bugun_var:
            if simdi < calisma:  # günün çalışması henüz gelmedi (önceki elle deneme hatası sayılmaz)
                bolumler.append(_plan(tur, ig, simdi.date(), s, "sirada"))
            elif hata:
                bolumler.append(_plan(tur, ig, simdi.date(), s, "hata", hata))
                uyarilar.append(f"@{ig}: bugün bölüm çıkmadı — {hata}")
            elif simdi > calisma + dt.timedelta(minutes=GECIKME_DK):
                bolumler.append(_plan(tur, ig, simdi.date(), s, "hata", "Bulut zamanlayıcısı bu saatte başlatmadı; panelde Düzelt ile yeniden başlatılabilir."))
                uyarilar.append(f"@{ig}: bugünkü {s} çalışması yapılmadı (bulut zamanlayıcısı başlatmadı).")
            else:  # çalışma sürüyor
                bolumler.append(_plan(tur, ig, simdi.date(), s, "sirada"))
        bolumler.append(_plan(tur, ig, simdi.date() + dt.timedelta(days=1), s, "sirada"))
        if tur == "para":   # öğlen biçimi (12:30, Yılda Kaça Patlıyor?) ayrı kayıt dosyasında
            for dosya, bic, a_saat, ek, bas, sek in (("para-aliskanlik-bolumler.json", "aliskanlik", "12:30", "-a", "Yorumlardan seçilecek alışkanlık", "Yılda Kaça Patlıyor?"),
                                                    ("para-kapisma-bolumler.json", "kapisma", "17:30", "-k", "Yorumlardan seçilecek iki maaş", "Maaş Kapışması")):
                ka = [k for k in (oku(dosya, []) or []) if isinstance(k, dict) and k.get("tarih")]
                bolumler += [_bolum(tur, {**k, "bicim": bic}, ig) for k in ka[-EN_COK:]]
                ah, am = map(int, a_saat.split(":"))
                a_var = any(str(k["tarih"]).startswith(f"{simdi:%Y%m%d}") and k.get("medya_id") for k in ka)
                for gun_ in (simdi.date(), simdi.date() + dt.timedelta(days=1)):
                    if gun_ == simdi.date() and (a_var or simdi > simdi.replace(hour=ah, minute=am) + dt.timedelta(minutes=GECIKME_DK)):
                        continue
                    pl = _plan(tur, ig, gun_, a_saat, "sirada"); pl["id"] += ek; pl["baslik"] = bas; pl["sektor"] = sek
                    bolumler.append(pl)
    if any("günlük kota doldu" in x for x in log):
        uyarilar.append("Gemini bugün ücretsiz kotaya takıldı; yedek modeller denendi.")
    # Yapay zekâ kota rozeti (2026-11-27): panel tablosunda her hesabın satırında "Yapay zekâ" (rakam/anahtar yok)
    doldu, groq_ok, groq_bitti = (any("günlük kota doldu" in x for x in log), any("ile yazıldı (Gemini yoktu)" in x for x in log),
                                  any("Groq ücretsiz kotası doldu" in x for x in log))
    z = simdi.isoformat(timespec="seconds")
    if doldu and groq_bitti:
        kr = {"durum": "hata", "zaman": z, "mesaj": "Bugünkü ücretsiz metin kotası (Gemini + Groq yedeği) bitti; 11:00'de yenilenir"}
    elif doldu:
        kr = {"durum": "tamam", "zaman": z, "mesaj": "Gemini'nin bazı modelleri günlük kotaya takıldı; " + ("Groq yedeği yazdı" if groq_ok else "diğer modeller çalışıyor")}
    else:
        kr = {"durum": "tamam", "zaman": z, "mesaj": "Ücretsiz kota yeterli"}
    return {"bolumler": bolumler[-120:], "ekler": {"baglanti": {t: {"gemini": kr} for t in ("kartvizit", "web", "para")}, "yorumdan": {
        "ayarlar": {"duraklat": durak, "mod": "canli" if canli else "deneme", "hesaplar": hesaplar},
        "uyarilar": uyarilar[:12], "zaman": simdi.isoformat(timespec="seconds")}}}


def _istek(yol: str, govde: dict) -> dict:
    veri = json.dumps(govde, ensure_ascii=False).encode()
    zaman = str(int(time.time() * 1000))
    imza = hmac.new(ANAHTAR.read_bytes().strip(), zaman.encode() + b"." + veri, hashlib.sha256).hexdigest()
    req = urllib.request.Request(PANEL + yol, data=veri, method="POST", headers={
        "Content-Type": "application/json", "X-Requested-With": "ajans-web", "User-Agent": "yorumdan-hat/1",
        "X-Muhit-Zaman": zaman, "X-Muhit-Imza": imza})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read() or b"{}")


def _komutlar(cevap: dict) -> tuple[list[str], list[dict]]:
    """duraklat/devam uygulanır (sırayla; sonuncusu geçerli); "duzelt" senkron()'da ayrıca işlenir. Diğerleri bu hatta yok → reddedilir."""
    d = oku(PANEL_DURUM, {}) or {}
    yapilan = set(d.get("uygulanan") or [])
    uygulanan, reddedilen = [], []
    for c in cevap.get("komutlar") or []:
        cid = str(c.get("id") or "")
        if not cid:
            continue
        if c.get("tur") == "duzelt":
            continue  # senkron() ayrıca işler (adım adım rapor)
        if c.get("tur") in ("duraklat", "devam"):
            if cid not in yapilan:
                d["duraklat"] = c["tur"] == "duraklat"
                gunluk(f"panel: hat {'DURAKLATILDI' if d['duraklat'] else 'devam ettiriliyor'} ({c.get('kullanici', '')})")
            uygulanan.append(cid)
        else:
            reddedilen.append({"id": cid, "neden": "Bu hat yalnız duraklat/devam alır."})
    for x in cevap.get("duzenlemeler") or []:
        reddedilen.append({"id": str(x.get("id")), "neden": "Bu hat panelden düzenlenmez."})
    if uygulanan:
        d["uygulanan"] = sorted(yapilan | set(uygulanan))[-200:]
        yaz(PANEL_DURUM, d)
    return uygulanan, reddedilen


META_ANAHTAR = {"ad": "Meta sayfa/sistem kullanıcısı iznini kontrol et", "link": "https://business.facebook.com/settings/system-users"}
YT_YETKI = {"ad": "YouTube kanal yetkisini kontrol et", "link": "https://myaccount.google.com/connections"}


def _calisiyor_mu(tur: str) -> bool:
    import subprocess
    return subprocess.run(["pgrep", "-f", f"gunluk.py --hesap {tur}"], capture_output=True).returncode == 0


def duzelt_uygula(tur: str | None, simdi: dt.datetime | None = None) -> dict:
    """Panel "Düzelt": Instagram/YouTube bağlantısını OKUYARAK denetler; bugünkü videoda kesin hata almış Facebook/YouTube paylaşımını
    yeniden gönderir; günün çalışması hiç olmadıysa (Mac uykudaydı vb.) yeniden başlatır (hattın 'bugün zaten paylaşıldı' kapısı çift
    paylaşımı önler). Instagram'a gitmiş videoyu Instagram'a yeniden GÖNDERMEZ."""
    import subprocess
    import sys
    from instagram import Instagram, facebook_reels, youtube_shorts
    simdi = simdi or dt.datetime.now(TR)
    if tur not in HESAPLAR:
        return {"durum": "sorun", "adimlar": [{"ad": "Hesap", "durum": "hata", "mesaj": "Bu hat yalnız Kartvizitçi, Siteci Abi ve Cüzdan Hocası hesaplarını yönetir."}], "eylemler": []}
    ay = ayarlar()
    h = ay.get("hesaplar", {}).get(tur, {})
    adimlar, eylemler = [], []
    try:
        Instagram(tur).son_medyalar(1)
        adimlar.append({"ad": "Instagram bağlantısı", "durum": "tamam", "mesaj": "Hesap okunabiliyor"})
    except Exception as e:  # noqa: BLE001
        adimlar.append({"ad": "Instagram bağlantısı", "durum": "hata", "mesaj": _hata_sinifi(str(e))})
        eylemler.append(META_ANAHTAR)
    if ay.get("youtube", True):
        import requests
        try:
            r = requests.post("https://oauth2.googleapis.com/token", timeout=30, data={
                "client_id": env("YT_CLIENT_ID"), "client_secret": env("YT_CLIENT_SECRET"), "refresh_token": env("YT_REFRESH_TOKEN"),
                "grant_type": "refresh_token"})
            ok = r.ok and "access_token" in r.json()
            adimlar.append({"ad": "YouTube bağlantısı", "durum": "tamam" if ok else "hata", "mesaj": "Yetki geçerli" if ok else _hata_sinifi(r.text)})
            if not ok:
                eylemler.append(YT_YETKI)
        except Exception as e:  # noqa: BLE001
            adimlar.append({"ad": "YouTube bağlantısı", "durum": "hata", "mesaj": _hata_sinifi(str(e))})
    kd = f"{tur}-bolumler.json"
    kayit = oku(kd, []) or []
    bugun = [k for k in kayit if str(k.get("tarih", "")).startswith(f"{simdi:%Y%m%d}") and k.get("medya_id")]
    if bugun:
        k = bugun[-1]
        video = pathlib.Path(str(k.get("video") or ""))
        video = video if video.is_absolute() else KOK / video
        metin = video.with_suffix(".txt").read_text() if video.with_suffix(".txt").exists() else ""
        for anahtar, ad, lk, hk, acik, fn in (
                ("facebook", "Facebook Reels", "fb_link", "fb_hata", ay.get("facebook_reels", True), lambda: facebook_reels(tur, video, metin)),
                ("youtube", "YouTube Shorts", "yt_link", "yt_hata", ay.get("youtube", True), lambda: youtube_shorts(tur, video, metin, h.get("ig_kullanici", "")))):
            if not acik or k.get(lk) or not k.get(hk):
                continue
            if not video.exists() or not metin:
                adimlar.append({"ad": f"{ad} yeniden gönderme", "durum": "hata", "mesaj": "Video ya da açıklama dosyası bulunamadı"})
                continue
            try:
                k[lk] = fn()
                k.pop(hk, None)
                adimlar.append({"ad": f"{ad} yeniden gönderildi", "durum": "tamam", "mesaj": None})
            except Exception as e:  # noqa: BLE001
                k[hk] = str(e)[:200]
                adimlar.append({"ad": f"{ad} hâlâ gönderilemiyor", "durum": "hata", "mesaj": _hata_sinifi(str(e))})
                if anahtar == "facebook" and META_ANAHTAR not in eylemler:
                    eylemler.append(META_ANAHTAR)
        yaz(kd, kayit)
        if not any(a["ad"].endswith(("gönderildi", "gönderilemiyor")) for a in adimlar):
            adimlar.append({"ad": "Bugünkü bölüm", "durum": "tamam", "mesaj": "Yayında; yeniden gönderilecek hata yok."})
    else:
        hh, mm = map(int, saat(tur).split(":"))
        calisma = simdi.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if simdi < calisma:
            adimlar.append({"ad": "Bugünkü bölüm", "durum": "bilgi", "mesaj": f"Saati ({saat(tur)}) gelmedi; zamanında hat kendisi çalışır."})
        elif duraklatildi():
            adimlar.append({"ad": "Bugünkü bölüm", "durum": "uyari", "mesaj": "Hat panelden duraklatılmış; 'Devam' verilmeden çalışmaz."})
        elif _calisiyor_mu(tur):
            adimlar.append({"ad": "Bugünkü bölüm", "durum": "bilgi", "mesaj": "Hat şu an çalışıyor; sonuç birkaç dakika içinde tabloda."})
        else:
            import os
            if os.environ.get("GITHUB_ACTIONS"):   # bulutta: günlük iş akışını yeniden tetikle (GITHUB_TOKEN, actions: write)
                import requests
                bic = "butce" if tur == "para" else "butce"
                r_ = requests.post(f"https://api.github.com/repos/{os.environ.get('GITHUB_REPOSITORY')}/actions/workflows/gunluk.yml/dispatches", timeout=30,
                                   headers={"Authorization": f"Bearer {os.environ.get('GITHUB_TOKEN', '')}", "Accept": "application/vnd.github+json"},
                                   json={"ref": "main", "inputs": {"hesap": tur, "bicim": bic, "deneme": "false"}})
                if r_.status_code >= 300:
                    raise RuntimeError(f"bulut tetiklenemedi {r_.status_code}")
            else:
                ortam = {**os.environ, "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:" + os.environ.get("PATH", "")}  # npx/ffmpeg (launchd PATH dar)
                subprocess.Popen([sys.executable, str(KOK / "hat" / "gunluk.py"), "--hesap", tur], cwd=str(KOK), start_new_session=True, env=ortam,
                                 stdout=open(DURUM / "launchd.log", "a"), stderr=subprocess.STDOUT)
            gunluk(f"panel Düzelt: {tur} günlük çalışması yeniden başlatıldı")
            adimlar.append({"ad": "Bugünkü bölüm yeniden başlatıldı", "durum": "tamam",
                            "mesaj": "Günün çalışması yapılmamıştı; şimdi başladı (çift paylaşım kapısı açık). Sonuç ~15 dk içinde tabloda."})
    return {"durum": "sorun" if any(a["durum"] == "hata" for a in adimlar) else "tamam", "adimlar": adimlar, "eylemler": eylemler}


def senkron() -> dict:
    """Panelle bir tur: özet gönder, iş emirlerini uygula, sonucu bildir. ASLA hata fırlatmaz."""
    try:
        if not ANAHTAR.exists():
            gunluk("panel: hat/.panel_anahtari yok, senkron atlandı")
            return {"atlandi": "anahtar yok"}
        cevap = _istek("", ozet())
        _fikir_al(cevap)
        uygulanan, reddedilen = _komutlar(cevap)
        duzelt = []
        for c in cevap.get("komutlar") or []:
            if c.get("tur") == "duzelt" and c.get("id"):
                _istek("/onay", {"duzelt": [{"id": c["id"], "durum": "calisiyor", "adimlar": [{"ad": "Hat çalışıyor", "durum": "bilgi", "mesaj": "Bağlantılar denetleniyor"}]}]})
                try:
                    duzelt.append({"id": c["id"], **duzelt_uygula((c.get("deger") or {}).get("marka"))})
                except Exception as e:  # noqa: BLE001
                    duzelt.append({"id": c["id"], "durum": "sorun", "adimlar": [{"ad": "Düzeltme yarıda kaldı", "durum": "hata", "mesaj": type(e).__name__}]})
                uygulanan.append(c["id"])
        fikir = _fikir_bildirimleri()
        if uygulanan or reddedilen or fikir:
            _istek("/onay", {"uygulanan": uygulanan, "reddedilen": reddedilen, "tanitim": fikir, "duzelt": duzelt})
            if fikir:
                f = oku(FIKIRLER, {}) or {}
                for x in fikir:
                    f[x["id"]]["bildirildi"] = True
                yaz(FIKIRLER, f)
            _istek("", ozet())  # panel yeni hâli (duraklat) hemen görsün
        return {"gonderildi": True, "uygulanan": len(uygulanan), "reddedilen": len(reddedilen), "duraklat": duraklatildi()}
    except Exception as e:  # noqa: BLE001
        try:
            ayrinti = f"HTTP {e.code} {e.read()[:200].decode('utf-8', 'replace')}" if isinstance(e, urllib.error.HTTPError) else f"{type(e).__name__}: {str(e)[:200]}"
        except Exception:  # noqa: BLE001
            ayrinti = type(e).__name__
        try:
            gunluk(f"panel: senkron olmadı {ayrinti}")
        except Exception:  # noqa: BLE001
            pass
    return {"gonderildi": False}


if __name__ == "__main__":
    from ortak import durum_esitle
    durum_esitle("al")      # Mac'te 10 dk'da bir: buluttaki (GitHub Actions) son bölümleri de panele taşı
    print(json.dumps(senkron(), ensure_ascii=False))
    durum_esitle("ver")     # panelden gelen içerik fikri / duraklat komutu bulut çalışmasına da ulaşsın
