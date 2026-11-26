"""Cüzdan Hocası maskotu: kep takmış, konuşan yeşil cüzdan. Kodla çizilir (yapay zekâ görseli değil, etiket gerektirmez).
svg(ifade, para) → tek parça SVG. sablon_svg() → şablona gömülecek, tüm ifadeleri id'li gruplarda taşıyan sürüm.
İfadeler: mutlu, sok, uzgun, kirp (göz kırpma), hesap (gözlük + düşünme)."""
from __future__ import annotations

YESIL1, YESIL2, KOYU = "#25a06c", "#127049", "#0b3f2a"
KREM, ALTIN, ALTIN2 = "#fbefc9", "#ffc928", "#e09a00"
PARA1, PARA2 = "#c9f0b3", "#7fc28a"


def _para(n: int) -> str:
    """Cüzdanın üstünden taşan banknotlar (n = 0..4); bütçe durumu = cüzdanın doluluğu."""
    dz = [(-14, 168, 128), (8, 300, 112), (-5, 236, 98), (12, 360, 136)]
    out = []
    for a, x, y in dz[:n]:
        out.append(f'<g transform="rotate({a} {x + 70} {y + 60})"><rect x="{x}" y="{y}" width="150" height="120" rx="10" fill="{PARA1}" stroke="{PARA2}" stroke-width="6"/>'
                   f'<circle cx="{x + 75}" cy="{y + 52}" r="22" fill="none" stroke="{PARA2}" stroke-width="6"/></g>')
    return "".join(out)


GOZ = {
    "acik": lambda cx: f'<ellipse cx="{cx}" cy="330" rx="46" ry="54" fill="#fff" stroke="{KOYU}" stroke-width="6"/><circle cx="{cx + 6}" cy="338" r="22" fill="#14110f"/><circle cx="{cx + 14}" cy="328" r="7" fill="#fff"/>',
    "kucuk": lambda cx: f'<ellipse cx="{cx}" cy="326" rx="50" ry="60" fill="#fff" stroke="{KOYU}" stroke-width="6"/><circle cx="{cx}" cy="330" r="12" fill="#14110f"/>',
    "kapali": lambda cx: f'<path d="M{cx - 40} 336 Q{cx} 358 {cx + 40} 336" fill="none" stroke="{KOYU}" stroke-width="10" stroke-linecap="round"/>',
}
KAS = {
    "normal": f'<path d="M190 262 Q228 246 262 258" fill="none" stroke="{KOYU}" stroke-width="12" stroke-linecap="round"/><path d="M338 258 Q372 246 410 262" fill="none" stroke="{KOYU}" stroke-width="12" stroke-linecap="round"/>',
    "yuksek": f'<path d="M188 244 Q226 222 262 236" fill="none" stroke="{KOYU}" stroke-width="12" stroke-linecap="round"/><path d="M338 236 Q374 222 412 244" fill="none" stroke="{KOYU}" stroke-width="12" stroke-linecap="round"/>',
    "uzgun": f'<path d="M192 270 Q230 250 262 246" fill="none" stroke="{KOYU}" stroke-width="12" stroke-linecap="round"/><path d="M338 246 Q370 250 408 270" fill="none" stroke="{KOYU}" stroke-width="12" stroke-linecap="round"/>',
    "dusunce": f'<path d="M190 256 Q228 246 262 256" fill="none" stroke="{KOYU}" stroke-width="12" stroke-linecap="round"/><path d="M338 246 Q374 228 410 240" fill="none" stroke="{KOYU}" stroke-width="12" stroke-linecap="round"/>',
}
AGIZ = {
    "gulus": f'<path d="M248 410 Q300 468 352 410 Z" fill="#7a1e2c" stroke="{KOYU}" stroke-width="7" stroke-linejoin="round"/><path d="M270 438 Q300 456 330 438 Q300 448 270 438Z" fill="#ff7f8f"/>',
    "o": f'<ellipse cx="300" cy="430" rx="26" ry="32" fill="#7a1e2c" stroke="{KOYU}" stroke-width="7"/>',
    "uzgun": f'<path d="M256 444 Q300 404 344 444" fill="none" stroke="{KOYU}" stroke-width="10" stroke-linecap="round"/>',
    "sirit": f'<path d="M250 418 Q310 452 356 404" fill="none" stroke="{KOYU}" stroke-width="10" stroke-linecap="round"/>',
    "duz": f'<path d="M266 428 L334 424" fill="none" stroke="{KOYU}" stroke-width="10" stroke-linecap="round"/>',
}
GOZLUK = (f'<g fill="none" stroke="{KOYU}" stroke-width="8"><rect x="168" y="282" width="120" height="100" rx="30"/><rect x="312" y="282" width="120" height="100" rx="30"/>'
          f'<path d="M288 326 Q300 314 312 326"/></g>')
IFADE = {  # göz sol, göz sağ, kaş, ağız, gözlük
    "mutlu": ("acik", "acik", "normal", "gulus", False),
    "sok": ("kucuk", "kucuk", "yuksek", "o", False),
    "uzgun": ("acik", "acik", "uzgun", "uzgun", False),
    "kirp": ("acik", "kapali", "normal", "sirit", False),
    "hesap": ("acik", "acik", "dusunce", "duz", True),
}


