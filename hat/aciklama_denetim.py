"""MCHT ortak açıklama denetçisi — her sosyal medya hattı paylaşmadan ÖNCE çağırır.

Kullanıcı isteği (2026-11-27): "tüm hesaplarda açıklamalar yazım hatasız, SEO uyumlu, yazım kurallarına uygun,
dikkat çekici olsun ve bundan sonra hep kontrol edilsin".

    from aciklama_denetim import denetle
    sonuc = denetle(metin, platform="instagram", gecmis=[eski açıklamalar], llm=metin_duzelt_fonksiyonu)
    sonuc["metin"]      -> düzeltilmiş açıklama (her zaman kullanılabilir)
    sonuc["hatalar"]    -> düzeltilemeyen sorunlar (ör. tekrar) — hat kendi kararını verir
    sonuc["duzeltmeler"]-> yapılan değişikliklerin listesi (panel/log için)

Kural katmanı bağımsızdır (yalnız standart kütüphane). llm verilirse (Gemini/Groq gibi ücretsiz bir metin
fonksiyonu: istem -> yanıt metni) TDK yazım/noktalama düzeltmesi yapar; rakam, telefon, bağlantı ya da hashtag
değiştiren LLM çıktısı REDDEDİLİR (yalnız yazım düzeltilir, anlam değişmez).
Bu dosyanın kopyaları hatlarda durur; kaynak: ~/Documents/mcht-aciklama-denetim (değişince hepsine kopyala).
"""
from __future__ import annotations

import json
import re
import unicodedata

SURUM = "2026-11-27"

# platform -> (azami karakter, azami hashtag, asgari hashtag)
SINIR = {"instagram": (2200, 5, 3), "facebook": (5000, 5, 0), "tiktok": (2200, 5, 3), "youtube": (5000, 5, 0)}

# Sık yapılan, anlamı belirsiz olmayan yazım hataları (TDK). Yalnız kelime sınırında değiştirilir.
YAZIM = {
    "cerceve": "çerçeve", "Cerceve": "Çerçeve",
    "herkez": "herkes", "Herkez": "Herkes",
    "yanlız": "yalnız", "Yanlız": "Yalnız",
    "birsey": "bir şey", "birşey": "bir şey", "Birşey": "Bir şey",
    "herşey": "her şey", "Herşey": "Her şey",
    "hiçbirşey": "hiçbir şey",
    "malesef": "maalesef", "Malesef": "Maalesef",
    "yada": "ya da",
    "şuanda": "şu anda", "Şuanda": "Şu anda",
    "pekçok": "pek çok", "Pekçok": "Pek çok",
    "orjinal": "orijinal", "Orjinal": "Orijinal",
    "sürpriz": "sürpriz",
    "eşortman": "eşofman",
    "kirpik": "kirpik",
    "nikah": "nikâh", "Nikah": "Nikâh",
}
# bağlama göre: "sis hakim" -> "sis hâkim" (hakim = yargıç)
BAGLAM = [(re.compile(r"\b(sis|soğuk|hava|sessizlik|huzur|kontrol)\s+hakim\b", re.I), lambda m: m.group(1) + " hâkim")]

SORU_EKI = re.compile(r"\b(nasıl|neden|niye|ne|neler|nerede|nereden|hangi|hangisi|kim|kaç|mı|mi|mu|mü|mısın|misin|musun|müsün|mıyım|miyim)\b", re.I)
URL = re.compile(r"(https?://\S+|\b[\w-]+\.(?:com|com\.tr|tr|net|org)(?:/\S*)?)", re.I)
TEL = re.compile(r"\+?\d[\d\s]{8,}\d")
HASHTAG = re.compile(r"#[\wçğıöşüÇĞİÖŞÜâîû]+", re.U)
SAYI = re.compile(r"\d+(?:[.,]\d+)*")


def _tr_buyuk(c: str) -> str:
    return {"i": "İ", "ı": "I"}.get(c, c.upper())


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFC", t or "").lower()
    return re.sub(r"[^\wçğıöşü]+", " ", t).strip()


