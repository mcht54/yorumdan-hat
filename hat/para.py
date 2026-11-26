"""Cüzdan Hocası bölümü: yorumdan maaş/kira/hane → bütçe planı (kod hesaplar) → senaryo (Gemini, rakamlar okunuşla) →
ses → hizalama → şablon katmanları → render → miks.
Kanıt: @milyoner.dersleri'nin en çok izlenen videosu "80.000 ₺ maaş için hazır sistem" (943 bin, 2026-11-26 ölçümü);
yorumla ilerleyen seri @senyaz.tv / @imzatasarimi mekaniği. Bkz. icerik/para-kurallari.md."""
from __future__ import annotations

import json
import pathlib
import random
import re

import butce
from guvenlik import uygunsuz
from kartvizit import altyazilar, kelime_html
from ortak import ICERIK, gunluk, json_sor, normal, oku
from ses import dok, hizala, seslendir
from uret import e, hazirla, miks, render

KAPANIS = "Sıradaki bütçe senin olsun! Yorumlara maaşını, kiranı ve şehrini yaz. En çok beğeni alan kazanır!"
SES = "Puck"           # Cüzdan Hocası: neşeli, hızlı; Whisper geçmezse Fenrir
YASAK = ["muhteşem", "inanılmaz", "haydi", "kaçırmayın", "kanka", "garanti", "kesin kazanç", "zengin ol", "hisse", "kripto", "coin",
         "borsa", "fon al", "dolar al", "altın al", "yatırım tavsiyesi"]

# ---------- yorum seçimi ----------
CIKAR = """Instagram yorumlarından kişisel bütçe bilgisi çıkarırsın. Her yorum için JSON:
- maas: aylık NET gelir, TL tam sayı ("45 bin" → 45000, "45k" → 45000, "1,5 milyon" → yıllık değilse 1500000). Yoksa 0.
- kira: aylık kira TL tam sayı; yazılmamışsa null.
- konut: "kira" | "ev_sahibi" | "aile" (ailesiyle/annemlerle oturuyorsa aile). Belirsizse "kira".
- sehir: il ya da ilçe; yoksa "".
- hane: "bekar" | "evli". cocuk: sayı (yoksa 0). borc: aylık kredi/kart taksiti TL (yoksa 0).
- hedef: kısa ("ev almak", "araba", "düğün") yoksa "".
- uygun: false eğer maaş yoksa; maaş 5.000'den az ya da 1.000.000'dan fazlaysa; şaka/troll; telefon, TC no, IBAN, adres gibi kişisel veri;
  hakaret/argo; bahis, kumar, kripto/coin al-sat, +18; siyaset. Diğer durumlarda true.
- neden: uygun değilse tek cümle.
Sadece JSON: {"adaylar":[{"id":"...","maas":0,"kira":null,"konut":"kira","sehir":"","hane":"bekar","cocuk":0,"borc":0,"hedef":"","uygun":true,"neden":""}]}"""


def sec(yorumlar: list[dict], kendi: str = "") -> dict | None:
    """En çok beğenilen uygun yorum; yoksa icerik/para-yedek.json sırası (örnek bütçe, kullanıcı adı YOK)."""
    kullanilan = set(oku("para-kullanilan.json", []))
    ad = [y for y in yorumlar if y.get("text") and (y.get("username") or "").lower() != kendi.lower() and y["id"] not in kullanilan
          and re.search(r"\d", y["text"]) and not uygunsuz(y["text"], y.get("username", ""))]
    ad.sort(key=lambda y: -int(y.get("like_count") or 0))
    ad = ad[:40]
    if ad:
        istem = "Yorumlar:\n" + "\n".join(json.dumps({"id": y["id"], "metin": y["text"]}, ensure_ascii=False) for y in ad)
        try:
            cev = {a["id"]: a for a in json_sor(CIKAR, istem, 0.1).get("adaylar", [])}
        except Exception as ex:  # noqa: BLE001
            gunluk(f"para: yorum çıkarımı olmadı: {ex}"); cev = {}
        for y in ad:
            c = cev.get(y["id"])
            if c and c.get("uygun") and 5000 <= int(c.get("maas") or 0) <= 1_000_000:
                return {"kaynak": "yorum", "yorum": y["text"][:160], "kullanici": y.get("username", ""), "begeni": int(y.get("like_count") or 0),
                        "yorum_id": y["id"], "maas": int(c["maas"]), "kira": int(c["kira"]) if c.get("kira") else None, "konut": c.get("konut") or "kira",
                        "sehir": c.get("sehir") or "", "hane": c.get("hane") or "bekar", "cocuk": int(c.get("cocuk") or 0), "borc": int(c.get("borc") or 0),
                        "hedef": c.get("hedef") or ""}
    liste = json.loads((ICERIK / "para-yedek.json").read_text())
    sira = len(oku("para-bolumler.json", []))
    p = dict(liste[sira % len(liste)])
    p.update({"kaynak": "yedek", "kullanici": "", "begeni": 0})
    return p


