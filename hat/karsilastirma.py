"""Cüzdan Hocası 3. format — "Maaş Kapışması" (17:30).
Yorumlardaki iki maaşı (ya da yedek çifti) aynı ekranda karşılaştırır: kira, mutfak+fatura, kalan; sonuçta yıllık kenara farkı ve
"maaşın yüzde kaçı kenara" oranı. Çatışma yorum getirir (2026-11-27 ölçüm: @sezerkarikatur "Asgari ücretli kız ile 100 bin maaşlı erkek" 713 bin).
Kural: kimse küçümsenmez, "kazanan" kişi değil yöntemdir; bütün tutarları butce.plan hesaplar."""
from __future__ import annotations

import json
import re

import butce
import para
from ortak import ICERIK, gunluk, json_sor, normal, oku

KAYIT = "para-kapisma-bolumler.json"
KAPANIS = "Sıradaki kapışma seninle! Yorumlara maaşını, kiranı ve şehrini yaz. En çok beğeni alan kazanır!"


def _plan(k: dict) -> dict:
    return butce.plan(k["maas"], k.get("kira"), k.get("konut", "kira"), k.get("hane", "bekar"), int(k.get("cocuk") or 0), int(k.get("borc") or 0))


def sec(yorumlar: list[dict], kendi: str = "") -> tuple[dict, dict]:
    """İki aday: yorumlardan maaşı belirgin farklı en çok beğenilen iki yorum; yoksa icerik/kapisma-yedek.json çifti."""
    if yorumlar:
        a = para.sec(yorumlar, kendi)
        if a.get("kaynak") == "yorum":
            kalan = [y for y in yorumlar if y["id"] != a.get("yorum_id")]
            b = para.sec(kalan, kendi)
            if b.get("kaynak") == "yorum" and abs(b["maas"] - a["maas"]) >= 5000:
                return (a, b) if a["maas"] <= b["maas"] else (b, a)
    liste = json.loads((ICERIK / "kapisma-yedek.json").read_text())
    c = liste[len(oku(KAYIT, [])) % len(liste)]
    a, b = dict(c["a"]), dict(c["b"])
    for x in (a, b):
        x.update({"kaynak": "yedek", "kullanici": "", "begeni": 0, "yorum": ""})
    return a, b


def _etiket(k: dict) -> str:
    return "Asgari ücretli" if (k.get("asgari") or k["maas"] == para.ASGARI) else f"{butce.tl(k['maas'])} maaşlı"


def okunuslar(a: dict, b: dict, pa: dict, pb: dict) -> dict:
    y = butce.yazi
    o = {"a_maas": y(a["maas"]) + " lira", "b_maas": y(b["maas"]) + " lira",
         "a_yil": y(pa["kenara_yil"]) + " lira", "b_yil": y(pb["kenara_yil"]) + " lira",
         "a_acik": y(pa["acik"]) + " lira", "b_acik": y(pb["acik"]) + " lira"}
    o["a_oran"] = "yüzde " + y(max(0, round(100 * pa["kalan"] / pa["maas"]))) if pa["kalan"] > 0 else "yüzde sıfır"
    o["b_oran"] = "yüzde " + y(max(0, round(100 * pb["kalan"] / pb["maas"]))) if pb["kalan"] > 0 else "yüzde sıfır"
    return o


SEMA = """{
 "kanca": "1 cümle, en fazla 12 kelime: iki maaşı okunuşla söyle + 'kim daha rahat?' merakı",
 "teshis": ["iki kişinin durumunu tanıtan 1 cümle (şehir, kira)", "esprili 1 cümle (cüzdanın hakemliği, iki cüzdanın atışması)"],
 "kalemler": ["A kişisinin kenara ayırabildiği yıllık tutar ya da açığı (verilen okunuşla) 1 cümle", "B kişisinin yıllık tutarı ya da açığı 1 cümle", "oranı karşılaştıran 1 cümle (maaşın yüzde kaçı kenara)"],
 "ipucu": ["iki kişiye de yarayacak tek uygulanabilir ipucu", "esprili tamamlayıcı"],
 "sonuc": "sonucu söyleyen 1-2 kısa cümle: kazanan kişi değil yöntem; maaş büyük diye bütçe rahat olmayabilir ya da tersi",
 "ipucu_kisa": "ekranda yazacak ipucu, en fazla 7 kelime",
 "aciklama": "Instagram açıklaması gövdesi: 2 kısa cümle, hashtag yok",
 "soru": "yorumda TEK KELİMEYLE cevaplanacak soru (ör. 'Sence kim daha rahat: A mı B mi?')",
 "etiketler": ["en fazla 5 hashtag: #maaş #bütçe #birikim + 1 + #cüzdanhocası"]
}"""


