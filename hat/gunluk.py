"""Günlük otomatik bölüm: yorum topla → firma seç → yıldız seç → senaryo → video → denetim → paylaş → kayıt.
Kullanım:
  .venv/bin/python hat/gunluk.py                 # ayarlar.json'daki moda göre iki hesap
  .venv/bin/python hat/gunluk.py --hesap web --deneme   # örnek yorumlarla, paylaşmadan
Hiçbir adım insan onayı beklemez; bir hesapta hata olursa o hesap atlanır, diğeri sürer (günlük.log)."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import subprocess
import traceback

import kartvizit
import panel
import platform_ayar
import radar
from guvenlik import uygunsuz
import sec
import senaryo
import web
import yorumlar
from instagram import Instagram
from ortak import CIKTI, ICERIK, IS, ayarlar, env, gunluk, json_sor, oku, sure, yaz


def kalite(video, beklenen: float) -> list[str]:
    """Teslimden önce: süre, ses seviyesi, sondaki parazit (cızırtı) denetimi."""
    import numpy as np
    sorun = []
    s = sure(video)
    if abs(s - beklenen) > 1.0 or not 25 <= s <= 75:
        sorun.append(f"süre {s:.1f} sn")
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(video), "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True).stderr
    try:
        I = float(r.split("I:")[-1].split("LUFS")[0]); tp = float(r.split("Peak:")[-1].split("dBFS")[0])
        if not -16.5 <= I <= -12.5: sorun.append(f"ses seviyesi {I} LUFS")
        if tp > -0.3: sorun.append(f"tepe {tp} dBFS")
    except Exception:  # noqa: BLE001
        sorun.append("ses ölçülemedi")
    ham = subprocess.run(["ffmpeg", "-v", "error", "-sseof", "-3", "-i", str(video), "-f", "s16le", "-ac", "1", "-ar", "48000", "-"], capture_output=True).stdout
    a = np.frombuffer(ham, np.int16).astype(float) / 32768
    db = [20 * np.log10(np.sqrt(np.mean(a[i:i + 960] ** 2)) + 1e-9) for i in range(0, len(a) - 960, 960)]
    son1 = db[-50:]   # yalnız son 1 sn: kapanıştaki doğal konuşma girişleri parazit sayılmasın
    if any(son1[i] - son1[i - 1] > 25 and son1[i] > -20 for i in range(1, len(son1))) or (db and max(db[-5:]) > -45):
        sorun.append("sonda ani ses sıçraması / kuyruk paraziti")
    return sorun


def aciklama(tur: str, s: dict, firma: dict, ek: str = "") -> str:
    etk = " ".join([x if x.startswith("#") else "#" + x for x in s.get("etiketler", [])][:5])
    alt = ayarlar()["ilk_yorum"]
    soru = (s.get("soru") or "").strip() or ("Mat mı parlak mı?" if tur == "kartvizit" else "Koyu tema mı açık tema mı?")
    kaydet = ("📌 Kaydet: kendi kartvizitini yaptırırken bu ayrıntılar işine yarar." if tur == "kartvizit"
              else "📌 Kaydet: kendi siteni yaptırırken bu bölümleri unutma.")
    parcalar = [s.get("aciklama", "").strip(), "", f"🤔 {soru} Yorumlara tek kelime yaz 👇", kaydet, "", f"💬 {alt}"]
    if firma.get("kaynak") == "yorum" and firma.get("kullanici"):
        parcalar.append(f"Bugünün firması: @{firma['kullanici']} (yorumuyla seçildi, {firma['begeni']} beğeni)")
    if tur == "web":   # kullanıcı: Siteci Abi'nin her paylaşımında Site Mucidi etiketlensin
        parcalar.append("🛠 Bu site @sitemucidi ile yapıldı; kendi siteni sen de birkaç dakikada oluşturabilirsin.")
    parcalar.append("Vitrin tasarımıdır; firma isterse satın alabilir.")
    parcalar.append("Esnaf bir arkadaşın varsa bu videoyu ona gönder; sıradaki onun firması olabilir.")
    if ek:
        parcalar.append(ek)
    if ayarlar().get("ai_etiketi"):
        parcalar.append("Seslendirme yapay zekâ ile yapılmıştır.")
    parcalar += ["", etk]
    return "\n".join(parcalar)[:2150]


RADAR = {"kartvizit": {"hesaplar": ["kartvizitci", "baskiburada", "davetiyeci"], "yt": ["kartvizit tasarımı", "matbaa baskı", "esnaf reklam fikri"], "marka": "Kartvizitçi (@kartvizitci.tr)",
                       "kitle": "Türkiye'deki esnaf ve küçük işletme sahipleri", "konu": "kartvizit, matbaa ve esnaf tanıtımı"},
         "web": {"hesaplar": ["syncoretr", "ikas", "ideasoft", "ticimax"], "yt": ["esnaf web sitesi", "web tasarım", "google haritalar işletme"], "marka": "Siteci Abi (@siteci.abi) / Site Mucidi",
                 "kitle": "web sitesi olmayan esnaf ve küçük işletmeler", "konu": "web sitesi, e-ticaret ve esnafın dijitalleşmesi"}}


def radar_metni(tur: str) -> str:
    """Rakip + trend radarı; 3 günde bir yenilenir (kota), hata hattı durdurmaz."""
    ad = f"radar-{tur}.json"
    o = oku(ad, {}) or {}
    if o.get("tarih", "") < (dt.date.today() - dt.timedelta(days=3)).isoformat():
        try:
            pre = "IG_KARTVIZIT" if tur == "kartvizit" else "IG_WEB"
            ig_id, tok = env(f"{pre}_ID"), env(f"{pre}_TOKEN")
            c = RADAR[tur]
            hs = [h for h in (radar.hesap_oku(ig_id, tok, u) for u in c["hesaplar"]) if h]
            tt = radar.ara(env("GEMINI_API_KEY"), radar.TIKTOK_SORU.format(tarih=dt.date.today().isoformat(), konu=c["konu"]))
            yt = radar.yt_trend(radar.yt_erisim(env("YT_CLIENT_ID"), env("YT_CLIENT_SECRET"), env("YT_REFRESH_TOKEN")), c["yt"])
            yeni = radar.ozet(lambda i: json_sor("Sadece JSON döndür.", i, 0.4), c["marka"], c["kitle"], radar.tutanlar(hs) + yt, tt)
            if yeni:
                o = yeni; yaz(ad, o)
                gunluk(f"{tur}: radar yenilendi ({len(hs)} Instagram hesabı, {len(yt)} YouTube Shorts, arama {'var' if tt else 'yok'})")
        except Exception as e:  # noqa: BLE001
            gunluk(f"{tur}: radar yenilenemedi: {e}")
    import gundem_notu  # doğrulanmış, tarihli gündem (2026-11-27): haftada 3 gün, süresi geçen düşer
    g = gundem_notu.metin(ICERIK / "gundem" / f"{tur}.json")
    return radar.yazar_metni(o) + (("\n\n" + g) if g else "")


def _ara_kaydet(kd: str, kayit: list, satir: dict) -> None:
    """Bir platform sonucu (bağlantı / belirsiz) alınır alınmaz kayda yazar ve durum deposuna gönderir: sonraki adımlar çökse ya da
    süreç öldürülse bile bir sonraki koşu "bugün zaten paylaşıldı" kapısında durur, aynı videoyu ikinci kez paylaşmaz."""
    yaz(kd, kayit + [satir])
    try:
        from ortak import durum_esitle
        durum_esitle("ver")
    except Exception as e:  # noqa: BLE001  (yerel dosya yazıldı; push sonra finally'de yeniden denenir)
        gunluk(f"durum ara kaydı gönderilemedi: {type(e).__name__}")


def _platformlara_paylas(tur: str, kd: str, kayit: list, satir: dict, cikti, metin: str, ortaklar: list[str],
                         fb_acik: bool, yt_acik: bool, ig_kullanici: str) -> dict | None:
    """Instagram Reels → Facebook Reels → YouTube Shorts. Panelde kapalı platform atlanır. Her sonuç anında kalıcı kaydedilir.
    Instagram kesin hata (yayından önce) → istisna yükselir, kayıt yazılmaz, sonraki koşu yeniden dener.
    İstek gittikten sonra yanıtsızlık (BelirsizYayin) → *_belirsiz yazılır; günlük koşu da Düzelt de ASLA yeniden göndermez."""
    from instagram import BelirsizYayin, facebook_reels, youtube_shorts
    kapali = platform_ayar.kapalilar(tur)
    if kapali:
        satir["panelde_kapali"] = kapali
        gunluk(f"{tur}: {', '.join(kapali)} → {platform_ayar.NOT}")
    b = None
    if "instagram" not in kapali:
        try:
            b = Instagram(tur).reels(cikti, metin, ortaklar=ortaklar)
            satir.update({"medya_id": b["id"], "link": b.get("permalink")})
        except BelirsizYayin as e:
            gunluk(f"{tur}: Instagram Reels BELİRSİZ, elle kontrol (otomatik yeniden paylaşılmaz): {e}")
            satir.update(ig_belirsiz=str(e)[:200], yayin_denendi=True)
        _ara_kaydet(kd, kayit, satir)
    else:
        satir["yayin_denendi"] = True   # Instagram kapalı: Facebook/YouTube denemesi de "bugün zaten paylaşıldı" kapısını kapatır
    for anahtar, ad, acik_, lk, hk, bk, fn in (
            ("facebook", "Facebook Reels", fb_acik, "fb_link", "fb_hata", "fb_belirsiz", lambda: facebook_reels(tur, cikti, metin)),
            ("youtube", "YouTube Shorts", yt_acik, "yt_link", "yt_hata", "yt_belirsiz", lambda: youtube_shorts(tur, cikti, metin, ig_kullanici))):
        if not acik_ or anahtar in kapali:
            continue
        try:
            satir[lk] = fn()
        except BelirsizYayin as e:   # gitmiş olabilir: Düzelt bunu yeniden göndermez
            gunluk(f"{tur}: {ad} BELİRSİZ, elle kontrol (otomatik yeniden paylaşılmaz): {e}")
            satir[bk] = str(e)[:200]
        except Exception as e:  # noqa: BLE001  (kesin hata: panel nedeni gösterir, "Düzelt" yeniden dener; IG paylaşımını bozmaz)
            gunluk(f"{tur}: {ad} paylaşılamadı: {e}")
            satir[hk] = str(e)[:200]
        _ara_kaydet(kd, kayit, satir)
    return b


def bolum_para(deneme: bool, bicim: str = "butce") -> dict | None:
    """Cüzdan Hocası: butce (20:30) = yorumdan maaş/kira → bütçe planı; aliskanlik (12:30) = yorumdan alışkanlık → yıllık hesap.
    Bütün tutarları kod hesaplar → anlatımlı maskot videosu → paylaş."""
    import aliskanlik
    import butce
    import karsilastirma
    import para
    ay = ayarlar(); h = ay["hesaplar"]["para"]; tur = "para"
    canli = ay["mod"] == "canli" and not deneme
    kd = f"{'deneme-' if not canli else ''}{ {'butce': 'para-bolumler.json', 'aliskanlik': aliskanlik.KAYIT, 'kapisma': karsilastirma.KAYIT}[bicim] }"
    kayit = oku(kd, [])
    if canli and any(platform_ayar.paylasildi(k) and k.get("tarih", "").startswith(dt.datetime.now().strftime("%Y%m%d")) for k in kayit):
        gunluk("para: bugün zaten paylaşıldı, atlandı"); return None
    if canli and len(platform_ayar.kapalilar(tur)) == len(platform_ayar.PLATFORMLAR):
        gunluk("para: panelde tüm platformlar kapalı, bugün bölüm üretilmedi"); return None
    gun = len([k for k in kayit if platform_ayar.paylasildi(k) or deneme or not canli]) + 1
    ig = Instagram(tur)
    ylar = []
    if not deneme and ig.hazir:   # bu biçimin son videosunun yorumları (yoksa hesabın son Reels'i)
        son_m = next((x.get("medya_id") for x in reversed(kayit) if x.get("medya_id")), None)
        if not son_m:
            sm = [m for m in ig.son_medyalar(5) if m.get("media_type") in ("VIDEO", "REELS")]
            son_m = sm[0]["id"] if sm else None
        ylar = ig.yorumlar(son_m) if son_m else []
        gunluk(f"para/{bicim}: {len(ylar)} yorum ({son_m})")
    tarih = dt.datetime.now().strftime("%Y%m%d-%H%M")
    on = {"butce": "para", "aliskanlik": "para-aliskanlik", "kapisma": "para-kapisma"}[bicim]
    is_dir = IS / f"{on}-{tarih}"; cikti = CIKTI / f"{on}-gun{gun:03d}-{tarih}.mp4"
    if bicim == "butce":
        k = para.sec(ylar, h.get("ig_kullanici", ""))
        p = butce.plan(k["maas"], k.get("kira"), k.get("konut", "kira"), k.get("hane", "bekar"), int(k.get("cocuk") or 0), int(k.get("borc") or 0))
        s = para.yaz_senaryo(k, p, gun)
        r = para.yap(k, p, s, gun, is_dir, cikti)
    elif bicim == "kapisma":
        if not ylar and not deneme and ig.hazir:   # kapışma maaş yorumlarını akşam bütçe videosundan da toplar
            sb = next((x.get("medya_id") for x in reversed(oku("para-bolumler.json", [])) if x.get("medya_id")), None)
            ylar = ig.yorumlar(sb) if sb else []
        ka, kb = karsilastirma.sec(ylar, h.get("ig_kullanici", ""))
        pa, pb = karsilastirma._plan(ka), karsilastirma._plan(kb)
        s = karsilastirma.yaz_senaryo(ka, kb, pa, pb, gun)
        r = para.yap(ka, None, s, gun, is_dir, cikti, karsilastirma.gorsel(ka, kb, pa, pb, s, gun))
        k, p = {**ka, "yorum_id": ka.get("yorum_id"), "_b": kb}, {"durum": f"{pa['durum']}/{pb['durum']}"}
    else:
        k = aliskanlik.sec(ylar, h.get("ig_kullanici", ""))
        p = aliskanlik.hesap(k)
        s = aliskanlik.yaz_senaryo(k, p, gun)
        r = para.yap(k, None, s, gun, is_dir, cikti, aliskanlik.gorsel(k, p, s, gun))
    sorun = kalite(cikti, r["sure"])
    if sorun:
        gunluk(f"para: kalite denetimi geçmedi {sorun} → paylaşılmadı ({cikti})"); return None
    if bicim == "butce":
        metin = para.aciklama(s, k, ay.get("ai_etiketi", True), p)
    elif bicim == "kapisma":
        metin = karsilastirma.aciklama(s, ka, kb, pa, pb, ay.get("ai_etiketi", True))
    else:
        metin = aliskanlik.aciklama(s, k, p, ay.get("ai_etiketi", True))
    kat = uygunsuz(metin, k.get("yorum", ""), *para.metinler(s))
    if kat:
        gunluk(f"para: GÜVENLİK KAPISI ({kat}) → paylaşılmadı ({cikti})"); return None
    cikti.with_suffix(".txt").write_text(metin)
    satir = {"gun": gun, "tarih": tarih, "bicim": bicim, "maas": k.get("maas"), "maas_b": (k.get("_b") or {}).get("maas"), "durum": p.get("durum"), "ne": k.get("ne"), "yil": p.get("yil"), "kaynak": k["kaynak"], "kullanici": k.get("kullanici"),
             "yorum_id": k.get("yorum_id"), "senaryo_kaynak": s.get("_kaynak"), "video": str(cikti), "medya_id": None}
    if canli:
        ig = Instagram(tur)
        b = _platformlara_paylas(tur, kd, kayit, satir, cikti, metin, list(h.get("ortak", [])),
                                 ay.get("facebook_reels", True) and bool(env("META_PARA_PAGE_ID")), ay.get("youtube", True), h.get("ig_kullanici", ""))
        try:
            if b is not None:   # Instagram panelde kapalıysa ilk yorum/yanıt yok (hata değil)
                ig.yorum_yaz(b["id"], {"butce": h.get("ilk_yorum") or para.KAPANIS,
                                       "aliskanlik": "Yarının alışkanlığı bu videonun yorumlarından seçilecek: bir alışkanlığını ve fiyatını yaz. En çok beğeni alan kazanır.",
                                       "kapisma": "Yarının kapışması bu videonun yorumlarından: maaşını, kiranı ve şehrini yaz. En çok beğeni alan iki yorum kapışır."}[bicim])
                if k.get("yorum_id") and k["kaynak"] == "yorum":
                    ig.yanitla(k["yorum_id"], (f"Bütçen hazır: {b.get('permalink') or ''} Kaydet, maaş günü zarfları ayır." if bicim == "butce"
                                               else f"Hesabın hazır: {b.get('permalink') or ''} Yarıya indir, cebinde kalsın."))
        except Exception as ex:  # noqa: BLE001
            gunluk(f"para: yorum/yanıt yazılamadı: {ex}")
        u = oku("para-kullanilan.json", [])
        u += [x for x in (k.get("yorum_id"), (k.get("_b") or {}).get("yorum_id")) if x]
        yaz("para-kullanilan.json", u[-500:])
    else:
        gunluk(f"para: DENEME modu, paylaşılmadı → {cikti}")
    kayit.append(satir); yaz(kd, kayit)
    kc = oku("para-son-kancalar.json", []); kc.append(str(s.get("kanca") or "")[:140]); yaz("para-son-kancalar.json", kc[-20:])
    if s.get("_mizah"):
        an = {"butce": "para", "aliskanlik": "para-aliskanlik", "kapisma": "para-kapisma"}[bicim]
        mz = oku(f"{an}-son-mizah.json", []); mz.append(s["_mizah"]); yaz(f"{an}-son-mizah.json", mz[-10:])
    es = oku("para-son-espriler.json", []); es.append(" | ".join(x for x in (*(s.get("teshis") or [])[1:2], *(s.get("ipucu") or [])[1:2]) if x)); yaz("para-son-espriler.json", es[-20:])
    return satir


def bolum(tur: str, deneme: bool, bicim: str = "butce") -> dict | None:
    if tur == "para":
        return bolum_para(deneme, bicim)
    ay = ayarlar(); h = ay["hesaplar"][tur]
    canli = ay["mod"] == "canli" and not deneme
    kd = f"{'deneme-' if not canli else ''}{tur}-bolumler.json"   # deneme kayıtları gerçek sırayı kirletmez
    kayit = oku(kd, [])
    if canli and any(platform_ayar.paylasildi(k) and k.get("tarih", "").startswith(dt.datetime.now().strftime("%Y%m%d")) for k in kayit):
        gunluk(f"{tur}: bugün zaten paylaşıldı, atlandı"); return None
    if canli and len(platform_ayar.kapalilar(tur)) == len(platform_ayar.PLATFORMLAR):
        gunluk(f"{tur}: panelde tüm platformlar kapalı, bugün bölüm üretilmedi"); return None
    gun = len([k for k in kayit if platform_ayar.paylasildi(k) or deneme or not canli]) + 1
    medya, ylar = yorumlar.topla(tur, deneme=deneme or not Instagram(tur).hazir)
    firma, fikir_id = None, None
    fk = None if deneme else panel.siradaki_fikir(tur)   # panelin "İçerik fikri" kutusu önceliklidir
    if fk:
        f = sec.fikirden(fk[1]["metin"])
        if f and f.get("red"):
            panel.fikir_sonuc(fk[0], "reddedildi", not_=f["red"]); gunluk(f"{tur}: panel fikri reddedildi: {f['red']}")
        elif f:
            firma, fikir_id = f, fk[0]
            gunluk(f"{tur}: günün firması panel fikrinden → {f['firma']} ({f['sektor']})")
    firma = firma or sec.sec(tur, ylar, h.get("ig_kullanici", ""))
    if not firma:
        gunluk(f"{tur}: firma bulunamadı, bugün bölüm yok"); return None
    firma["_radar"] = radar_metni(tur)
    tarih = dt.datetime.now().strftime("%Y%m%d-%H%M")
    is_dir = IS / f"{tur}-{tarih}"; is_dir.mkdir(parents=True, exist_ok=True)
    cikti = CIKTI / f"{tur}-gun{gun:03d}-{tarih}.mp4"
    if tur == "kartvizit":
        yil = senaryo.yildiz_sec(tur, firma["sektor_anahtar"])
        s = senaryo.yaz(tur, firma, gun, yil)
        r = kartvizit.yap(firma, s, gun, yil, is_dir, cikti); ek = ""
    else:
        son_v = [b.get("varyant") for b in kayit[-2:]]   # tasarım çeşidi son 2 bölümde tekrar etmez
        varyant = random.choice([x for x in ("yalin", "vizyon", "prestij") if x not in son_v])
        bilgi = web.site_uret(firma, is_dir / "site0", {"varyant": varyant})
        liste = json.loads((ICERIK / "site-ozellikleri.json").read_text())
        son = [b.get("yildiz") for b in kayit[-7:]]
        uygun = [x for x in liste if x["kod"] in bilgi["bolumler"]] or [x for x in liste if x["kod"] == "hakkimizda"]
        tercih = [x for x in uygun if x["kod"] not in son] or uygun
        yil = next((x for x in tercih if firma["sektor_anahtar"] in x["uygun"]), tercih[0])
        s = senaryo.yaz(tur, firma, gun, yil, web.SEKTOR_AD.get(bilgi["yanlis_sektor"], "başka bir sektör"))
        r = web.yap(firma, s, gun, yil, is_dir, cikti, bilgi)
        ek = "Örnek görseller: Wikimedia Commons (CC BY / CC BY-SA), kaynakları sitemucidi.com.tr/gorsel-kaynaklari" if r.get("fotolar") else ""
    sorun = kalite(cikti, r["sure"])
    if sorun:
        gunluk(f"{tur}: kalite denetimi geçmedi {sorun} → paylaşılmadı ({cikti})")
        return None
    metin = aciklama(tur, s, firma, ek)
    kat = uygunsuz(metin, firma.get("firma", ""), firma.get("yorum", ""), *[c for _, c in senaryo._metinler(tur, s)])
    if kat:  # son kapı: model ne derse desin argo/bahis/kumar/+18 paylaşılmaz
        gunluk(f"{tur}: GÜVENLİK KAPISI ({kat}) → paylaşılmadı ({cikti})")
        if fikir_id:
            panel.fikir_sonuc(fikir_id, "reddedildi", not_=f"İçerik güvenlik kapısından geçmedi ({kat}).")
        return None
    (cikti.with_suffix(".txt")).write_text(metin)
    kayit_satir = {"gun": gun, "tarih": tarih, "firma": firma["firma"], "sektor": firma["sektor"], "yildiz": yil["kod"], "video": str(cikti),
                   "duzen": r.get("duzen"), "arka_mod": r.get("arka_mod"), "rozet": r.get("rozet"), "motif": r.get("motif"), "varyant": r.get("varyant"), "senaryo_kaynak": s.get("_kaynak"), "kaynak": firma["kaynak"], "kullanici": firma.get("kullanici"), "medya_id": None}
    if canli:
        ig = Instagram(tur)
        ortaklar = list(h.get("ortak", []))
        if firma.get("kaynak") == "yorum" and firma.get("kendisi") and firma.get("kullanici"):
            ortaklar = [firma["kullanici"]] + ortaklar
        b = _platformlara_paylas(tur, kd, kayit, kayit_satir, cikti, metin, ortaklar,
                                 ay.get("facebook_reels", True), ay.get("youtube", True), h.get("ig_kullanici", ""))
        try:
            if b is not None:   # Instagram panelde kapalıysa ilk yorum/yanıt yok (hata değil)
                ig.yorum_yaz(b["id"], ay["ilk_yorum"])
                if firma.get("yorum_id"):
                    ig.yanitla(firma["yorum_id"], ay["tebrik"].format(link=b.get("permalink") or ""))
        except Exception as e:  # noqa: BLE001
            gunluk(f"{tur}: yorum/yanıt yazılamadı: {e}")
    else:
        gunluk(f"{tur}: DENEME modu, paylaşılmadı → {cikti}")
    kayit.append(kayit_satir); yaz(kd, kayit)
    if fikir_id:
        panel.fikir_sonuc(fikir_id, "planlandi", gun=dt.date.today().isoformat(), not_=f"{firma['firma']} için {'kartvizit' if tur == 'kartvizit' else 'web sitesi'} bölümü yapıldı")
    if canli:
        sec.kullanildi(firma["firma"])
    if s.get("_mizah"):
        mz = oku(f"{tur}-son-mizah.json", []); mz.append(s["_mizah"]); yaz(f"{tur}-son-mizah.json", mz[-10:])
    es = oku(f"{tur}-son-espriler.json", []); es.append(" | ".join(x for x in (s.get("tanitim"), *(s.get("font") or s.get("kapak") or [])[1:2], *(s.get("perdah") or s.get("ozellik") or [])[1:2]) if x)); yaz(f"{tur}-son-espriler.json", es[-20:])
    return kayit_satir


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hesap", choices=["kartvizit", "web", "para"])
    ap.add_argument("--deneme", action="store_true", help="örnek yorumlarla, paylaşmadan")
    ap.add_argument("--bicim", choices=["butce", "aliskanlik", "kapisma"], default="butce", help="Cüzdan Hocası biçimi (yalnız --hesap para)")
    a = ap.parse_args()
    from ortak import durum_esitle
    durum_esitle("al")
    panel.senkron()  # panelden "duraklat/devam" iş emri varsa önce al (panel düşükse hat yine çalışır)
    if panel.duraklatildi() and not a.deneme:
        gunluk("panelden duraklatıldı: bugün bölüm üretilmedi (panel › İçerik takvimi › Yorumdan Tasarım › Hattı devam ettir)")
        return
    try:
        for tur in ([a.hesap] if a.hesap else ["kartvizit", "web"]):
            if not ayarlar()["hesaplar"].get(tur, {}).get("aktif") and not a.deneme:
                continue
            try:
                r = bolum(tur, a.deneme, a.bicim)
                gunluk(f"{tur}: sonuç {json.dumps(r, ensure_ascii=False) if r else 'yok'}")
            except Exception as e:  # noqa: BLE001
                gunluk(f"{tur}: HATA {e}\n{traceback.format_exc()[-1500:]}")
    finally:
        panel.senkron()  # günün sonucu panelde görünsün; asla hata fırlatmaz
        if not os.environ.get("GITHUB_ACTIONS"):   # radar sonucu Mac'teki ops anahtarıyla sunucuya gider; bulutta atlanır
            try:
                import muhit_radar
                muhit_radar.calistir()  # 3 günde bir; Muhit sunucusuna yalnız sonuç dosyası
            except Exception as e:  # noqa: BLE001
                gunluk(f"muhit radar atlandı: {e}")
        durum_esitle("ver")


if __name__ == "__main__":
    main()