ASGARI = 28075   # 2026 net asgari ücret (ÇSGB 23.12.2025, Resmî Gazete 26.12.2025); 2027 açıklanınca güncelle


def ozet(k: dict) -> str:
    """Ekran ve senaryo için tek satır durum: 'İstanbul · evli · 1 çocuk · kirada'."""
    p = ["asgari ücret"] if k.get("asgari") or int(k.get("maas") or 0) == ASGARI else []
    p += [k["sehir"]] if k.get("sehir") else []
    p.append("evli" if k.get("hane") == "evli" else "bekâr")
    if k.get("cocuk"):
        p.append(f"{k['cocuk']} çocuk")
    p.append({"kira": "kirada", "ev_sahibi": "ev sahibi", "aile": "ailesiyle"}.get(k.get("konut"), "kirada"))
    return " · ".join(p)


# ---------- mizah ----------
# 2026-11-26 Mücahit: "içeriklere komedi ve mizah ekle". Her bölüm 3 farklı mizah türü; son 2 bölümde kullanılan türler tekrar etmez.
MIZAH = {
    "dram": "CÜZDANIN DRAMI: cüzdan olaylara dramatik tepki verir ('Kirayı görünce fermuarım kendiliğinden kapandı.').",
    "tanidik": "TANIDIK AN: herkesin yaşadığı para anı ('Ayın yirmisi: makarna ve umut.').",
    "abarti": "TATLI ABARTI: tutarın ya da zarfın etkisini sevimli abart ('Bu acil fon o kadar sağlam ki kendi kasası var.').",
    "ucleme": "ÜÇLEME: iki normal öğe, üçüncüsü sürpriz ('Kira, fatura ve... annemin yemek yedin mi telefonu.').",
    "ters_kose": "BEKLENTİ KIRMA: cümle bir yöne gider, son kelime ters köşe yapar.",
    "kendine": "KENDİNE TAKILMA: Cüzdan Hocası kendi hâline güler ('Ben cüzdanım, matematikten korkmam; faturalardan korkarım.').",
    "diyalog": "MİNİ DİYALOG: iki kısa replik, cüzdan ile maaş/kira/kart arasında ('Kira: Geldim! Cüzdan: Daha yeni geldin!').",
}


def mizah_sec(anahtar: str) -> list[str]:
    import random
    son = [t for x in oku(f"{anahtar}-son-mizah.json", [])[-2:] for t in x]
    aday = [m for m in MIZAH if m not in son]
    if len(aday) < 3:
        aday = list(MIZAH)
    return random.sample(aday, 3)


def mizah_metni(tur: list[str]) -> str:
    return ("ESPRİ: en az 4 espri (kanca sonrası, teşhis, kalemlerden biri, ipucu) ve sonuçta kancaya geri dönüş. "
            "Bu bölümün mizah türleri (art arda iki espri aynı türden olmasın):\n" + "\n".join(f"{i + 1}. {MIZAH[m]}" for i, m in enumerate(tur)))


# ---------- senaryo ----------
# Kanca türü her bölüm döner (instagram-growth / hook-writer: ilk 2 sn izlenme süresini belirler, aynı kalıp izleyiciyi yorar)
KANCA_TURLERI = [
    "SORU: maaş + kira okunuşu, sonra 'bu bütçe yeter mi?' benzeri soru (her seferinde farklı kelimelerle)",
    "ŞOK ORAN: önce kiranın/zorunlu giderin maaşa oranını söyle ('Maaşın yarısından fazlası daha ay başında gidiyor.'), sonra maaşı",
    "SONUÇ ÖNCE: bölümün sonunda çıkan yıllık kenara tutarını ya da açığı ilk cümlede söyle, 'nasıl mı?' merakıyla bitir",
    "TANIDIK AN: herkesin yaşadığı para anıyla başla ('Maaş yattı, üç gün sonra hesap boş.') ve hemen bu kişinin maaşını söyle",
    "İDDİA: tek cümlelik cesur ama doğru iddia ('Bu maaşla birikim yapılır, kanıtlıyorum.'); tutarlar sonraki cümlede",
]
GRUPLAR = [("kira", "ev", "fatura"), ("mutfak", "ulasim", "borc"), ("acil",), ("hedef", "keyif")]


