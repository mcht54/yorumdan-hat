"""Cüzdan Hocası 2. format — "Yılda Kaça Patlıyor?" (öğlen bölümü).
Yorumdaki bir alışkanlığın (günde bir kahve 120 TL gibi) aylık, yıllık ve 10 yıllık tutarını KOD hesaplar; yarıya indirince yılda
cebinde kalanı sayaçla gösterir. Rakam uydurulmaz: fiyatı yorum verir; yedek bölümlerde "diyelim ki" diye örnek kurulur.
Sağlığa zararlı ya da yasa dışı alışkanlıklar (sigara, alkol, bahis…) seçilmez: hesap da olsa özendirme riski var."""
from __future__ import annotations

import json
import re

import butce
from guvenlik import uygunsuz
from ortak import ICERIK, gunluk, json_sor, normal, oku

KAYIT = "para-aliskanlik-bolumler.json"
KAPANIS = "Sıradaki alışkanlık senin olsun! Yorumlara bir alışkanlığını ve fiyatını yaz. En çok beğeni alan kazanır!"
YASAK_KONU = ["sigara", "tütün", "puro", "nargile", "alkol", "bira", "rakı", "şarap", "viski", "bahis", "iddaa", "kumar", "casino",
              "kripto", "coin", "uyuşturucu", "esrar", "vape", "elektronik sigara"]
SIKLIK = {"gun": (365, "Her gün"), "hafta": (52, "Her hafta"), "ay": (12, "Her ay")}
ETIKET = {"gun": "günlük", "hafta": "haftalık", "ay": "aylık"}

CIKAR = """Instagram yorumlarından düzenli bir harcama alışkanlığı çıkarırsın. Her yorum için JSON:
- ne: alışkanlığın kısa adı, küçük harf ("kahve", "dışarıdan yemek", "taksi", "dizi aboneliği"). Yoksa "".
- fiyat: bir seferlik tutar, TL tam sayı ("120 tl" → 120, "2 bin" → 2000). Yoksa 0.
- adet: bir dönemde kaç kez (yoksa 1).
- siklik: "gun" | "hafta" | "ay" (her gün / haftada / ayda). Belirsizse "gun".
- uygun: false eğer fiyat yoksa; fiyat 5'ten az ya da 20.000'den fazlaysa; sigara, tütün, nargile, alkol, bahis, kumar, kripto, uyuşturucu
  ya da +18 içerikse; şaka/troll; hakaret/argo; kişisel veri (telefon, IBAN, adres). Diğer durumlarda true.
Sadece JSON: {"adaylar":[{"id":"...","ne":"","fiyat":0,"adet":1,"siklik":"gun","uygun":true}]}"""