def _yuz(ifade: str) -> str:
    gs, gg, k, a, gl = IFADE[ifade]
    return GOZ[gs](228) + GOZ[gg](372) + KAS[k] + AGIZ[a] + (GOZLUK if gl else "") + \
        '<ellipse cx="176" cy="404" rx="24" ry="14" fill="#ff6f8e" opacity=".75"/><ellipse cx="424" cy="404" rx="24" ry="14" fill="#ff6f8e" opacity=".75"/>'


def _govde(para: str, yuz: str, kollar: str = "") -> str:
    return f"""<defs><linearGradient id="cg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{YESIL1}"/><stop offset="1" stop-color="{YESIL2}"/></linearGradient>
<linearGradient id="kg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#2b2b33"/><stop offset="1" stop-color="#111116"/></linearGradient></defs>
<g id="bacak"><path d="M230 560 L224 640" stroke="{KOYU}" stroke-width="20" stroke-linecap="round"/><path d="M370 560 L376 640" stroke="{KOYU}" stroke-width="20" stroke-linecap="round"/>
<ellipse cx="210" cy="650" rx="44" ry="20" fill="#1c1c22"/><ellipse cx="390" cy="650" rx="44" ry="20" fill="#1c1c22"/></g>
<g id="para">{para}</g>
<g id="govde"><rect x="90" y="196" width="420" height="380" rx="58" fill="url(#cg)" stroke="{KOYU}" stroke-width="8"/>
<rect x="114" y="220" width="372" height="332" rx="40" fill="none" stroke="{KREM}" stroke-width="5" stroke-dasharray="16 12" opacity=".85"/>
<path d="M90 236 Q90 196 140 196 L460 196 Q510 196 510 236 L510 262 L90 262 Z" fill="#1b8a5a" opacity=".55"/>
<rect x="470" y="330" width="88" height="104" rx="26" fill="{YESIL2}" stroke="{KOYU}" stroke-width="8"/><circle cx="526" cy="382" r="20" fill="{ALTIN}" stroke="{ALTIN2}" stroke-width="6"/></g>
{kollar}
<g id="yuz">{yuz}</g>
<g id="kep" transform="rotate(-10 300 150)"><path d="M300 92 L450 148 L300 204 L150 148 Z" fill="url(#kg)" stroke="#000" stroke-width="5" stroke-linejoin="round"/>
<path d="M214 172 L214 214 Q300 248 386 214 L386 172 L300 204 Z" fill="#1d1d24" stroke="#000" stroke-width="5" stroke-linejoin="round"/>
<circle cx="300" cy="148" r="10" fill="{ALTIN}"/><path d="M300 148 Q380 160 430 196 L432 254" fill="none" stroke="{ALTIN}" stroke-width="7" stroke-linecap="round"/>
<path d="M420 250 L444 250 L440 290 L424 290 Z" fill="{ALTIN}" stroke="{ALTIN2}" stroke-width="3"/></g>"""


KOL_NORMAL = (f'<g id="kollar"><path d="M96 400 Q40 430 52 492" fill="none" stroke="{KOYU}" stroke-width="18" stroke-linecap="round"/><circle cx="54" cy="500" r="24" fill="{KREM}" stroke="{KOYU}" stroke-width="6"/>'
              f'<path d="M504 470 Q560 500 556 552" fill="none" stroke="{KOYU}" stroke-width="18" stroke-linecap="round"/><circle cx="556" cy="560" r="24" fill="{KREM}" stroke="{KOYU}" stroke-width="6"/></g>')


def svg(ifade: str = "mutlu", para: int = 3, w: int = 600) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 40 620 650" width="{w}">'
            + _govde(_para(para), _yuz(ifade), KOL_NORMAL) + "</svg>")


def sablon_svg() -> str:
    """Şablon için: tüm ifadeler ve para seviyeleri id'li gruplarda (GSAP opaklıkla seçer)."""
    yuzler = "".join(f'<g id="ifade-{k}" class="ifade" opacity="{1 if k == "mutlu" else 0}">{_yuz(k)}</g>' for k in IFADE)
    paralar = "".join(f'<g id="para-{n}" class="paraseviye" opacity="{1 if n == 3 else 0}">{_para(n)}</g>' for n in range(5))
    g = _govde(paralar, yuzler, KOL_NORMAL)
    return f'<svg id="maskot-svg" xmlns="http://www.w3.org/2000/svg" viewBox="0 40 620 650" width="100%" height="100%">{g}</svg>'


if __name__ == "__main__":
    import pathlib
    d = pathlib.Path(__file__).parent
    for k in IFADE:
        (d / f"maskot-{k}.svg").write_text(svg(k, {"uzgun": 0, "sok": 1}.get(k, 3)))
    (d / "maskot-sablon.svg").write_text(sablon_svg())
    print("yazıldı", list(IFADE))
