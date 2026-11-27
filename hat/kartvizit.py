"""Kartvizit bölümü: senaryo → ses → hizalama → şablon katmanları + veri → render → miks."""
from __future__ import annotations

import json
import pathlib
import re

import segno

import random

from ortak import gunluk, oku, sure
from senaryo import anlatim
from ses import dok, hizala, seslendir
from uret import e, hazirla, miks, render

DUZENLER = ["yatay", "merkez", "panel", "dev", "minimal", "kose", "serit", "bant", "muhur"]  # 2026-11-27: +serit, bant, mühür
ARKA_MODLAR = ["acik", "ana", "vurgu"]


def duzen_sec(dosya: str = "kartvizit-bolumler.json") -> tuple[str, str]:
    """Kart düzeni son 5 bölümde, arka yüz rengi son bölümde kullanılanı tekrar etmez."""
    kayit = oku(dosya, [])
    son_d = [b.get("duzen") for b in kayit[-5:]]
    son_a = [b.get("arka_mod") for b in kayit[-1:]]
    d = random.choice([x for x in DUZENLER if x not in son_d] or DUZENLER)
    a = random.choice([x for x in ARKA_MODLAR if x not in son_a] or ARKA_MODLAR)
    return d, a


FONT_AD = {"modern": "Inter", "klasik": "Playfair Display", "guclu": "Montserrat", "samimi": "Nunito"}


def ust(s: str) -> str:
    return s.replace("i", "İ").replace("ı", "I").upper()


def monogram(firma: str) -> str:
    k = [w for w in re.split(r"\s+", firma) if w and w[0].isalnum()]
    return ust("".join(w[0] for w in k[:2])) or ust(firma[:1])


def altyazilar(cumleler: list[tuple[str, str]], bas: list[float], son_t: float, atla=("kanca", "kapanis")) -> list[tuple[float, float, str]]:
    out = []
    for i, (v, c) in enumerate(cumleler):
        if v in atla:
            continue
        t0, t1 = bas[i], (bas[i + 1] if i + 1 < len(bas) else son_t) - 0.08
        kel = c.split()
        parca = [" ".join(kel[j:j + 6]) for j in range(0, len(kel), 6)]
        uz = sum(len(p) for p in parca) or 1
        t = t0
        for p in parca:
            d = (t1 - t0) * len(p) / uz
            out.append((round(t, 2), round(max(0.5, d), 2), p)); t += d
    return out


def kelime_html(t0: float, d: float, p: str) -> str:
    """Altyazı parçasını kelime kelime vurgulanacak span'lere böler (data-t = kelimenin mutlak başlangıcı)."""
    import html as _h
    kel = p.split(); uz = sum(len(k) + 1 for k in kel) or 1; t = t0; out = []
    for k in kel:
        out.append(f'<b class="ks" data-t="{t:.2f}">{_h.escape(k)}</b>'); t += d * (len(k) + 1) / uz
    return "<span>" + " ".join(out) + "</span>"