def hesap(a: dict) -> dict:
    kat, _ = SIKLIK.get(a.get("siklik"), SIKLIK["gun"])
    bir = int(a["fiyat"]) * max(1, int(a.get("adet") or 1))
    yil = bir * kat
    return {"bir_donem": bir, "ay": round(yil / 12), "yil": yil, "on_yil": yil * 10, "yarisi": yil // 2, "kat": kat}


def sec(yorumlar: list[dict], kendi: str = "") -> dict:
    kullanilan = set(oku("para-kullanilan.json", []))
    ad = [y for y in yorumlar if y.get("text") and (y.get("username") or "").lower() != kendi.lower() and y["id"] not in kullanilan
          and re.search(r"\d", y["text"]) and not uygunsuz(y["text"], y.get("username", ""))
          and not any(x in normal(y["text"]) for x in YASAK_KONU)]
    ad.sort(key=lambda y: -int(y.get("like_count") or 0))
    if ad:
        try:
            cev = {c["id"]: c for c in json_sor(CIKAR, "Yorumlar:\n" + "\n".join(json.dumps({"id": y["id"], "metin": y["text"]}, ensure_ascii=False) for y in ad[:40]), 0.1).get("adaylar", [])}
        except Exception as ex:  # noqa: BLE001
            gunluk(f"alışkanlık çıkarımı olmadı: {ex}"); cev = {}
        for y in ad[:40]:
            c = cev.get(y["id"])
            if c and c.get("uygun") and c.get("ne") and 5 <= int(c.get("fiyat") or 0) <= 20000 and not any(x in normal(c["ne"]) for x in YASAK_KONU):
                return {"kaynak": "yorum", "yorum": y["text"][:160], "kullanici": y.get("username", ""), "begeni": int(y.get("like_count") or 0),
                        "yorum_id": y["id"], "ne": c["ne"].strip()[:30], "fiyat": int(c["fiyat"]), "adet": max(1, int(c.get("adet") or 1)),
                        "siklik": c.get("siklik") if c.get("siklik") in SIKLIK else "gun"}
    liste = json.loads((ICERIK / "aliskanlik-yedek.json").read_text())
    a = dict(liste[len(oku(KAYIT, [])) % len(liste)])
    a.update({"kaynak": "yedek", "kullanici": "", "begeni": 0, "yorum": ""})
    return a


def tarif(a: dict) -> str:
    """'günde 1 kez 120 ₺' gibi ekran metni."""
    s = {"gun": "Günde", "hafta": "Haftada", "ay": "Ayda"}[a["siklik"]]
    return f"{s} {a['adet']} kez · {butce.tl(a['fiyat'])}" if a["adet"] > 1 else f"{s} {butce.tl(a['fiyat'])}"


def okunuslar(h: dict) -> dict:
    return {k: butce.yazi(h[k]) + " lira" for k in ("bir_donem", "ay", "yil", "on_yil", "yarisi")}


SEMA = """{
 "kanca": "1 cümle, en fazla 12 kelime: alışkanlık + merak. (ör. 'Günde bir kahve. Masum görünüyor, değil mi?')",
 "teshis": ["alışkanlığın günlük/haftalık/aylık tutarını ('günde', 'haftada' diyerek) söyleyen 1 cümle; 'dönem' kelimesi yasak", "sıcak espri, 1 cümle (cüzdanın ya da herkesin bildiği an)"],
 "kalemler": ["AYLIK tutarı okunuşuyla söyleyen 1 cümle", "YILLIK tutarı okunuşuyla söyleyen 1 cümle", "ON YILLIK tutarı okunuşuyla söyleyen 1 cümle (bugünkü fiyatla)"],
 "ipucu": ["vazgeçmeden azaltmanın tek uygulanabilir yolu (yarıya indir, haftada iki gün ara ver, evde hazırla…)", "esprili kısa tamamlayıcı"],
 "sonuc": "yarıya indirince yılda cebinde kalan tutarı okunuşuyla söyleyen 1-2 kısa cümle",
 "ipucu_kisa": "ekranda yazacak ipucu, en fazla 7 kelime",
 "aciklama": "Instagram açıklaması gövdesi: 2 kısa cümle, hashtag yok",
 "soru": "yorumda TEK KELİMEYLE cevaplanacak iki seçenekli soru (ör. 'Vazgeçer misin, azaltır mısın?'), en fazla 7 kelime",
 "etiketler": ["en fazla 5 hashtag: #tasarruf #paratasarrufu #birikim + konuya uygun 1 + #cüzdanhocası"]
}"""


def _metinler(s: dict) -> list[tuple[str, str]]:
    from para import _metinler as m
    return m({**s, "_kapanis": KAPANIS})


def denetle(s: dict, oku_: dict) -> list[str]:
    from para import YASAK, _duz
    sorun = []
    try:
        mt = _metinler(s)
    except Exception:  # noqa: BLE001
        return ["şema eksik"]
    metin = " ".join(c for v, c in mt if v != "kapanis")
    n = len(metin.split())
    if not 50 <= n <= 118:
        sorun.append(f"anlatım {n} kelime (50-118 olmalı)")
    if "dönem" in metin.lower():
        sorun.append("'dönem' kelimesi yapay duruyor; 'günde/haftada/ayda' de")
    if re.search(r"\d", metin):
        sorun.append("rakam var: tutarları verilen okunuşla YAZIYLA yaz")
    for y in YASAK:
        if y in metin.lower():
            sorun.append(f"yasak ifade: {y}")
    kal = s.get("kalemler") or []
    if len(kal) != 3:
        sorun.append("kalemler tam 3 cümle olmalı (aylık, yıllık, on yıllık)")
    else:
        for i, kod in enumerate(("ay", "yil", "on_yil")):
            if normal(oku_[kod]) not in normal(_duz(kal[i])):
                sorun.append(f"kalemler[{i}] '{oku_[kod]}' ifadesini aynen içermeli")
    if normal(oku_["yarisi"]) not in normal(_duz(s.get("sonuc"))):
        sorun.append(f"sonuc '{oku_['yarisi']}' ifadesini aynen içermeli")
    for v, c in mt:
        if v != "kapanis" and len(c.split()) > (22 if any(normal(x) in normal(c) for x in oku_.values()) else 14):
            sorun.append(f"uzun cümle: {c[:40]}…")
    return sorun


def yaz_senaryo(a: dict, h: dict, gun: int) -> dict:
    from para import kurallar, mizah_metni, mizah_sec
    oku_ = okunuslar(h)
    mz = mizah_sec("para-aliskanlik")
    son = oku("para-son-kancalar.json", [])[-8:]
    istem = f"""Yılda Kaça Patlıyor?, Gün {gun}.
{'Seçilen yorum (@' + a['kullanici'] + ', ' + str(a['begeni']) + ' beğeni): "' + a['yorum'] + '"' if a['kaynak'] == 'yorum' else 'Bugün ÖRNEK bir alışkanlık (gerçek kişi değil): cümleyi "Diyelim ki..." diye kur, "yorumlardan geldi" DEME.'}
Alışkanlık: {a['ne']}. {tarif(a)}.
Okunuşlar (HARFİ HARFİNE kullan, rakam yazma): {ETIKET[a['siklik']]} tutar '{oku_['bir_donem']}' ("dönem" kelimesini KULLANMA; "günde", "haftada", "ayda" de), aylık '{oku_['ay']}', yıllık '{oku_['yil']}', on yılda '{oku_['on_yil']}', yarıya indirirse yılda cebinde '{oku_['yarisi']}'.
Ton: suçlama yok, "bırak" deme; "azalt, cebinde kalsın" de. Alışkanlığı küçümseme.
Son bölümlerin kancaları (tekrar etme): {json.dumps(son, ensure_ascii=False)}
{mizah_metni(mz)}
Bu formatta komik zemin: alışkanlığın masum görünmesi ile yıllık tutarın büyüklüğü arasındaki tezat (cüzdanın şaşkınlığı).
Şu JSON şemasını doldur (yalnız JSON):
{SEMA}"""
    sistem = "Sen Cüzdan Hocası'sın: konuşan, neşeli bir cüzdan. Kısa Reels anlatımı yazarsın. Kurallara harfiyen uy.\n\n" + kurallar()
    sorunlar = []
    for _ in range(3):
        try:
            s = json_sor(sistem, istem + (f"\nÖnceki denemede sorunlar vardı, düzelt: {sorunlar}" if sorunlar else ""), 0.9)
        except Exception as ex:  # noqa: BLE001
            gunluk(f"alışkanlık senaryosu yazılamadı: {ex}"); break
        sorunlar = denetle(s, oku_)
        if not sorunlar:
            s["_kaynak"] = "gemini"; s["_kapanis"] = KAPANIS; s["_mizah"] = mz; return s
        gunluk(f"alışkanlık senaryo denetimi: {sorunlar}")
    gunluk("alışkanlık: yedek senaryo")
    return yedek(a, h, gun)


def yedek(a: dict, h: dict, gun: int) -> dict:
    o = okunuslar(h)
    s_ = {"gun": "günde", "hafta": "haftada", "ay": "ayda"}[a["siklik"]]
    on = "Diyelim ki " if a["kaynak"] != "yorum" else ""
    return {"_kaynak": "yedek", "_kapanis": KAPANIS,
            "kanca": f"{on}{s_} bir {a['ne']}. Masum görünüyor, değil mi?".capitalize() if on else f"{s_.capitalize()} bir {a['ne']}. Masum görünüyor, değil mi?",
            "teshis": [f"{s_.capitalize()} {o['bir_donem']}.", "Cüzdan şimdilik gülümsüyor. Şimdilik."],
            "kalemler": [f"Ayda {o['ay']} ediyor. Hâlâ masum.", f"Yılda {o['yil']}. Cüzdan oturdu.", f"On yılda, bugünkü fiyatla {o['on_yil']}. Cüzdan bayıldı."],
            "ipucu": ["Vazgeçme, sadece yarıya indir.", "Keyif de kalsın, cüzdan da ayılsın."],
            "sonuc": f"Yarıya indirirsen yılda {o['yarisi']} cebinde kalır.", "ipucu_kisa": "Vazgeçme, yarıya indir",
            "aciklama": f"Küçük alışkanlıkların yıllık hesabını yaptık.\nSen hangisini azaltırdın?",
            "soru": "Vazgeçer misin, azaltır mısın?", "etiketler": ["#tasarruf", "#paratasarrufu", "#birikim", "#" + re.sub(r"\W", "", a["ne"]), "#cüzdanhocası"]}


IKON = {"donem": "🔁", "ay": "📅", "yil": "📆", "on_yil": "⏳"}
RENK = {"donem": "#7cc6fe", "ay": "#ffd23f", "yil": "#ffa63d", "on_yil": "#ff6b4a"}


def gorsel(a: dict, h: dict, s: dict, gun: int) -> dict:
    """para.yap'ın genel şablon sahnelerine bu formatın içeriği."""
    from uret import e
    if a["kaynak"] == "yorum":
        bal = (f'<div class="balon" id="balon"><div class="avatar"><span>{e((a["kullanici"] or "?")[:1].upper())}</span></div><div class="bm">'
               f'<div class="balon-kim">@{e(a["kullanici"])}</div><div class="balon-metin">“{e(a["yorum"])}”</div></div>'
               f'<div class="kalp">♥<b>{a["begeni"] or ""}</b></div></div>')
        et = f"Yılda Kaça Patlıyor? · Gün {gun} · Yorumlardan"
    else:
        bal = f'<div class="balon" id="balon"><div class="bm"><div class="balon-kim">Bugünün örnek alışkanlığı</div><div class="balon-metin">{e(a["ne"].capitalize())} · {e(tarif(a))}</div></div></div>'
        et = f"Yılda Kaça Patlıyor? · Gün {gun}"
    cip = f'<div class="cipler"><span class="cip c-maas" id="c1"><small>{e(a["ne"].capitalize())}</small>{butce.tl(h["bir_donem"])}</span></div>'
    donem = {"gun": "Her gün", "hafta": "Her hafta", "ay": "Her ay"}[a["siklik"]]
    teshis = (f'<div class="etiket"><i></i>{e(tarif(a))}</div><div class="baslik" id="tb">{e(donem)} <b>{butce.tl(h["bir_donem"])}</b></div>'
              f'<div class="baslik" style="font-size:72px;margin-top:30px">Peki bir yılda?</div>')
    satirlar = [[{"kod": "donem", "ad": donem, "tutar": h["bir_donem"]}, {"kod": "ay", "ad": "Bir ayda", "tutar": h["ay"]}],
                [{"kod": "yil", "ad": "Bir yılda", "tutar": h["yil"]}],
                [{"kod": "on_yil", "ad": "On yılda (bugünkü fiyatla)", "tutar": h["on_yil"]}]]
    for g in satirlar:
        for x in g:
            x.update({"renk": RENK[x["kod"]], "ikon": IKON[x["kod"]], "yuzde": max(1, round(100 * x["tutar"] / h["on_yil"]))})
    sonuc = (f'<div class="etiket"><i></i>Yarıya indirirsen</div><div class="sayac-ust">Her yıl cebinde</div>'
             f'<div class="sayac" id="sayac" data-v="{h["yarisi"]}">0 ₺</div><div class="uyari">Hesap bugünkü fiyatla yapılmıştır; genel bilgidir.</div>')
    return {"kanca": f'<div class="etiket dolu" id="kanca-et"><i></i>{e(et)}</div>{bal}{cip}', "teshis": teshis, "gruplar": satirlar,
            "kalem_etiket": "Hesap büyüyor", "sonuc": sonuc, "cta": ("Sıradaki alışkanlık", "senin olsun!"), "yorum_yazi": "Alışkanlık + fiyatı",
            "marka_alt": "Her gün bir hesap", "ifadeler": [("0", "hesap"), ("T0", "mutlu"), ("K0", "sok"), ("I0", "kirp"), ("S0", "mutlu"), ("C", "mutlu")],
            "paralar": [("0", 3), ("K0", 1), ("S0", 4), ("C", 3)], "log": f"alışkanlık {a['ne']} yılda {h['yil']}"}


def ilk_satir(a: dict, h: dict) -> str:
    n = len(oku(KAYIT, []))
    s_ = {"gun": "Günde", "hafta": "Haftada", "ay": "Ayda"}[a["siklik"]]
    sec = [f"{s_} {butce.tl(a['fiyat'])} {a['ne']}: yılda {butce.tl(h['yil'])} ediyor. Sen olsan?",
           f"{a['ne'].capitalize()} masum mu? 10 yılda {butce.tl(h['on_yil'])} 👇",
           f"Bir {a['ne']} alışkanlığının yıllık hesabı: {butce.tl(h['yil'])}",
           f"{a['ne'].capitalize()} parası yarıya inse yılda {butce.tl(h['yarisi'])} cebinde 👇"]
    return sec[n % len(sec)]


def aciklama(s: dict, a: dict, h: dict, ai: bool) -> str:
    etk = " ".join([x if x.startswith("#") else "#" + x for x in s.get("etiketler", [])][:5])
    par = [ilk_satir(a, h), str(s.get("aciklama") or "").strip(), "", f"🤔 {(s.get('soru') or 'Vazgeçer misin, azaltır mısın?').strip()} Yorumlara tek kelime yaz 👇",
           "📌 Kaydet: harcamadan önce bu hesabı hatırla.", "",
           "💬 Sıradaki alışkanlık senin olsun: yorumlara bir alışkanlığını ve fiyatını yaz. En çok beğeni alan kazanır."]
    if a.get("kaynak") == "yorum" and a.get("kullanici"):
        par.append(f"Bugünün alışkanlığı: @{a['kullanici']} (yorumuyla seçildi, {a['begeni']} beğeni)")
    par += ["Bu alışkanlığı olan bir arkadaşın varsa videoyu ona gönder.", "Hesap bugünkü fiyatla yapılmıştır; genel bilgidir."]
    if ai:
        par.append("Seslendirme yapay zekâ ile yapılmıştır.")
    par += ["", etk]
    return "\n".join(par)[:2150]
