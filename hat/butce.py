"""Cüzdan Hocası bütçe motoru: yorumdaki maaş/kira/hane bilgisinden zarf (kalem) planı çıkarır.
Bütün rakamları KOD hesaplar (model rakam uydurmaz). Kalemler "harcarsın" değil "ayır" önerisidir: fiyat iddiası yok.
Yatırım tavsiyesi verilmez; birikim yalnız "kenara ayır" olarak geçer."""
from __future__ import annotations

BIRLER = ["", "bir", "iki", "üç", "dört", "beş", "altı", "yedi", "sekiz", "dokuz"]
ONLAR = ["", "on", "yirmi", "otuz", "kırk", "elli", "altmış", "yetmiş", "seksen", "doksan"]


def _uc(n: int) -> str:
    y, o, b = n // 100, (n // 10) % 10, n % 10
    return ((("" if y == 1 else BIRLER[y] + " ") + "yüz ") if y else "") + ((ONLAR[o] + " ") if o else "") + BIRLER[b]


def yazi(n: int) -> str:
    """Türkçe sayı okunuşu: 45250 → 'kırk beş bin iki yüz elli'."""
    n = int(round(n))
    if n == 0:
        return "sıfır"
    eksi = n < 0; n = abs(n); parcalar = []
    for ad, bol in (("milyon", 10**6), ("bin", 10**3)):
        q, n = divmod(n, bol)
        if q:
            parcalar.append(("" if (ad == "bin" and q == 1) else _uc(q).strip() + " ") + ad)
    if n:
        parcalar.append(_uc(n).strip())
    s = " ".join(p.strip() for p in parcalar).replace("  ", " ")
    return ("eksi " if eksi else "") + s


def tl(n: int) -> str:
    """Ekranda: 45.250 ₺"""
    return f"{int(round(n)):,}".replace(",", ".") + " ₺"


def yuvarla(n: float, maas: int) -> int:
    adim = 100 if maas < 30000 else 250 if maas < 100000 else 500
    return int(round(n / adim) * adim)


def taban() -> dict:
    """Gerçek fiyat alt sınırları (icerik/fiyat-tabani.json, TÜRK-İŞ verisiyle aylık güncellenir)."""
    import json
    import pathlib
    try:
        return json.loads((pathlib.Path(__file__).resolve().parent.parent / "icerik/fiyat-tabani.json").read_text())
    except Exception:  # noqa: BLE001
        return {}


def plan(maas: int, kira: int | None = None, konut: str = "kira", hane: str = "bekar", cocuk: int = 0, borc: int = 0) -> dict:
    """konut: kira | ev_sahibi | aile. kira None + konut=kira → oranla 'ev payı' (kiran yazılmadı).
    2026-11-27: kalemler artık max(maaş yüzdesi, gerçek fiyat tabanı) — sabit yüzde mutfak/faturayı gerçek dışı düşük gösteriyordu."""
    if not 5000 <= maas <= 1_000_000:
        raise ValueError("maaş aralık dışı")
    T = taban()
    yetiskin = 2 if hane == "evli" else 1
    cocuk = min(int(cocuk or 0), 4)
    fatura_t = T.get("fatura_aile" if (yetiskin + cocuk) > 1 else "fatura_bekar", 0)
    k = []   # (kod, ad, tutar, not)
    if konut == "kira" and kira:
        k.append(("kira", "Kira", int(kira), ""))
        k.append(("fatura", "Faturalar", max(yuvarla(maas * 0.08, maas), fatura_t), ""))
    elif konut == "kira":
        k.append(("ev", "Kira + fatura payı", yuvarla(maas * 0.38, maas), "kira yazılmadığı için oran"))
    else:
        k.append(("fatura", "Faturalar + aidat", max(yuvarla(maas * 0.10, maas), fatura_t), ""))
    mutfak_oran = {"bekar": 0.17, "evli": 0.22}.get(hane, 0.17) + 0.04 * min(cocuk, 3)
    mutfak_t = T.get("mutfak_yetiskin", 0) * yetiskin + T.get("mutfak_cocuk", 0) * cocuk
    k.append(("mutfak", "Mutfak", max(yuvarla(maas * mutfak_oran, maas), mutfak_t), ""))
    k.append(("ulasim", "Ulaşım", max(yuvarla(maas * 0.07, maas), T.get("ulasim", 0)), ""))
    if borc:
        k.append(("borc", "Kredi / kart taksiti", int(borc), ""))
    zorunlu = sum(x[2] for x in k)
    kalan = maas - zorunlu
    if kalan > 0:
        acil = yuvarla(kalan * 0.40, maas); hedef = yuvarla(kalan * 0.35, maas); keyif = kalan - acil - hedef
        k += [("acil", "Acil durum fonu", acil, ""), ("hedef", "Birikim", hedef, ""), ("keyif", "Keyif", keyif, "")]
    oran = kalan / maas
    durum = "iyi" if oran >= 0.25 else "orta" if oran >= 0.12 else "dar" if oran >= 0 else "acik"
    if durum in ("iyi", "orta") and hane != "evli" and konut == "kira" and maas < T.get("bekar_yasama_maliyeti", 0):
        durum = "dar" if durum == "orta" else "orta"   # TÜRK-İŞ bekar yaşama maliyetinin altındaysa "rahat" denmez
    ifade = {"iyi": "mutlu", "orta": "hesap", "dar": "sok", "acik": "uzgun"}[durum]
    para = {"iyi": 4, "orta": 3, "dar": 1, "acik": 0}[durum]
    kenara = sum(x[2] for x in k if x[0] in ("acil", "hedef"))
    kira_orani = round(100 * kira / maas) if kira else None
    return {"maas": maas, "kalemler": [{"kod": a, "ad": b, "tutar": c, "not": d, "yuzde": round(100 * c / maas)} for a, b, c, d in k],
            "zorunlu": zorunlu, "kalan": kalan, "acik": max(0, -kalan), "durum": durum, "ifade": ifade, "para": para,
            "kenara_ay": kenara, "kenara_yil": kenara * 12, "kira_orani": kira_orani}


def okunuslar(p: dict) -> dict:
    """Senaryo yazarına verilecek: her tutarın yazıyla okunuşu (TTS için rakam yok)."""
    o = {"maas": yazi(p["maas"]) + " lira", "kenara_ay": yazi(p["kenara_ay"]) + " lira", "kenara_yil": yazi(p["kenara_yil"]) + " lira",
         "acik": yazi(p["acik"]) + " lira"}
    for x in p["kalemler"]:
        o[x["kod"]] = yazi(x["tutar"]) + " lira"
    if p.get("kira_orani"):
        o["kira_orani"] = "yüzde " + yazi(p["kira_orani"])
    return o


if __name__ == "__main__":
    import json
    for a in [dict(maas=45000, kira=20000, hane="evli"), dict(maas=28000, konut="aile"), dict(maas=80000, kira=25000, hane="evli", cocuk=1),
              dict(maas=22104, kira=14000), dict(maas=60000)]:
        p = plan(**a); print(json.dumps({**a, "durum": p["durum"], "kalemler": [(x["ad"], x["tutar"]) for x in p["kalemler"]], "yil": p["kenara_yil"]}, ensure_ascii=False))
    print(yazi(45250), "|", yazi(1000), "|", yazi(122500), "|", yazi(1_250_000), "|", yazi(100))