def denetle(s: dict, o: dict, pa: dict, pb: dict) -> list[str]:
    sorun = []
    mt = para._metinler({**s, "_kapanis": KAPANIS})
    metin = " ".join(c for v, c in mt if v != "kapanis")
    if not 50 <= len(metin.split()) <= 130:
        sorun.append(f"anlatım {len(metin.split())} kelime (50-130 olmalı)")
    if re.search(r"\d", metin):
        sorun.append("rakam var: okunuşla YAZIYLA yaz")
    for y in para.YASAK + ["fakir", "zavallı", "ezik"]:
        if y in metin.lower():
            sorun.append(f"yasak ifade: {y}")
    kal = s.get("kalemler") or []
    if len(kal) != 3:
        sorun.append("kalemler tam 3 cümle olmalı")
    else:
        ka = o["a_yil"] if pa["kalan"] > 0 else o["a_acik"]
        kb = o["b_yil"] if pb["kalan"] > 0 else o["b_acik"]
        if normal(ka) not in normal(para._duz(kal[0])):
            sorun.append(f"kalemler[0] '{ka}' ifadesini aynen içermeli")
        if normal(kb) not in normal(para._duz(kal[1])):
            sorun.append(f"kalemler[1] '{kb}' ifadesini aynen içermeli")
    if re.search(r"(bir|iki|üç|dört|beş|altı|yedi|sekiz|dokuz|on|yirmi|otuz|kırk|elli|altmış|yetmiş|seksen|doksan|yüz)'", metin):
        sorun.append("okunuşa kesme işaretiyle ek getirme ('otuz bir'i' yanlış); 'kadarı' gibi eksiz kur")
    for v, c in mt:
        if v != "kapanis" and len(c.split()) > (26 if any(normal(x) in normal(c) for x in o.values()) else 15):
            sorun.append(f"uzun cümle: {c[:40]}…")
    return sorun


def yaz_senaryo(a: dict, b: dict, pa: dict, pb: dict, gun: int) -> dict:
    o = okunuslar(a, b, pa, pb)
    mz = para.mizah_sec("para-kapisma")
    yorum = "" if a["kaynak"] != "yorum" else f'Yorumlar: A @{a["kullanici"]} "{a["yorum"]}" / B @{b["kullanici"]} "{b["yorum"]}"'
    istem = f"""Maaş Kapışması, Gün {gun}. {yorum or 'Bugün ÖRNEK iki bütçe (gerçek kişi değil), "yorumlardan geldi" DEME.'}
A: {_etiket(a)} · {para.ozet(a)} · durum {pa['durum']} · yıllık kenara '{o['a_yil']}' · aylık açık '{o['a_acik']}' · maaşın {o['a_oran']} kadarı kenara
B: {_etiket(b)} · {para.ozet(b)} · durum {pb['durum']} · yıllık kenara '{o['b_yil']}' · aylık açık '{o['b_acik']}' · maaşın {o['b_oran']} kadarı kenara
Maaş okunuşları: A '{o['a_maas']}', B '{o['b_maas']}'. Kenara 0 ise o kişi için açığı söyle. Okunuşları HARFİ HARFİNE kullan, rakam yazma.
Kimseyi küçümseme; asgari ücretliyle dalga geçme. Mesaj: bütçe yöntemi maaştan önemli.
Son kancalar (tekrar etme): {json.dumps(oku('para-son-kancalar.json', [])[-8:], ensure_ascii=False)}
{para.mizah_metni(mz)}
Şu JSON şemasını doldur (yalnız JSON):
{SEMA}"""
    sistem = "Sen Cüzdan Hocası'sın: iki bütçeyi hakem gibi karşılaştıran neşeli bir cüzdan. Kurallara harfiyen uy.\n\n" + para.kurallar()
    sorunlar = []
    for _ in range(3):
        try:
            s = json_sor(sistem, istem + (f"\nÖnceki denemede sorunlar vardı, düzelt: {sorunlar}" if sorunlar else ""), 0.9)
        except Exception as ex:  # noqa: BLE001
            gunluk(f"kapışma senaryosu yazılamadı: {ex}"); break
        sorunlar = denetle(s, o, pa, pb)
        if not sorunlar:
            s.update({"_kaynak": "gemini", "_kapanis": KAPANIS, "_mizah": mz}); return s
        gunluk(f"kapışma senaryo denetimi: {sorunlar}")
    gunluk("kapışma: yedek senaryo")
    return yedek(a, b, pa, pb, gun)


