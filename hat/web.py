"""Web sitesi bölümü: Site Mucidi motoruyla site (yayına alınmaz) → katmanlar → senaryo sesi → şablon → render → miks."""
from __future__ import annotations

import json
import os
import pathlib
import subprocess

from kartvizit import altyazilar, kelime_html
from ortak import ff, gunluk, sure
from senaryo import anlatim
from ses import dok, hizala, seslendir
from uret import e, hazirla, miks, render

SM = pathlib.Path(os.environ.get("SITE_MUCIDI", str(pathlib.Path.home() / "Documents/mcht-web-studio")))
SEKTOR_AD = {"kurumsal-firma": "kurumsal firma", "sanayi-uretim": "fabrika", "yerel-hizmet": "tamirci", "otomotiv": "oto servis", "restoran-kafe": "restoran",
             "saglik-klinik": "poliklinik", "dis-klinigi": "diş kliniği", "spor-fitness": "spor salonu", "insaat-yapi": "inşaat şantiyesi",
             "emlak-gayrimenkul": "emlakçı", "lojistik": "lojistik deposu", "mobilya-dekorasyon": "mobilya mağazası", "hukuk-profesyonel": "hukuk bürosu",
             "danismanlik": "danışmanlık ofisi", "guzellik-bakim": "güzellik salonu", "egitim-kurs": "kurs merkezi", "turizm-konaklama": "otel",
             "teknoloji-yazilim": "yazılım ofisi", "urun-katalogu": "showroom", "e-ticaret": "mağaza", "etkinlik-organizasyon": "düğün salonu",
             "kisisel-portfoy": "fotoğraf stüdyosu", "taksi": "taksi durağı", "isitme-merkezi": "işitme merkezi", "okul": "okul", "kres-anaokulu": "anaokulu",
             "tesisat": "tesisatçı", "veteriner": "veteriner kliniği", "temizlik": "temizlik firması", "nakliyat": "nakliyat kamyonu"}
OZ_CIP = {"galeri": "Fotoğraf galerisi", "urunler": "Ürün kataloğu", "sss": "Sık sorulan sorular", "iletisim": "Harita + iletişim", "surec": "Adım adım süreç",
          "hakkimizda": "Hakkımızda", "hizmetler": "Hizmetler"}


YAMA_DOSYA = pathlib.Path(__file__).resolve().parent.parent / "icerik" / "sektor-yamalari.json"


def yama_bul(firma: dict) -> tuple[str, dict] | None:
    """Site Mucidi'de kalıbı olmayan sektör (ör. matbaa) → icerik/sektor-yamalari.json; fotoğraf yolları mutlak yapılır."""
    metin = f"{firma.get('sektor', '')} {firma.get('firma', '')}".lower()
    for ad, y in json.loads(YAMA_DOSYA.read_text()).items():
        if ad.startswith("_") or not any(k in metin for k in y["anahtar"]):
            continue
        kok = YAMA_DOSYA.parent / "yama" / ad
        yol = lambda f: str(kok / f) if f else f  # noqa: E731
        y = json.loads(json.dumps(y))
        for b in ("hero", "hakkimizda"):
            for a in ("foto", "foto2"):
                if y.get(b, {}).get(a): y[b][a] = yol(y[b][a])
        for i in y.get("hizmetler", {}).get("items", []):
            if i.get("foto"): i["foto"] = yol(i["foto"])
        if y.get("galeri"): y["galeri"]["fotolar"] = [yol(f) for f in y["galeri"]["fotolar"]]
        return ad, y
    return None


def yama_kaynak(ad: str) -> str:
    k = json.loads((YAMA_DOSYA.parent / "yama" / ad / "kaynak.json").read_text())
    return "Örnek fotoğraflar: Wikimedia Commons — " + "; ".join(f"{v['yazar']} ({v['lisans']})" for v in k.values())


