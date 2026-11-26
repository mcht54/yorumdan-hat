"""Yorumlardan günün firmasını seçer: kural filtreleri → Gemini ile firma/sektör çıkarımı → beğeniye göre puan.
Uygun yorum yoksa icerik/yedek-firmalar.json sırasından devam eder (ilk günler için tohum)."""
from __future__ import annotations

import json
import re

from guvenlik import uygunsuz
from ortak import ICERIK, gunluk, json_sor, normal, oku, yaz

SEKTORLER = ["kurumsal-firma", "sanayi-uretim", "yerel-hizmet", "otomotiv", "restoran-kafe", "saglik-klinik", "dis-klinigi",
             "spor-fitness", "insaat-yapi", "emlak-gayrimenkul", "lojistik", "mobilya-dekorasyon", "hukuk-profesyonel", "danismanlik",
             "guzellik-bakim", "egitim-kurs", "turizm-konaklama", "teknoloji-yazilim", "urun-katalogu", "e-ticaret",
             "etkinlik-organizasyon", "kisisel-portfoy", "taksi", "isitme-merkezi", "okul", "kres-anaokulu", "tesisat", "veteriner",
             "temizlik", "nakliyat"]
YASAK = ["turaklar", "chp", "akp", "mhp", "hdp", "dem parti", "iyi parti", "erdoğan", "kılıçdaroğlu", "bahis", "casino", "kumar",
         "rakı", "bira", "alkol", "tekel bayi", "18+", "escort", "silah", "kripto"]
KUFUR = ["amk", "aq", "oç", "piç", "sik", "orospu", "yarrak", "göt", "salak", "aptal", "gerizekalı", "şerefsiz"]


def _on_eleme(y: dict, kendi: str) -> bool:
    m = normal(y.get("text", ""))
    if not m.strip() or len(m.strip()) < 3 or (y.get("username") or "").lower() == kendi.lower():
        return False
    if "http" in y.get("text", "") or "www." in y.get("text", ""):
        return False
    kelimeler = set(m.split())
    if uygunsuz(y.get("text", ""), y.get("username", "")):  # argo/bahis/kumar/+18: yorum da kullanıcı adı da
        return False
    return not any(k in m for k in YASAK) and not (kelimeler & set(KUFUR))


SISTEM = """Sen bir sosyal medya editörüsün. Instagram yorumlarından, kartvizit ya da web sitesi tasarımı istenen firmaları çıkarırsın.
Her yorum için JSON nesnesi döndür. Kurallar:
- firma: yorumda geçen işletme adı (yazım düzeltmeden, düzgün büyük harfle). Yoksa "".
- sektor: kısa Türkçe sektör adı (ör. "Dönerci", "Kuaför", "Oto lastik"). Yoksa "".
- sehir: geçiyorsa il/ilçe, yoksa "".
- sektor_anahtar: şu listeden en yakını: %s
- kendisi: yorumu yazan kişinin bu işletmenin sahibi/çalışanı olduğu anlaşılıyorsa true ("bizim", "dükkanımız", kullanıcı adı firma adına benziyor vb.).
- uygun: false olmalı eğer: firma/sektör yoksa; ulusal/uluslararası büyük zincir ya da ünlü marka ise (Apple, Migros, THY vb.);
  kamu kurumu, siyasi parti, dernek kavgası; alkol, kumar, yetişkin, silah; başkasının işletmesiyle dalga geçme ya da kötüleme amacı;
  şaka/troll yorumu; kişisel isim (işletme değil); argo/küfür içeren yorum; bahis, iddaa, casino, kumar, +18, escort, onlyfans
  çağrışımı olan HER firma ya da yorum (ör. "XBet", "Casino Bar", "18+ shop") KESİNLİKLE false. Diğer durumlarda true.
- neden: uygun değilse tek cümle.
Sadece JSON döndür: {"adaylar":[{"id":"...","firma":"...","sektor":"...","sehir":"...","sektor_anahtar":"...","kendisi":false,"uygun":true,"neden":""}]}""" % ", ".join(SEKTORLER)