def yedek(a: dict, b: dict, pa: dict, pb: dict, gun: int) -> dict:
    o = okunuslar(a, b, pa, pb)
    ka = f"yılda {o['a_yil']} kenara ayırır" if pa["kalan"] > 0 else f"her ay {o['a_acik']} açık verir"
    kb = f"yılda {o['b_yil']} kenara ayırır" if pb["kalan"] > 0 else f"her ay {o['b_acik']} açık verir"
    return {"_kaynak": "yedek", "_kapanis": KAPANIS,
            "kanca": f"{o['a_maas'].replace(' lira', '').capitalize()} maaş mı, {o['b_maas'].replace(' lira', '')} maaş mı? Kim daha rahat?",
            "teshis": ["İki bütçe, tek hakem: ben.", "Düdüğümü aldım, fermuarımı kapattım. Başlıyoruz."],
            "kalemler": [f"Birinci bütçe {ka}.", f"İkinci bütçe {kb}.", f"Oranla bakınca biri maaşın {o['a_oran']} kadarını, diğeri {o['b_oran']} kadarını koruyor."],
            "ipucu": ["Maaş günü önce kenara ayır, sonra harca.", "Maaş büyüyünce harcama da spor salonuna yazılıyor."],
            "sonuc": "Kazanan kişi değil, yöntem. Plan varsa küçük maaş da büyür.", "ipucu_kisa": "Önce kenara ayır, sonra harca",
            "aciklama": "İki maaşı aynı ekranda kapıştırdık.\nSence kim daha rahat?", "soru": "Sence kim daha rahat: birinci mi ikinci mi?",
            "etiketler": ["#maaş", "#bütçe", "#birikim", "#asgariücret" if (a.get("asgari") or b.get("asgari")) else "#paratasarrufu", "#cüzdanhocası"]}