def site_uret(firma: dict, dizin: pathlib.Path, ek: dict | None = None) -> dict:
    dizin.mkdir(parents=True, exist_ok=True)
    g = {"firma": firma["firma"], "sektor_anahtar": firma["sektor_anahtar"], "sehir": firma.get("sehir", ""), "instagram": firma.get("kullanici", ""), **(ek or {})}
    ym = yama_bul(firma)
    if ym:  # kalıbın metni/görseli değil yamanınki; yalnız düzen tabandan
        g["sektor_anahtar"], g["yama"] = ym[1]["taban"], ym[1]
        gunluk(f"web: sektör yaması '{ym[0]}' uygulandı (taban {ym[1]['taban']})")
    elif g["sektor_anahtar"] not in SEKTOR_AD:   # kalıp yok ve yama yok: yanlış sektör görselleriyle site üretme
        raise RuntimeError(f"'{firma.get('sektor')}' için Site Mucidi kalıbı ve sektör yaması yok; icerik/sektor-yamalari.json'a ekle")
    (dizin / "girdi.json").write_text(json.dumps(g, ensure_ascii=False))
    r = subprocess.run(["npx", "tsx", "var/yorumdan/site-uret.ts", str(dizin / "girdi.json"), str(dizin)], cwd=SM, capture_output=True, text=True, timeout=300)
    if r.returncode:
        raise RuntimeError("site üretilemedi: " + r.stderr[-800:])
    b = json.loads((dizin / "bilgi.json").read_text())
    b["yama"] = ym[0] if ym else None
    return b


def katmanlar(dizin: pathlib.Path) -> dict:
    r = subprocess.run(["node", "var/yorumdan/katman.mjs", str(dizin)], cwd=SM, capture_output=True, text=True, timeout=300)
    if r.returncode:
        raise RuntimeError("katmanlar alınamadı: " + r.stderr[-800:])
    return json.loads((dizin / "kutular.json").read_text())