def gruplar(p: dict) -> list[list[dict]]:
    kod = {x["kod"]: x for x in p["kalemler"]}
    return [g for g in ([kod[c] for c in grp if c in kod] for grp in GRUPLAR) if g]


SEMA = """{
 "kanca": "1 cümle, en fazla 12 kelime: maaş (ve varsa kira) okunuşu + merak sorusu. (ör. 'Kırk beş bin maaş, yirmi bin kira. Bu bütçe nefes alır mı?')",
 "teshis": ["durum tespiti, 1 cümle (kira oranı ya da genel durum, verilen okunuşlarla)", "cüzdanın hâliyle ilgili sıcak espri, 1 cümle"],
 "kalemler": ["GRUP 1 cümlesi", "GRUP 2 cümlesi", "... her grup için tam BİR cümle, sırayla"],
 "ipucu": ["bu kişinin durumuna özel, uygulanabilir tek ipucu (genel bilgi; fiyat/istatistik uydurma yok)", "ipucuna esprili kısa tamamlayıcı"],
 "sonuc": "aylık ve yıllık kenara okunuşlarıyla 1-2 kısa cümle (açık varsa: açığı ve kapanma yolunu söyle)",
 "ipucu_kisa": "ekranda yazacak ipucu, en fazla 7 kelime",
 "baslik": "kapak yazısı, 3-5 kelime (ör. '45 bin maaşa bütçe')",
 "aciklama": "Instagram açıklaması: ilk satır '<maaş> TL maaşa bütçe planı – Bütçe Kliniği Gün <n>', sonra 2 kısa cümle; hashtag yok",
 "soru": "yorumda TEK KELİMEYLE cevaplanacak iki seçenekli soru (ör. 'Sen olsan keyif mi birikim mi?'), en fazla 7 kelime",
 "etiketler": ["en fazla 5 hashtag: #bütçe #birikim #paratasarrufu + 1 şehir + #cüzdanhocası"]
}"""


def _duz(x) -> str:
    return " ".join(str(y).strip() for y in x) if isinstance(x, list) else str(x or "").strip()


def _metinler(s: dict) -> list[tuple[str, str]]:
    out = [("kanca", _duz(s.get("kanca")))]
    for v in ("teshis", "kalemler", "ipucu"):
        d = s.get(v) or []
        for i, c in enumerate(d if isinstance(d, list) else [d]):
            out.append((f"{v}{i}", _duz(c)))
    out.append(("sonuc", _duz(s.get("sonuc"))))
    out.append(("kapanis", s.get("_kapanis") or KAPANIS))
    return [(v, c) for v, c in out if c]


def denetle(s: dict, p: dict, oku_: dict) -> list[str]:
    sorun = []
    try:
        metinler = _metinler(s)
    except Exception:  # noqa: BLE001
        return ["şema eksik"]
    metin = " ".join(c for v, c in metinler if v != "kapanis")
    n = len(metin.split())
    if not 60 <= n <= 138:   # tutarlar yazıyla okunur ("altı bin iki yüz elli lira" = 5 kelime) → sınır geniş
        sorun.append(f"anlatım {n} kelime (60-138 olmalı)")
    if re.search(r"\d", metin):
        sorun.append("rakam var: tutarları verilen okunuşla YAZIYLA yaz")
    for y in YASAK:
        if y in metin.lower():
            sorun.append(f"yasak ifade: {y}")
    gr = gruplar(p)
    if len(s.get("kalemler") or []) != len(gr):
        sorun.append(f"kalemler tam {len(gr)} cümle olmalı")
    else:
        for i, g in enumerate(gr):
            for x in g:
                if normal(oku_[x["kod"]]) not in normal(_duz(s["kalemler"][i])):
                    sorun.append(f"kalemler[{i}] '{oku_[x['kod']]}' ifadesini aynen içermeli ({x['ad']})")
    if not _duz(s.get("kanca")) or not _duz(s.get("sonuc")):
        sorun.append("kanca ve sonuc dolu tek cümle olmalı")
    if p["kalan"] > 0 and normal(oku_["kenara_yil"]) not in normal(_duz(s.get("sonuc"))):
        sorun.append(f"sonuc '{oku_['kenara_yil']}' ifadesini aynen içermeli")
    for v, c in metinler:
        sinir = 26 if any(normal(x) in normal(c) for x in oku_.values()) else 15   # tutar içeren cümle uzun olabilir
        if v != "kapanis" and len(c.split()) > sinir:
            sorun.append(f"uzun cümle: {c[:40]}…")
    return sorun