def gorsel(a: dict, b: dict, pa: dict, pb: dict, s: dict, gun: int) -> dict:
    from uret import e
    et = f"Maaş Kapışması · Gün {gun}" + (" · Yorumlardan" if a["kaynak"] == "yorum" else "")
    bal = (f'<div class="balon" id="balon"><div class="bm"><div class="balon-kim">{"@" + e(a["kullanici"]) + " vs @" + e(b["kullanici"]) if a["kaynak"] == "yorum" else "Bugünün kapışması"}</div>'
           f'<div class="balon-metin">{e(para.ozet(a))}<br>vs {e(para.ozet(b))}</div></div></div>')
    cip = (f'<div class="cipler"><span class="cip c-maas" id="c1"><small>{e(_etiket(a))}</small>{butce.tl(a["maas"])}</span>'
           f'<span class="cip c-kira" id="c2"><small>{e(_etiket(b))}</small>{butce.tl(b["maas"])}</span></div>')
    teshis = (f'<div class="etiket"><i></i>Aynı soru, iki bütçe</div><div class="baslik" id="tb">Kim daha <b>rahat?</b></div>'
              f'<div class="lejant" id="lejant" style="flex-direction:column;gap:14px"><span>🅰 {e(para.ozet(a))}</span><span>🅱 {e(para.ozet(b))}</span></div>')

    def kalem(p: dict, kod: str) -> int:
        return sum(x["tutar"] for x in p["kalemler"] if x["kod"] in kod.split(","))

    def ab(ad: str, va: int, vb: int, kod: str, renk: str, ikon: str) -> dict:
        return {"kod": kod, "ad": ad, "tutar": max(va, vb), "metin": f"{butce.tl(va)} | {butce.tl(vb)}", "renk": renk, "ikon": ikon, "yuzde": 33}
    satir = [[ab("Kira / ev", kalem(pa, "kira,ev"), kalem(pb, "kira,ev"), "ka", "#ff6b4a", "🏠"),
              ab("Mutfak + fatura", kalem(pa, "mutfak,fatura"), kalem(pb, "mutfak,fatura"), "km", "#ffd23f", "🛒")],
             [ab("Yılda kenara", pa["kenara_yil"], pb["kenara_yil"], "ky", "#1f9d6b", "🎯")],
             [{"kod": "ko", "ad": "Maaşın yüzde kaçı kenara", "tutar": 0, "renk": "#7cc6fe", "ikon": "⚖️", "yuzde": 33,
               "metin": f"%{max(0, round(100 * pa['kalan'] / pa['maas']))} | %{max(0, round(100 * pb['kalan'] / pb['maas']))}"}]]
    fark = abs(pa["kenara_yil"] - pb["kenara_yil"])
    sonuc = (f'<div class="etiket"><i></i>🅰 {e(_etiket(a))} · 🅱 {e(_etiket(b))}</div><div class="sayac-ust">Yıllık fark</div>'
             f'<div class="sayac" id="sayac" data-v="{fark}">0 ₺</div><div class="uyari">Genel bütçe önerisidir, yatırım tavsiyesi değildir.</div>')
    return {"kanca": f'<div class="etiket dolu" id="kanca-et"><i></i>{e(et)}</div>{bal}{cip}', "teshis": teshis, "gruplar": satir,
            "kalem_etiket": "🅰 solda · 🅱 sağda", "sonuc": sonuc, "cta": ("Sıradaki kapışma", "seninle!"), "yorum_yazi": "Maaş + kira + şehir",
            "marka_alt": "Her gün bir kapışma", "ifadeler": [("0", "sok"), ("T0", "hesap"), ("K0", "hesap"), ("I0", "kirp"), ("S0", "mutlu"), ("C", "mutlu")],
            "paralar": [("0", 2), ("S0", 4), ("C", 3)], "log": f"kapışma {a['maas']} vs {b['maas']}"}


def aciklama(s: dict, a: dict, b: dict, pa: dict, pb: dict, ai: bool) -> str:
    etk = " ".join([x if x.startswith("#") else "#" + x for x in s.get("etiketler", [])][:5])
    ilk = f"{_etiket(a)} vs {_etiket(b)}: kim yılda daha çok kenara ayırıyor? 👇"
    par = [ilk, str(s.get("aciklama") or "").strip(), "", f"🤔 {(s.get('soru') or 'Sence kim daha rahat?').strip()} Yorumlara yaz 👇",
           "📌 Kaydet: maaşın ne olursa olsun önce kenara ayır.", "",
           "💬 Sıradaki kapışma seninle: yorumlara maaşını, kiranı ve şehrini yaz. En çok beğeni alan kazanır."]
    if a.get("kaynak") == "yorum":
        par.append(f"Bugünün kapışması: @{a['kullanici']} vs @{b['kullanici']} (yorumlarıyla seçildi)")
    par += ["Maaşını kıyaslayan bir arkadaşın varsa videoyu ona gönder.", "Genel bütçe önerisidir, yatırım tavsiyesi değildir."]
    if ai:
        par.append("Seslendirme yapay zekâ ile yapılmıştır.")
    par += ["", etk]
    return "\n".join(par)[:2150]