def yap(firma: dict, s: dict, gun: int, yildiz: dict, is_dir: pathlib.Path, cikti: pathlib.Path, duzen: tuple[str, str] | None = None) -> dict:
    is_dir.mkdir(parents=True, exist_ok=True)
    duzen_kod, arka_mod = duzen or duzen_sec()
    cum = anlatim("kartvizit", s)
    metin = " ".join(c for _, c in cum)
    wav = is_dir / "ses.wav"
    seslendir(metin, wav)
    kel = dok(wav)
    bas, benz = hizala([c for _, c in cum], kel)
    if benz < 0.62:
        raise RuntimeError(f"ses metinle uyuşmuyor (benzerlik {benz:.2f})")
    ses_sure = sure(wav)
    ilk = {}
    for (v, _), t in zip(cum, bas):
        ilk.setdefault(v, []).append(t)
    g = lambda v, i=0: ilk[v][min(i, len(ilk[v]) - 1)]  # noqa: E731
    Z = {"T": g("tanitim"), "F0": g("font", 0), "F1": g("font", 1), "F2": g("font", 2), "R0": g("renk", 0), "R1": g("renk", 1), "R2": g("renk", 2),
         "P0": g("perdah", 0), "P1": g("perdah", 1), "A0": g("arka", 0), "A1": g("arka", 1), "M0": g("maket", 0), "M1": g("maket", 1), "C": g("kapanis")}
    Z["SON"] = round(max(ses_sure + 1.0, Z["C"] + 9.2), 2)
    C, SON = Z["C"], Z["SON"]
    kullanici = firma.get("kullanici") or ""
    qr = None
    if kullanici:
        q = segno.make(f"https://www.instagram.com/{kullanici}/", error="m")
        qr = [[1 if c else 0 for c in r] for r in q.matrix]
    satirlar = ([["@", kullanici]] if kullanici else []) + ([["K", firma["sehir"]]] if firma.get("sehir") else []) + [["D", "Bilgi ve sipariş: DM"]]
    renk = s["dogru_renk"]
    perdah_ad = yildiz["ad"]
    fad = FONT_AD.get(s.get("font_stil"), "Inter")
    L = []  # zamanlı katmanlar

    def kat(id_, s0, s1, ic, cls="", style="", iz=2):
        L.append(f'      <div id="{id_}" class="clip {cls}" data-start="{s0:.2f}" data-duration="{max(0.1, s1 - s0):.2f}" data-track-index="{iz}"{(" style=" + chr(34) + style + chr(34)) if style else ""}>{ic}</div>')
    # kanca: seçilen yorum (gerçek kullanıcı adı ve beğeni sayısı)
    if firma.get("kaynak") == "yorum":
        kimlik = f"@{e(kullanici)}"; yorum_m = f"“{e(firma['yorum'])}”"
        kalp = f'<div class="kalp">♥<b>{firma["begeni"]}</b></div>' if firma.get("begeni") else '<div class="kalp">♥</div>'
        et = f"Gün {gun} · Yorumlardan"
    else:
        kimlik = "Bugünün firması"; yorum_m = f"{e(firma['firma'])} · {e(firma['sektor'])}"; kalp = '<div class="kalp">♥</div>'; et = f"Gün {gun} · Kartvizit"
    kat("kanca", 0, Z["T"], f'<div class="etiket dolu" id="kanca-et"><i></i>{e(et)}</div><div class="balon" id="balon"><div class="avatar"><span>{e((kullanici or firma["firma"])[:1].upper())}</span></div><div><div class="balon-kim">{kimlik}</div><div class="balon-metin">{yorum_m}</div></div>{kalp}</div>', "ust")
    cip = f'<span class="cip" id="c1">{e(firma["sektor"])}</span>' + (f'<span class="cip" id="c2">{e(firma["sehir"])}</span>' if firma.get("sehir") else "")
    kat("firma", Z["T"], Z["F0"], f'<div class="etiket"><i></i>Gün {gun} · Kartvizit</div><div class="baslik" id="fb1">Bugünkü firma:</div><div class="baslik" id="fb2"><b>{e(firma["firma"])}</b></div><div class="cipler">{cip}</div>', "ust")
    kat("arac-font", Z["F0"], Z["R0"], f'<small>Yazı tipi</small><span id="f-komik" class="komik">Comic Sans MS</span><span id="f-dogru" style="display:none;align-items:center;gap:12px">{e(fad)} <span class="ok">✓</span></span>', "arac", iz=3)
    kat("damga1", Z["F1"], Z["F2"], "OLMAZ!", "damga", iz=4)
    yanlis = f"linear-gradient(135deg,{s['yanlis_renk'][0]},{s['yanlis_renk'][1]})"
    dogru = f"linear-gradient(135deg,{renk['ana']} 50%,{renk['vurgu']} 50%)"
    kat("arac-renk", Z["R0"], Z["P0"], f'<small>Renk</small><div class="renkler"><i style="background:#2f6fe4"></i><i style="background:{yanlis}"></i><i style="background:#f4c430"></i><i style="background:{dogru}"></i><div class="halka" id="halka"></div></div>', "arac", iz=3)
    kat("damga2", Z["R1"], Z["R2"], "YOK ARTIK!", "damga", iz=4)
    kat("arac-perdah", Z["P0"], Z["A0"], f'<small>Perdah</small>{e(perdah_ad.capitalize())} <span class="ok">✓</span>', "arac", iz=3)
    kat("arac-arka", Z["A0"], Z["M0"], f'<small>Arka yüz</small>{"Instagram + karekod" if qr else "İletişim"} <span class="ok">✓</span>', "arac", iz=3)
    kat("hazir", Z["M0"], C, f'<div class="etiket"><i></i>{e(perdah_ad.capitalize())} · 85×55 mm</div><div class="baslik" id="hzb">Baskıya <b>hazır!</b></div><div class="not">Vitrin tasarımı · firma isterse satın alabilir</div>', "ust")
    ikinci = "yeni bir tasarım!"
    kat("hergun", C, C + 2.55, f'<div class="etiket dolu"><i></i>Her gün · yeni firma · yeni tasarım</div><div class="baslik kucuk" id="hg1">Her gün yeni bir firma,</div><div class="baslik kucuk" id="hg2"><b>{ikinci}</b></div>', "ust")
    kat("cta", C + 2.55, SON, '<div class="etiket"><i></i>Yarın: yeni bölüm</div><div class="baslik" id="cb1">Sıradaki kartvizit</div><div class="baslik" id="cb2"><b>senin olsun!</b></div>', "ust")
    kat("cta-panel", C, SON, "", iz=11)
    kat("yorum-kutu", C + 4.3, SON, '<div class="av"></div><div id="yorum-yazi"><span id="yorum-ic">Firma adı + sektör</span><span id="imlec"></span></div><div id="okb">↓</div>', iz=12)
    L.append(f'      <img id="cta-logo" class="clip" src="assets/logo-tam-beyaz.png" alt="Mchttasarım" data-start="{C + 1.0:.2f}" data-duration="{SON - C - 1.0:.2f}" data-track-index="14" />')
    kat("cta-not", C + 6.7, SON, "En çok beğeni alan <b>kazanır!</b>", iz=13)
    kalpler = []
    for i in range(6):
        kid = f"k{i + 1}"; t0 = C + 5.0 + 0.55 * i
        if t0 + 1.7 <= SON:
            kat(kid, t0, t0 + 1.7, "♥", "kalp2", f"left:{[820, 760, 840, 780, 830, 770][i]}px;top:{[1020, 1030, 1010, 1025, 1015, 1030][i]}px", iz=15 + i % 2); kalpler.append((f"#{kid}", "kalp", t0))
    alt = altyazilar(cum, bas, ses_sure)
    for i, (t0, d, p) in enumerate(alt):
        kat(f"y{i:02d}", t0, t0 + d, kelime_html(t0, d, p), "yazi", iz=20 + i % 2)
    giris = [["#balon", "salla", 0.55], ["#kanca-et", "zipla", 0.05], ["#fb1", "yukari", Z["T"] + 0.4], ["#fb2", "buyuk", Z["T"] + 1.2], ["#c1", "zipla", Z["T"] + 1.8], ["#c2", "zipla", Z["T"] + 2.1],
             ["#arac-font", "dus", Z["F0"] + 0.05], ["#damga1", "damga", Z["F1"]], ["#f-komik", "gizle", Z["F2"]], ["#f-dogru", "goster", Z["F2"]],
             ["#arac-renk", "dus", Z["R0"] + 0.05], ["#halka", "halka", Z["R1"], 76], ["#damga2", "damga", Z["R1"]], ["#halka", "halka", Z["R2"], 228],
             ["#arac-perdah", "dus", Z["P0"] + 0.05], ["#arac-arka", "dus", Z["A0"] + 0.05], ["#hzb", "buyuk", Z["M0"] + 0.1],
             ["#hg1", "yukari", C + 0.05], ["#hg2", "buyuk", C + 1.55], ["#cta-panel", "panel", C], ["#cta-logo", "solgun", C + 1.0], ["#cb1", "yukari", C + 2.6], ["#cb2", "buyuk", C + 3.66],
             ["#yorum-kutu", "dus", C + 4.3], ["#okb", "zipzip", C + 4.7], ["#cta-not", "solgun", C + 6.75]] + kalpler + [[f"#y{i:02d} span", "pop", t0] for i, (t0, _, _) in enumerate(alt)]
    flaslar = [[0.55, 0.45], [Z["T"], 0.3], [Z["F0"], 0.3], [Z["R2"], 0.3], [Z["P0"], 0.35], [Z["A0"], 0.25], [Z["M0"], 0.7], [C, 0.3]]
    V = {"Z": Z, "firma": firma["firma"], "sektor": firma["sektor"], "slogan": s.get("slogan") or "", "monogram": monogram(firma["firma"]),
         "font_stil": s.get("font_stil", "modern"), "perdah": yildiz["kod"], "duzen": duzen_kod, "arka_mod": arka_mod, "renk": renk, "yanlis_renk": s["yanlis_renk"],
         "arka_satirlar": satirlar, "qr": qr, "flaslar": flaslar, "giris": giris}
    L = [x.replace('class="clip damga"', 'class="clip damga" data-layout-allow-occlusion') for x in L]   # flaş anında kasıtlı örtüşme
    proje = hazirla("kartvizit", is_dir, {"SURE": f"{SON:.2f}", "KATMANLAR": "\n".join(L), "VERI": json.dumps(V, ensure_ascii=False)})
    ham = is_dir / "ham.mp4"
    render(proje, ham)
    sfx = [("vurus", 0.55, .55), ("vuus", Z["T"] - 0.05, .5), ("vuus", Z["F0"] - 0.05, .5), ("vurus", Z["F1"], .55), ("vurus", Z["R1"], .55),
           ("vuus", Z["R2"] - 0.05, .5), ("vurus", Z["P0"], .6), ("vuus", Z["A0"], .5), ("vurus", Z["M0"], .6), ("vuus", C - 0.05, .5)]
    miks(ham, wav, sfx, SON, cikti, proje / "assets")
    gunluk(f"kartvizit bölümü hazır: {cikti} ({SON:.1f} sn, benzerlik {benz:.2f}, düzen {duzen_kod}/{arka_mod})")
    return {"duzen": duzen_kod, "arka_mod": arka_mod, "sure": SON, "benzerlik": benz, "Z": Z, "proje": str(proje)}