def kurallar() -> str:
    import gundem_notu  # doğrulanmış, tarihli gündem (2026-11-27): haftada 3 gün, süresi geçen düşer
    g = gundem_notu.metin(ICERIK / "gundem" / "para.json")
    return (ICERIK / "para-kurallari.md").read_text() + (("\n\n" + g) if g else "")


def yaz_senaryo(k: dict, p: dict, gun: int) -> dict:
    oku_ = butce.okunuslar(p)
    gr = gruplar(p)
    grup_tarif = "\n".join(f"GRUP {i + 1}: " + ", ".join(f"{x['ad']} = '{oku_[x['kod']]}'" for x in g) for i, g in enumerate(gr))
    son = oku("para-son-espriler.json", [])[-8:]
    son_kanca = oku("para-son-kancalar.json", [])[-8:]
    kanca_tur = KANCA_TURLERI[len(oku("para-bolumler.json", [])) % len(KANCA_TURLERI)]
    mz = mizah_sec("para")
    istem = f"""Bütçe Kliniği, Gün {gun}.
{'Seçilen yorum (@' + k['kullanici'] + ', ' + str(k['begeni']) + ' beğeni): "' + k['yorum'] + '"' if k['kaynak'] == 'yorum' else 'Bugün örnek bir bütçe (gerçek kişi değil; "yorumlardan geldi" DEME, "bugünün örnek bütçesi" de).'}
Durum: {ozet(k)}. Hedef: {k.get('hedef') or '-'}.
{'BU MAAŞ 2026 NET ASGARİ ÜCRET (yirmi sekiz bin yetmiş beş lira). Kancada "asgari ücret" de; asgari ücretliyi küçümseme, durumu esprili ama saygılı anlat.' if (k.get('asgari') or k['maas'] == ASGARI) else ''}
Maaş: '{oku_['maas']}'. {('Kira: ' + repr(oku_.get('kira')) + ', maaşın ' + repr(oku_.get('kira_orani')) + "'i.") if p.get('kira_orani') else ''}
Bütçe durumu: {p['durum']} ({'aylık açık ' + repr(oku_['acik']) if p['acik'] else 'kenara aylık ' + repr(oku_['kenara_ay']) + ', yıllık ' + repr(oku_['kenara_yil'])}).
KALEMLER (her grup için tam bir cümle; okunuşları HARFİ HARFİNE kullan, rakam yazma):
{grup_tarif}
Son bölümlerin esprileri (tekrar etme): {json.dumps(son, ensure_ascii=False)}
BU BÖLÜMÜN KANCA TÜRÜ: {kanca_tur}
{mizah_metni(mz)}
Son bölümlerin kancaları (kalıbını da kelimelerini de TEKRAR ETME): {json.dumps(son_kanca, ensure_ascii=False)}
Şu JSON şemasını doldur (yalnız JSON):
{SEMA}"""
    sistem = "Sen Cüzdan Hocası'sın: konuşan, neşeli, biraz telaşlı bir cüzdan. Kısa Reels anlatımı yazarsın. Kurallara harfiyen uy.\n\n" + kurallar()
    sorunlar = []
    for deneme in range(3):
        try:
            s = json_sor(sistem, istem + ("" if not sorunlar else f"\nÖnceki denemede sorunlar vardı, düzelt: {sorunlar}"), 0.9)
        except Exception as ex:  # noqa: BLE001
            gunluk(f"para senaryo yazılamadı: {ex}"); break
        sorunlar = denetle(s, p, oku_)
        if not sorunlar:
            s["_kaynak"] = "gemini"; s["_mizah"] = mz; return s
        gunluk(f"para senaryo denetimi: {sorunlar}")
    gunluk("para: yedek senaryo")
    return yedek(k, p, gun)