def sec(hesap: str, yorumlar: list[dict], kendi_kullanici: str = "") -> dict | None:
    kullanilan = {normal(f) for f in oku("kullanilan-firmalar.json", [])}
    adaylar = [y for y in yorumlar if _on_eleme(y, kendi_kullanici)]
    adaylar.sort(key=lambda y: (-int(y.get("like_count") or 0), y.get("timestamp", "")))
    adaylar = adaylar[:40]
    secilen = None
    if adaylar:
        istem = "Yorumlar:\n" + "\n".join(json.dumps({"id": y["id"], "kullanici": y.get("username", ""), "metin": y["text"]}, ensure_ascii=False) for y in adaylar)
        try:
            cevap = {a["id"]: a for a in json_sor(SISTEM, istem, 0.2).get("adaylar", [])}
        except Exception as e:  # noqa: BLE001
            gunluk(f"aday çıkarımı yapılamadı: {e}"); cevap = {}
        puanli = []
        for y in adaylar:
            a = cevap.get(y["id"])
            if not a or not a.get("uygun") or not a.get("firma") or not a.get("sektor"):
                continue
            if normal(a["firma"]) in kullanilan or a.get("sektor_anahtar") not in SEKTORLER:
                continue
            if uygunsuz(a["firma"], a.get("sektor", "")):
                gunluk(f"{hesap}: uygunsuz firma/sektör elendi"); continue
            puan = int(y.get("like_count") or 0) + (2 if a.get("kendisi") else 0)
            puanli.append((puan, y, a))
        if puanli:
            puanli.sort(key=lambda p: -p[0])
            p, y, a = puanli[0]
            secilen = {"kaynak": "yorum", "yorum_id": y["id"], "kullanici": y.get("username", ""), "yorum": y["text"],
                       "begeni": int(y.get("like_count") or 0), "firma": a["firma"], "sektor": a["sektor"], "sehir": a.get("sehir", ""),
                       "sektor_anahtar": a["sektor_anahtar"], "kendisi": bool(a.get("kendisi"))}
    if not secilen:  # tohum sırası: kendi markalarımız (izin sorunu yok)
        sira = json.loads((ICERIK / "yedek-firmalar.json").read_text())
        for f in sira:
            if normal(f["firma"]) not in kullanilan:
                secilen = {"kaynak": "yedek", "yorum_id": None, "kullanici": f.get("kullanici", ""), "yorum": f.get("yorum", ""),
                           "begeni": 0, **{k: f[k] for k in ("firma", "sektor", "sehir", "sektor_anahtar")}, "kendisi": True}
                break
    if secilen:
        gunluk(f"{hesap}: günün firması → {secilen['firma']} ({secilen['sektor']}, {secilen['begeni']} beğeni, kaynak {secilen['kaynak']})")
    return secilen


def kullanildi(firma: str) -> None:
    k = oku("kullanilan-firmalar.json", [])
    k.append(firma); yaz("kullanilan-firmalar.json", k)


FIKIR_SISTEM = """Sen bir sosyal medya editörüsün. Kullanıcı (hesap sahibi) panelden bir içerik fikri yazdı; sokak ağzıyla, kısaltmalı, yazım
hatalı ya da Türkçe karaktersiz yazmış olabilir ("serdivandaki berbr ahmt abiye bayram kartı yap", "lokantaya sit yapsn"). Niyetini bir
insan editör gibi anla. Kartvizit / web sitesi tasarlanacak firmayı çıkar; firma adı yazılmadıysa sektöre ve yere uygun, iddiasız, uydurma
olduğu belli olmayan sade bir vitrin adı öner (ör. "Ahmet Usta Berber"). Bilmediğin bilgi (telefon, adres, fiyat) EKLEME.
Sadece JSON: {"uygun": true, "neden": "", "firma": "...", "sektor": "kısa Türkçe sektör", "sehir": "", "sektor_anahtar": "<şu listeden: %s>",
"istek": "kullanıcının ne istediği, düzgün Türkçeyle tek cümle (tema, renk, özel gün, espri isteği dahil)"}
uygun=false: siyaset, alkol/kumar/yetişkin, birine hakaret, büyük ulusal marka ya da tasarımla ilgisiz bir istek.""" % ", ".join(SEKTORLER)


def fikirden(metin: str) -> dict | None:
    """Panel fikrini günün firmasına çevirir. Uygun değilse {"red": neden}; Gemini düşerse None (fikir sonraki güne kalır)."""
    try:
        a = json_sor(FIKIR_SISTEM, f"Fikir: {metin}", 0.2)
    except Exception as e:  # noqa: BLE001
        gunluk(f"fikir anlaşılamadı: {e}"); return None
    if not a.get("uygun") or not a.get("firma") or not a.get("sektor"):
        return {"red": a.get("neden") or "Fikirden firma/sektör çıkarılamadı."}
    if any(k in normal(metin) for k in YASAK) or uygunsuz(metin, a.get("firma", ""), a.get("sektor", ""), a.get("istek", "")):
        return {"red": "Bu konu hesaplarda kullanılmıyor (argo, bahis/kumar, +18, alkol ya da benzeri)."}
    sa = a.get("sektor_anahtar") if a.get("sektor_anahtar") in SEKTORLER else "yerel-hizmet"
    return {"kaynak": "panel", "yorum_id": None, "kullanici": "", "yorum": a.get("istek") or metin, "begeni": 0, "firma": a["firma"],
            "sektor": a["sektor"], "sehir": a.get("sehir", ""), "sektor_anahtar": sa, "kendisi": False, "istek": a.get("istek") or metin}