def benzerlik(a: str, b: str) -> float:
    x, y = set(_norm(a).split()), set(_norm(b).split())
    return len(x & y) / max(1, min(len(x), len(y))) if x and y else 0.0


def kurallar(metin: str, platform: str = "instagram", gecmis: list[str] | None = None) -> dict:
    """Kod düzeltmeleri: güvenli olanları uygular, kalanları hata olarak döndürür."""
    azami, etiket_azami, etiket_asgari = SINIR.get(platform, SINIR["instagram"])
    d, h = [], []
    t = unicodedata.normalize("NFC", (metin or "").replace("\r", "")).strip()

    # 1) Yazım sözlüğü + bağlam
    for yanlis, dogru in YAZIM.items():
        if yanlis != dogru:
            yeni = re.sub(rf"(?<![\wçğıöşü]){re.escape(yanlis)}(?![\wçğıöşü])", dogru, t)
            if yeni != t:
                d.append(f"yazım: {yanlis} → {dogru}"); t = yeni
    for desen, f in BAGLAM:
        yeni = desen.sub(f, t)
        if yeni != t:
            d.append("yazım: hakim → hâkim"); t = yeni

    satirlar = t.split("\n")
    temiz = []
    for s in satirlar:
        s0 = s
        s = re.sub(r"[ \t]{2,}", " ", s).rstrip()
        # 2) Kesik satır ("…" ile biten, liste/metin) -> son tam cümleye kadar kırp, olmazsa satırı at
        if re.search(r"(…|\.\.\.)\s*$", s) and not re.search(r"(…|\.\.\.)\s*\S+$", s):
            govde = re.sub(r"\s*(…|\.\.\.)\s*$", "", s)
            if re.search(r"[.!?]", govde):
                govde = re.sub(r"(.*[.!?]).*$", r"\1", govde)
                d.append(f"kesik satır kırpıldı: {s0[:40]}…"); s = govde
            elif govde.lstrip().startswith(("✔", "•", "-", "👉", "✅")):
                d.append(f"kesik liste satırı çıkarıldı: {s0[:40]}…"); continue
            else:
                h.append(f"yarım kalan satır: {s0[:60]}"); s = govde
        # 3) Aynı satırda iki "iki nokta" (ör. "ekleyin: başvuru profildeki linkte: site")
        if s.count(": ") >= 2 and not URL.search(s.split(": ")[0]):
            parcalar = s.split(": ")
            s = parcalar[0] + ": " + " — ".join(parcalar[1:]) if len(parcalar) > 2 else s
            s = s.replace(" — ", ", ")
            d.append("çift iki nokta düzeltildi")
        # 4) Soru cümlesi soru işaretsiz bitiyorsa ("… önlüyorsun Yorumlara yaz")
        m = re.match(r"^(.*?\b\w+)\s+(Yorumlara yaz.*|Yoruma yaz.*|Yorumlarda buluşalım.*)$", s)
        if m and SORU_EKI.search(m.group(1)) and not m.group(1).rstrip().endswith("?"):
            s = m.group(1).rstrip() + "? " + m.group(2); d.append("soru işareti eklendi")
        elif SORU_EKI.search(s) and re.search(r"\b(mı|mi|mu|mü|musun|misin|mısın|müsün)\s*$", s):
            s += "?"; d.append("soru işareti eklendi")
        temiz.append(s)
    t = "\n".join(temiz)
    t = re.sub(r"\n{3,}", "\n\n", t).strip()

    # 5) İlk harf büyük (Türkçe i → İ); bağlantı/hashtag/emoji ile başlıyorsa dokunma
    ilk = re.search(r"[A-Za-zÇĞİÖŞÜçğıöşü]", t)
    if ilk and t[ilk.start()].islower() and not URL.match(t[ilk.start():]) and ilk.start() < 3:
        t = t[:ilk.start()] + _tr_buyuk(t[ilk.start()]) + t[ilk.start() + 1:]; d.append("ilk harf büyütüldü")

    # 6) Cümle ortasında gereksiz büyük harf ("Sitenize Teklif formu ekleyin")
    def kucult(m):
        return m.group(1) + m.group(2).lower() + m.group(3)
    yeni = re.sub(r"(\b[a-zçğıöşü]\w+ )([A-ZÇĞİÖŞÜ][a-zçğıöşü]+)( [a-zçğıöşü]+\b)", kucult, t)
    # özel adları (Google, Instagram, WhatsApp, Sakarya…) koru
    if yeni != t:
        korunan = ("Google", "Instagram", "WhatsApp", "Facebook", "TikTok", "YouTube", "Sakarya", "Adapazarı", "Sapanca",
                   "Türkiye", "Mücahit", "Muhit", "Bakanlık", "Marka", "Site", "Mucidi", "Dijital", "Çırak")
        parcalar = []
        for a, b in zip(t.split(" "), yeni.split(" ")):
            parcalar.append(a if a.strip(".,!?:;'’") in korunan else b)
        yeni = " ".join(parcalar) if len(t.split(" ")) == len(yeni.split(" ")) else t
        if yeni != t:
            d.append("cümle ortası büyük harf küçültüldü"); t = yeni

    # 7) Hashtag: yalnız # ile yazılanlar, kesik/tekrar yok, azami sayı
    etiketler = HASHTAG.findall(t)
    gorulen, tut = set(), []
    for e in etiketler:
        k = e.lower()
        if k in gorulen or len(e) < 4:
            d.append(f"hashtag çıkarıldı: {e}"); continue
        gorulen.add(k); tut.append(e)
    if len(tut) > etiket_azami:
        d.append(f"hashtag sayısı {len(tut)} → {etiket_azami}"); tut = tut[:etiket_azami]
    if len(tut) < etiket_asgari:
        h.append(f"hashtag az ({len(tut)}); {etiket_asgari}-{etiket_azami} arası olmalı")
    govde = HASHTAG.sub("", t)
    # '#' unutulmuş etiket satırı: "İşletmeGeliştirme Girişimcilik Keşfet" (Büyük harfle başlayan bitişik kelime dizisi)
    govde_satir = []
    for s in govde.split("\n"):
        kelimeler = s.split()
        if len(kelimeler) >= 3 and all(re.fullmatch(r"[A-ZÇĞİÖŞÜ][\wçğıöşü]+", k) for k in kelimeler) and any(
                re.search(r"[a-zçğıöşü][A-ZÇĞİÖŞÜ]", k) for k in kelimeler):
            d.append("'#' unutulmuş etiket satırı çıkarıldı"); continue
        govde_satir.append(s.rstrip())
    govde = re.sub(r"\n{3,}", "\n\n", "\n".join(govde_satir)).strip()
    t = govde + ("\n\n" + " ".join(tut) if tut else "")

    # 8) Uzunluk: asla kelime/hashtag ortasından kesme — önce hashtag, sonra son paragraf at
    while len(t) > azami and tut:
        tut.pop(); t = govde + ("\n\n" + " ".join(tut) if tut else ""); d.append("uzunluk için hashtag çıkarıldı")
    if len(t) > azami:
        h.append(f"açıklama çok uzun ({len(t)}>{azami})")

    # 9) Tekrar: son 14 günün açıklamalarına %85+ benzerlik
    for eski in gecmis or []:
        if benzerlik(govde, HASHTAG.sub("", eski)) >= 0.85:
            h.append("açıklama son paylaşımlardan biriyle neredeyse aynı (tekrar)"); break

    # 10) İlk satır (kanca) kontrolü
    ilk_satir = next((s for s in t.split("\n") if s.strip()), "")
    if len(ilk_satir) > 125:
        h.append("ilk satır 125 karakteri aşıyor (Instagram '…devamı' kesiminde kanca görünmez)")
    if HASHTAG.match(ilk_satir.strip()) or URL.match(ilk_satir.strip()):
        h.append("ilk satır hashtag/bağlantıyla başlıyor (kanca yok)")
    return {"metin": t, "duzeltmeler": d, "hatalar": h}