def yap(firma: dict, s: dict, gun: int, yildiz: dict, is_dir: pathlib.Path, cikti: pathlib.Path, bilgi: dict) -> dict:
    site = is_dir / "site"
    varyant = bilgi["tema"].rsplit("-", 1)[-1]
    bilgi = site_uret(firma, site, {"varyant": varyant, "site_baslik": s.get("site_baslik"), "site_alt": s.get("site_alt"), "yanlis_sektor": bilgi["yanlis_sektor"]})
    ku = katmanlar(site)
    ff("-i", bilgi["yanlis_foto"], "-q:v", "3", site / "yanlis.jpg")
    cum = anlatim("web", s)
    wav = is_dir / "ses.wav"
    seslendir(" ".join(c for _, c in cum), wav)
    bas, benz = hizala([c for _, c in cum], dok(wav))
    if benz < 0.62:
        raise RuntimeError(f"ses metinle uyuşmuyor (benzerlik {benz:.2f})")
    ses_sure = sure(wav)
    ilk = {}
    for (v, _), t in zip(cum, bas):
        ilk.setdefault(v, []).append(t)
    g = lambda v, i=0: ilk[v][min(i, len(ilk[v]) - 1)]  # noqa: E731
    Z = {"T": g("tanitim"), "K0": g("kapak", 0), "K1": g("kapak", 1), "K2": g("kapak", 2), "B0": g("baslik"), "I0": g("icerik", 0), "I1": g("icerik", 1),
         "O0": g("ozellik", 0), "O1": g("ozellik", 1), "CI": g("cihaz"), "H": g("hazir"), "C": g("kapanis")}
    Z["SON"] = round(max(ses_sure + 1.0, Z["C"] + 9.2), 2)
    C, SON = Z["C"], Z["SON"]
    LH = 900
    hiz = ku.get("hizmet") or {"y": 900, "h": 600}
    oz = ku["bolum"].get(yildiz["kod"]) or ku["bolum"].get("hizmetler") or hiz
    son_sy = max(0, ku["boy"] - LH)
    V_kutu = {"h1": ku["h1"], "p": ku["p"], "btn": ku["btn"], "img": ku["img"], "kart": ku["kart"], "hizmet": ku.get("hizmet")}
    kullanici = firma.get("kullanici") or ""
    L = []

    def kat(id_, s0, s1, ic, cls="", style="", iz=2):
        L.append(f'      <div id="{id_}" class="clip {cls}" data-start="{s0:.2f}" data-duration="{max(0.1, s1 - s0):.2f}" data-track-index="{iz}"{(" style=" + chr(34) + style + chr(34)) if style else ""}>{ic}</div>')
    if firma.get("kaynak") == "yorum":
        kimlik, yorum_m, et = f"@{e(kullanici)}", f"“{e(firma['yorum'])}”", f"Gün {gun} · Yorumlardan"
        kalp = f'<div class="kalp">♥<b>{firma["begeni"]}</b></div>' if firma.get("begeni") else '<div class="kalp">♥</div>'
    else:
        kimlik, yorum_m, et, kalp = "Bugünün firması", f"{e(firma['firma'])} · {e(firma['sektor'])}", f"Gün {gun} · Web sitesi", '<div class="kalp">♥</div>'
    kat("kanca", 0, Z["T"], f'<div class="etiket dolu" id="kanca-et"><i></i>{e(et)}</div><div class="balon" id="balon"><div class="avatar"><span>{e((kullanici or firma["firma"])[:1].upper())}</span></div><div><div class="balon-kim">{kimlik}</div><div class="balon-metin">{yorum_m}</div></div>{kalp}</div>', "ust")
    cip = f'<span class="cip" id="c1">{e(firma["sektor"])}</span>' + (f'<span class="cip" id="c2">{e(firma["sehir"])}</span>' if firma.get("sehir") else "")
    kat("firma", Z["T"], Z["K0"], f'<div class="etiket"><i></i>Gün {gun} · Web sitesi</div><div class="baslik" id="fb1">Bugünkü firma:</div><div class="baslik" id="fb2"><b>{e(firma["firma"])}</b></div><div class="cipler">{cip}</div>', "ust")
    kat("arac-kapak", Z["K0"], Z["I0"], '<small>Kapak fotoğrafı</small><span id="k-hazir">Hazır görsel ▾</span><span id="k-dogru" style="display:none;align-items:center;gap:12px">Uygun fotoğraf <span class="ok">✓</span></span>', "arac", iz=3)
    kat("damga1", Z["K1"] + 0.4, min(Z["K2"], Z["K1"] + 2.4), "YANLIŞ DOSYA!", "damga", "top:860px;font-size:80px", iz=4)
    kat("arac-icerik", Z["I0"], Z["O0"], f'<small>İçerik</small>{len(ku["kart"]) or ""} hizmet kartı <span class="ok">✓</span>', "arac", iz=3)
    kat("arac-oz", Z["O0"], Z["CI"], f'<small>Özellik</small>{e(yildiz.get("cip") or yildiz["ad"])} <span class="ok">✓</span>', "arac", iz=3)
    kat("arac-cihaz", Z["CI"], Z["H"], '<span id="cz1">Telefon <span class="ok">✓</span></span><span id="cz2">Bilgisayar <span class="ok">✓</span></span>', "arac", iz=3)
    kat("hazir", Z["H"], C, '<div class="etiket dolu"><i></i>Site Mucidi ile yapıldı</div><div class="baslik" id="hzb">Satışa <b>hazır</b> bekliyor.</div><div class="not">Vitrin tasarımı · içerik temsilidir</div>', "ust")
    ozl = ["Mobil uyumlu"] + [OZ_CIP[b] for b in bilgi["bolumler"] if b in OZ_CIP and b != "hizmetler"][:3]
    kat("ozellikler", Z["H"] + 0.25, C, "".join(f'<div class="oz" id="oz{i}"><i>✓</i>{e(o)}</div>' for i, o in enumerate(ozl)), iz=5)
    kat("hergun", C, C + 2.55, '<div class="etiket dolu"><i></i>Her gün · yeni firma · yeni tasarım</div><div class="baslik kucuk" id="hg1">Her gün yeni bir firma,</div><div class="baslik kucuk" id="hg2"><b>yeni bir site!</b></div>', "ust")
    kat("cta", C + 2.55, SON, '<div class="etiket"><i></i>Yarın: yeni bölüm</div><div class="baslik" id="cb1">Sıradaki web sitesi</div><div class="baslik" id="cb2"><b>senin olsun!</b></div>', "ust")
    kat("cta-panel", C, SON, "", iz=11)
    kat("yorum-kutu", C + 4.3, SON, '<div class="av"></div><div id="yorum-yazi"><span id="yorum-ic">Firma adı + sektör</span><span id="imlec"></span></div><div id="okb">↓</div>', iz=12)
    L.append(f'      <img id="cta-logo" class="clip" src="assets/logo-tam-beyaz.png" alt="Mchttasarım" data-start="{C + 1.0:.2f}" data-duration="{SON - C - 1.0:.2f}" data-track-index="14" />')
    kat("cta-not", C + 6.7, SON, "En çok beğeni alan <b>kazanır!</b>", iz=13)
    kalpler = []
    for i in range(6):
        t0 = C + 5.0 + 0.55 * i
        if t0 + 1.7 <= SON:
            kat(f"k{i + 1}", t0, t0 + 1.7, "♥", "kalp2", f"left:{[820, 760, 840, 780, 830, 770][i]}px;top:{[1020, 1030, 1010, 1025, 1015, 1030][i]}px", iz=15 + i % 2); kalpler.append([f"#k{i + 1}", "kalp", t0])
    alt = altyazilar(cum, bas, ses_sure, ("kanca", "kapanis", "hazir"))
    # web'de altyazı dizüstü ekranının üstünde (ekran ortada)
    for i, (t0, d, p) in enumerate(alt):
        kat(f"y{i:02d}", t0, t0 + d, kelime_html(t0, d, p), "yazi", "", iz=20 + i % 2)
    L = [x.replace('class="clip damga"', 'class="clip damga" data-layout-allow-occlusion') for x in L]
    giris = [["#balon", "salla", 0.45], ["#kanca-et", "zipla", 0.05], ["#fb1", "yukari", Z["T"] + 0.4], ["#fb2", "buyuk", Z["T"] + 1.2], ["#c1", "zipla", Z["T"] + 1.8], ["#c2", "zipla", Z["T"] + 2.1],
             ["#arac-kapak", "dus", Z["K0"] + 0.05], ["#damga1", "damga", Z["K1"] + 0.4], ["#k-hazir", "gizle", Z["K2"]], ["#k-dogru", "goster", Z["K2"]],
             ["#arac-icerik", "dus", Z["I0"] + 0.05], ["#arac-oz", "dus", Z["O0"] + 0.05], ["#arac-cihaz", "dus", Z["CI"] + 0.05], ["#hzb", "buyuk", Z["H"] + 0.1]] + \
            [[f"#oz{i}", "zipla", Z["H"] + 0.35 + 0.22 * i] for i in range(len(ozl))] + \
            [["#hg1", "yukari", C + 0.05], ["#hg2", "buyuk", C + 1.55], ["#cta-panel", "panel", C], ["#cta-logo", "solgun", C + 1.0], ["#cb1", "yukari", C + 2.6], ["#cb2", "buyuk", C + 3.66],
             ["#yorum-kutu", "dus", C + 4.3], ["#okb", "zipzip", C + 4.7], ["#cta-not", "solgun", C + 6.75]] + kalpler + [[f"#y{i:02d} span", "pop", t0] for i, (t0, _, _) in enumerate(alt)]
    flaslar = [[0.45, 0.45], [0.85, 0.35], [Z["T"], 0.3], [Z["K0"], 0.3], [Z["K2"], 0.3], [Z["I0"], 0.2], [Z["O0"], 0.25], [Z["CI"], 0.35], [Z["H"], 0.5], [C, 0.3]]
    V = {"Z": Z, "firma": firma["firma"], "kutu": V_kutu, "hizmet_sy": min(son_sy, max(0, hiz["y"] - 80)),
         "ozellik": {"sy": min(son_sy, max(0, oz["y"] - 60)), "rect": {"x": oz["x"], "y": oz["y"], "w": oz["w"], "h": oz["h"]}}, "flaslar": flaslar, "giris": giris}
    proje = hazirla("web", is_dir, {"SURE": f"{SON:.2f}", "KATMANLAR": "\n".join(L), "VERI": json.dumps(V, ensure_ascii=False)},
                    {"masa-tam.png": site / "masa-tam.png", "masa-taban.png": site / "masa-taban.png", "mobil.png": site / "mobil.png", "yanlis.jpg": site / "yanlis.jpg"})
    ham = is_dir / "ham.mp4"
    render(proje, ham)
    sfx = [("vurus", 0.45, .55), ("vurus", 0.85, .45), ("vuus", Z["T"] - 0.05, .5), ("vuus", Z["K0"] - 0.05, .5), ("vurus", Z["K1"] + 0.4, .55),
           ("vuus", Z["K2"] - 0.05, .5), ("vuus", Z["I0"], .45), ("vurus", Z["O0"] + 0.9, .5), ("vuus", Z["CI"], .55), ("vurus", Z["H"], .55), ("vuus", C - 0.05, .5)]
    miks(ham, wav, sfx, SON, cikti, proje / "assets")
    gunluk(f"web bölümü hazır: {cikti} ({SON:.1f} sn, benzerlik {benz:.2f})")
    return {"sure": SON, "benzerlik": benz, "Z": Z, "fotolar": bilgi.get("fotolar", []), "tema": bilgi["tema"], "varyant": varyant, "yama": bilgi.get("yama")}