def yedek(k: dict, p: dict, gun: int) -> dict:
    o = butce.okunuslar(p)
    kanca = f"{o['maas'].replace(' lira', '')} maaş" + (f", {o['kira'].replace(' lira', '')} kira." if p.get("kira_orani") else ".") + " Bu bütçe nefes alır mı?"
    tes = [f"Maaşın {o['kira_orani']} kadarı kiraya gidiyor." if p.get("kira_orani") else "Önce zorunlu giderleri ayıralım.",
           {"iyi": "Cüzdan bugün o kadar mutlu ki fermuarı kendiliğinden ıslık çalıyor.", "orta": "Cüzdan biraz terliyor ama ben sporcuyum, dayanırım.",
            "dar": "Kirayı görünce fermuarım kendiliğinden kapandı.", "acik": "Cüzdan biraz kilo verdi ama birlikte toparlarız."}[p["durum"]]]
    kal = []
    for g in gruplar(p):
        kal.append(", ".join(f"{x['ad'].lower()} için {o[x['kod']]}" for x in g).capitalize() + " ayır.")
    ip = ["Maaş yatar yatmaz önce kenara ayır, sonra harca.", "Ayın yirmisinde makarna değil, rahat bir nefes olsun."] if p["kalan"] > 0 else \
         ["Önce en büyük gideri küçült, sonra küçükleri topla.", "Ben cüzdanım, matematikten korkmam; sadece faturalardan korkarım."]
    sonuc = (f"Ayda {o['kenara_ay']} kenara. Yılda {o['kenara_yil']} eder." if p["kalan"] > 0 else f"Ayda {o['acik']} açık var. Önce bunu kapatalım.")
    kanca = kanca[:1].upper() + kanca[1:]
    return {"_kaynak": "yedek", "kanca": kanca, "teshis": tes, "kalemler": kal, "ipucu": ip, "sonuc": sonuc, "ipucu_kisa": "Önce kenara ayır, sonra harca",
            "baslik": f"{butce.tl(p['maas']).replace(' ₺', '')} ₺ maaşa bütçe", "aciklama": f"{butce.tl(p['maas'])} maaşa bütçe planı – Bütçe Kliniği Gün {gun}\nYorumlardan gelen maaşa zarf zarf bütçe yaptık.",
            "soru": "Sen olsan keyif mi birikim mi?", "etiketler": ["#bütçe", "#birikim", "#paratasarrufu", "#" + re.sub(r"\W", "", (k.get("sehir") or "türkiye").lower()), "#cüzdanhocası"]}


# ---------- video ----------
EK_I = {1: "i", 2: "si", 3: "ü", 4: "ü", 5: "i", 6: "sı", 7: "si", 8: "i", 9: "u", 10: "u", 20: "si", 30: "u", 40: "ı", 50: "si", 60: "ı", 70: "i", 80: "i", 90: "ı"}


def yuzde_ek(n: int) -> str:
    """%44 → %44'ü (iyelik eki, son okunan kelimeye göre)."""
    return f"%{n}'{EK_I.get(n % 10) or EK_I.get(n % 100 // 10 * 10, 'i')}"

RENK = {"kira": "#ff6b4a", "ev": "#ff6b4a", "fatura": "#ffa63d", "mutfak": "#ffd23f", "ulasim": "#7cc6fe", "borc": "#b388ff",
        "acil": "#2ec4b6", "hedef": "#1f9d6b", "keyif": "#ff7eb6"}
IKON = {"kira": "🏠", "ev": "🏠", "fatura": "💡", "mutfak": "🛒", "ulasim": "🚌", "borc": "💳", "acil": "🛟", "hedef": "🎯", "keyif": "🎈"}