LLM_ISTEM = """Aşağıdaki sosyal medya açıklamasını YALNIZCA Türkçe yazım ve noktalama açısından düzelt (TDK kuralları):
yazım yanlışları, eksik/yanlış harf (ç, ğ, ı, ö, ş, ü, â), bitişik/ayrı yazım (de/da, ki, mi), büyük-küçük harf,
soru işareti, virgül, çift boşluk. Anlamı, tonu, emojileri, satır düzenini, rakamları, telefon numaralarını,
bağlantıları ve hashtag'leri DEĞİŞTİRME; cümle ekleme ya da çıkarma. Bozuk bir kalıp cümle varsa (ör. "Yapay zekâda
görünmek arıyorsanız") en az değişiklikle dil bilgisine uygun hâle getir ("Yapay zekâda görünmek istiyorsanız").
YALNIZCA şu JSON'u döndür: {{"metin": "<düzeltilmiş açıklama>", "degisiklikler": ["eski → yeni", ...]}}

AÇIKLAMA:
{metin}"""


def _koruma_izi(t: str) -> tuple:
    return (sorted(SAYI.findall(HASHTAG.sub("", URL.sub("", t)))), sorted(URL.findall(t)), sorted(e.lower() for e in HASHTAG.findall(t)))


def llm_duzelt(metin: str, llm) -> tuple[str, list[str]]:
    """LLM ile TDK düzeltmesi; rakam/bağlantı/hashtag değiştiyse ya da yanıt bozuksa orijinali döndürür."""
    try:
        yanit = llm(LLM_ISTEM.format(metin=metin))
        yanit = re.sub(r"^```(?:json)?|```$", "", (yanit or "").strip(), flags=re.M).strip()
        j = json.loads(yanit)
        if isinstance(j, list):
            j = j[0]
        yeni = unicodedata.normalize("NFC", j["metin"]).strip()
    except Exception as e:  # noqa: BLE001
        return metin, [f"(LLM düzeltmesi yapılamadı: {type(e).__name__})"]
    if not yeni or abs(len(yeni) - len(metin)) > max(40, len(metin) * 0.15):
        return metin, ["(LLM çıktısı uzunluğu çok değiştirdi, reddedildi)"]
    if _koruma_izi(yeni) != _koruma_izi(metin):
        return metin, ["(LLM rakam/bağlantı/hashtag değiştirdi, reddedildi)"]
    if benzerlik(yeni, metin) < 0.8:
        return metin, ["(LLM anlamı değiştirdi, reddedildi)"]
    return yeni, [f"yazım (LLM): {x}" for x in (j.get("degisiklikler") or [])[:12]] if yeni != metin else []


def denetle(metin: str, platform: str = "instagram", gecmis: list[str] | None = None, llm=None) -> dict:
    """Önce kod kuralları, sonra (varsa) LLM yazım düzeltmesi, sonra kurallar tekrar (LLM'in bozduğunu düzeltir)."""
    r = kurallar(metin, platform, gecmis)
    duz = list(r["duzeltmeler"])
    if llm:
        yeni, ld = llm_duzelt(r["metin"], llm)
        duz += ld
        if yeni != r["metin"]:
            r2 = kurallar(yeni, platform, gecmis)
            duz += [x for x in r2["duzeltmeler"] if x not in duz]
            r = {"metin": r2["metin"], "hatalar": r2["hatalar"]}
    return {"metin": r["metin"], "duzeltmeler": duz, "hatalar": r["hatalar"], "surum": SURUM}


if __name__ == "__main__":  # hızlı deneme: python3 aciklama_denetim.py < metin.txt
    import sys
    print(json.dumps(denetle(sys.stdin.read()), ensure_ascii=False, indent=1))