def yap(k: dict, p: dict | None, s: dict, gun: int, is_dir: pathlib.Path, cikti: pathlib.Path, G: dict | None = None) -> dict:
    is_dir.mkdir(parents=True, exist_ok=True)
    cum = _metinler(s)
    wav = is_dir / "ses.wav"
    benz, bas, kel = 0.0, [], []
    for sesadi in (SES, "Fenrir"):
        seslendir(" ".join(c for _, c in cum), wav, sesadi)
        kel = dok(wav)
        bas, benz = hizala([c for _, c in cum], kel)
        if benz >= 0.62:
            break
        gunluk(f"para: {sesadi} sesi metinle uyuşmadı ({benz:.2f})")
    if benz < 0.62:
        raise RuntimeError(f"ses metinle uyuşmuyor (benzerlik {benz:.2f})")
    from ortak import sure
    ses_sure = sure(wav)
    Z = {v: t for (v, _), t in zip(cum, bas)}
    C = Z["kapanis"]
    SON = round(max(ses_sure + 1.0, C + 7.5), 2)
    Z["SON"] = SON
    T0 = Z.get("teshis0", 2.5); K0 = Z.get("kalemler0", T0 + 3); I0 = Z.get("ipucu0", K0 + 6); S0 = Z["sonuc"]
    L = []

    def kat(id_, s0, s1, ic, cls="", style="", iz=2):
        L.append(f'      <div id="{id_}" class="clip {cls}" data-start="{s0:.2f}" data-duration="{max(0.1, s1 - s0):.2f}" data-track-index="{iz}"'
                 f'{(" style=" + chr(34) + style + chr(34)) if style else ""}>{ic}</div>')

    G = G or gorsel_butce(k, p, s, gun)
    zaman = {"0": 0.0, "T0": T0, "K0": K0, "I0": I0, "S0": S0, "C": C}
    kat("kanca", 0, T0, G["kanca"], "ust")
    kat("teshis", T0, K0, G["teshis"], "ust")
    # kalemler: satırlar, gruplara göre cümleyle birlikte düşer
    satir, giris_k = [], []
    for gi, g in enumerate(G["gruplar"]):
        t = Z.get(f"kalemler{gi}", K0 + 1.6 * gi)
        for j, x in enumerate(g):
            sid = f"z-{x['kod']}"
            satir.append(f'<div class="zarf" id="{sid}" style="--r:{x["renk"]}"><span class="ik">{x["ikon"]}</span><span class="za">{e(x["ad"])}</span>'
                         f'<span class="zt" data-v="{x["tutar"]}">{e(x.get("metin") or butce.tl(x["tutar"]))}</span></div>')
            giris_k.append([f"#{sid}", "dus", round(t + 0.12 * j + 0.05, 2)])
    yigin = "".join(f'<i id="y-{x["kod"]}" style="width:{max(1, x["yuzde"])}%;background:{x["renk"]}"></i>' for g in G["gruplar"] for x in g)
    kat("kalemler", K0, I0, f'<div class="etiket"><i></i>{e(G["kalem_etiket"])}</div><div class="yigin">{yigin}</div><div class="zarflar">{"".join(satir)}</div>', "ust")
    kat("ipucu", I0, S0, f'<div class="etiket dolu"><i></i>Hocanın ipucu</div><div class="ipkart" id="ipkart"><span class="ampul">💡</span><span>{e(s.get("ipucu_kisa") or "")}</span></div>', "ust")
    sonuc_html = G["sonuc"]
    m_ = re.search(r'id="sayac" data-v="(\d+)"', sonuc_html)
    if m_:   # 6+ haneli tutar 220px'te taşar (kalite denetimi text_box_overflow)
        v_ = int(m_.group(1))
        sinif = "cokuzun" if v_ >= 1_000_000 else "uzun" if v_ >= 100_000 else ""
        sonuc_html = re.sub(r'class="sayac( kirmizi)?" id="sayac"', lambda m: f'class="sayac{m.group(1) or ""} {sinif}" id="sayac"', sonuc_html, count=1)
    kat("sonuc", S0, C, sonuc_html, "ust")
    kat("cta-panel", C, SON, "", iz=11)
    kat("cta", C + 0.2, SON, f'<div class="baslik beyaz" id="cb1">{e(G["cta"][0])}</div><div class="baslik beyaz" id="cb2"><b>{e(G["cta"][1])}</b></div>', "ust ust-cta", iz=12)
    kat("yorum-kutu", C + 2.2, SON, '<div class="av"></div><div id="yorum-yazi"><span id="yorum-ic"></span><span id="imlec"></span></div><div id="okb">↓</div>', iz=12)
    kat("cta-not", C + 4.6, SON, "En çok beğeni alan <b>kazanır!</b>", iz=13)
    kat("marka", C + 0.6, SON, f'<b>Cüzdan Hocası</b><span>{e(G["marka_alt"])}</span>', iz=13)
    for i in range(7):
        t0 = S0 + 0.5 + 0.22 * i
        if t0 + 1.4 < C:
            kat(f"para{i}", t0, t0 + 1.4, "₺", "para", f"left:{[140, 300, 760, 860, 220, 640, 480][i]}px;top:520px", iz=9)
    alt = altyazilar(cum, bas, ses_sure, atla=("kapanis",))
    for i, (t0, d, pr) in enumerate(alt):
        kat(f"y{i:02d}", t0, t0 + d, kelime_html(t0, d, pr), "yazi", iz=20 + i % 2)
    ifadeler = [[zaman[t], f] for t, f in G["ifadeler"]]
    paralar = [[zaman[t] + (0.4 if t == "S0" else 0), n] for t, n in G["paralar"]]
    giris = [["#balon", "salla", 0.45], ["#kanca-et", "zipla", 0.05], ["#c1", "zipla", 0.9], ["#c2", "zipla", 1.3],
             ["#tb", "buyuk", T0 + 0.1], ["#cubuk", "solgun", T0 + 0.3], ["#dolgu", "dolgu", T0 + 0.5], ["#lejant", "solgun", T0 + 1.2],
             ["#ipkart", "dus", I0 + 0.1], ["#sayac", "sayac", S0 + 0.2], ["#cta-panel", "panel", C], ["#cb1", "yukari", C + 0.25], ["#cb2", "buyuk", C + 0.9],
             ["#yorum-kutu", "dus", C + 2.2], ["#okb", "zipzip", C + 2.6], ["#cta-not", "solgun", C + 4.65], ["#marka", "solgun", C + 0.7]] + giris_k + \
            [[f"#para{i}", "para", S0 + 0.5 + 0.22 * i] for i in range(7) if S0 + 0.5 + 0.22 * i + 1.4 < C] + \
            [[f"#y{i:02d} span", "pop", t0] for i, (t0, _, _) in enumerate(alt)]
    zipla = [0.45, T0, K0, I0, S0, C]
    V = {"Z": Z, "ifadeler": ifadeler, "paralar": paralar, "zipla": zipla, "giris": giris, "yorum_yazi": G["yorum_yazi"],
         "flaslar": [[T0, 0.25], [K0, 0.25], [S0, 0.4], [C, 0.3]]}
    maskot = (pathlib.Path(__file__).resolve().parent.parent / "profil/cuzdan/maskot-sablon.svg").read_text()
    proje = hazirla("para", is_dir, {"SURE": f"{SON:.2f}", "KATMANLAR": "\n".join(L), "VERI": json.dumps(V, ensure_ascii=False), "MASKOT": maskot})
    ham = is_dir / "ham.mp4"
    render(proje, ham)
    sfx = [("vurus", 0.45, .5), ("vuus", T0 - 0.05, .45), ("vuus", K0 - 0.05, .45)] + [("vurus", round(g[2], 2), .3) for g in giris_k[:6]] + \
          [("vuus", I0 - 0.05, .45), ("vurus", S0 + 0.2, .6), ("vuus", C - 0.05, .5)]
    miks(ham, wav, sfx, SON, cikti, proje / "assets")
    gunluk(f"para bölümü hazır: {cikti} ({SON:.1f} sn, benzerlik {benz:.2f}, {G.get('log') or p['durum']})")
    return {"sure": SON, "benzerlik": benz, "Z": Z, "proje": str(proje)}


def gorsel_butce(k: dict, p: dict, s: dict, gun: int) -> dict:
    """Bütçe Kliniği sahnelerinin içeriği (para.yap genel şablonuna)."""
    if k["kaynak"] == "yorum":
        bal = (f'<div class="balon" id="balon"><div class="avatar"><span>{e((k["kullanici"] or "?")[:1].upper())}</span></div><div class="bm">'
               f'<div class="balon-kim">@{e(k["kullanici"])}</div><div class="balon-metin">“{e(k["yorum"])}”</div></div>'
               f'<div class="kalp">♥<b>{k["begeni"] or ""}</b></div></div>')
        et = f"Bütçe Kliniği · Gün {gun} · Yorumlardan"
    else:
        bal = f'<div class="balon" id="balon"><div class="bm"><div class="balon-kim">Bugünün örnek bütçesi</div><div class="balon-metin">{e(ozet(k).capitalize())}</div></div></div>'
        et = f"Bütçe Kliniği · Gün {gun}"
    cip = f'<div class="cipler"><span class="cip c-maas" id="c1"><small>{"Asgari ücret" if (k.get("asgari") or p["maas"] == ASGARI) else "Maaş"}</small>{butce.tl(p["maas"])}</span>'
    if p.get("kira_orani"):
        cip += f'<span class="cip c-kira" id="c2"><small>Kira</small>{butce.tl(k["kira"])}</span>'
    cip += "</div>"
    zor_y = round(100 * min(p["zorunlu"], p["maas"]) / p["maas"])
    tbas = (f"Maaşın <b>{yuzde_ek(p['kira_orani'])}</b> kiraya!" if p.get("kira_orani") and p["kira_orani"] >= 30 else f"Zorunlu giderler <b>%{zor_y}</b>")
    kira_mi = bool(p.get("kira_orani"))
    pay_tl = k["kira"] if kira_mi else p["zorunlu"]
    lejant = (f'<div class="lejant" id="lejant"><span><i style="background:#ff5a3c"></i>{"Kira" if kira_mi else "Zorunlu"} {butce.tl(pay_tl)}</span>'
              f'<span><i style="background:#fff"></i>Kalan {butce.tl(p["maas"] - pay_tl)}</span></div>')
    teshis = (f'<div class="etiket"><i></i>{e(ozet(k))}</div><div class="baslik" id="tb">{tbas}</div>'
              f'<div class="cubuk" id="cubuk"><div class="dolgu" id="dolgu" style="width:{min(100, p["kira_orani"] or zor_y)}%"></div>'
              f'<span class="cl">{butce.tl(p["maas"])}</span></div>{lejant}')
    gr = [[{**x, "renk": RENK[x["kod"]], "ikon": IKON[x["kod"]]} for x in g] for g in gruplar(p)]
    if p["kalan"] > 0:
        son = (f'<div class="etiket"><i></i>Ayda {butce.tl(p["kenara_ay"])} kenara</div><div class="sayac-ust">Bir yılda</div>'
               f'<div class="sayac" id="sayac" data-v="{p["kenara_yil"]}">0 ₺</div>')
    else:
        son = f'<div class="etiket"><i></i>Bütçe açığı</div><div class="sayac-ust">Her ay</div><div class="sayac kirmizi" id="sayac" data-v="{p["acik"]}">0 ₺</div>'
    son += '<div class="uyari">Genel bütçe önerisidir, yatırım tavsiyesi değildir.</div>'
    return {"kanca": f'<div class="etiket dolu" id="kanca-et"><i></i>{e(et)}</div>{bal}{cip}', "teshis": teshis, "gruplar": gr,
            "kalem_etiket": "Zarf zarf bölüyoruz", "sonuc": son, "cta": ("Sıradaki bütçe", "senin olsun!"), "yorum_yazi": "Maaş + kira + şehir",
            "marka_alt": "Her gün bir bütçe",
            "ifadeler": [("0", "sok" if p["durum"] in ("dar", "acik") else "hesap"), ("T0", p["ifade"]), ("K0", "hesap"), ("I0", "kirp"),
                         ("S0", "uzgun" if p["kalan"] <= 0 else "mutlu"), ("C", "mutlu")],
            "paralar": [("0", p["para"]), ("S0", min(4, p["para"] + 1) if p["kalan"] > 0 else 0), ("C", 3)], "log": f"durum {p['durum']}"}


def ilk_satir(k: dict, p: dict) -> str:
    """Açıklamanın 'daha fazla' öncesi görünen ilk satırı: rakamlı, merak uyandıran, her gün farklı kalıp."""
    m = butce.tl(p["maas"]); kira = butce.tl(k["kira"]) if p.get("kira_orani") else None
    n = len(oku("para-bolumler.json", []))
    if p["kalan"] <= 0:
        sec = [f"{m} maaş, her ay {butce.tl(p['acik'])} açık. Çıkış yolu var mı?", f"{m} maaşla ay sonu gelmiyor. Zarf zarf baktık 👇"]
    else:
        sec = [f"{m} maaş{', ' + kira + ' kira' if kira else ''}: bu bütçe yeter mi?",
               f"{m} maaştan yılda {butce.tl(p['kenara_yil'])} kenara nasıl ayrılır?",
               f"Maaşın {yuzde_ek(p['kira_orani'])} kiraya gidiyorsa bunu izle 👇" if p.get("kira_orani") else f"{m} maaşı zarf zarf böldük 👇",
               f"{m} maaş: kira, mutfak, birikim… hepsi tek ekranda 👇"]
    return sec[n % len(sec)]


def aciklama(s: dict, k: dict, ai: bool, p: dict | None = None) -> str:
    etk = " ".join([x if x.startswith("#") else "#" + x for x in s.get("etiketler", [])][:5])
    soru = (s.get("soru") or "Sen olsan keyif mi birikim mi?").strip()
    ilk = ilk_satir(k, p) if p else s.get("aciklama", "").strip()
    govde = "\n".join(s.get("aciklama", "").strip().splitlines()[1:]).strip()
    par = [ilk, govde, "", f"🤔 {soru} Yorumlara tek kelime yaz 👇",
           "📌 Kaydet: maaş günü bu zarfları kendin de ayır.", "",
           "💬 Sıradaki bütçe senin olsun: yorumlara maaşını, kiranı ve şehrini yaz. En çok beğeni alan kazanır."]
    if k.get("kaynak") == "yorum" and k.get("kullanici"):
        par.append(f"Bugünün bütçesi: @{k['kullanici']} (yorumuyla seçildi, {k['begeni']} beğeni)")
    par.append("Maaşı yetmeyen bir arkadaşın varsa bu videoyu ona gönder.")
    par.append("Genel bütçe önerisidir, yatırım tavsiyesi değildir.")
    if ai:
        par.append("Seslendirme yapay zekâ ile yapılmıştır.")
    par += ["", etk]
    return "\n".join(par)[:2150]


def metinler(s: dict) -> list[str]:
    return [c for _, c in _metinler(s)]


if __name__ == "__main__":
    k = {"kaynak": "yorum", "yorum": "45 bin maaş, İstanbul'da 20 bin kira, evliyim. Nasıl yeteceğim?", "kullanici": "deneme_kullanici", "begeni": 37,
         "maas": 45000, "kira": 20000, "konut": "kira", "sehir": "İstanbul", "hane": "evli", "cocuk": 0, "borc": 0, "hedef": ""}
    p = butce.plan(k["maas"], k["kira"], k["konut"], k["hane"], k["cocuk"], k["borc"])
    print(json.dumps(yedek(k, p, 1), ensure_ascii=False, indent=1))
