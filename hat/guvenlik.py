"""İçerik güvenliği (2026-11-26, Mücahit: "argo, bahis, kumar, +18 içerikleri kesinlikle yapma").
Yorumdan gelen her metin (yorum, kullanıcı adı, çıkarılan firma adı), panel fikri ve paylaşılacak son metin buradan geçer.
Kaçamak yazımlar da yakalanır: "B@h!s", "c a s i n o", "kumaaar", "18+", "+18", "x-bet".
Yapay zekâ denetimine ek, ondan BAĞIMSIZ kural katmanıdır: model "uygun" dese bile burada yakalanan metin kullanılmaz."""
from __future__ import annotations

import re

_TR = str.maketrans({"ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u", "â": "a", "î": "i", "û": "u"})
_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s", "!": "i", "|": "i", "€": "e"})

# Kaba ASCII biçimde, harf tekrarları sadeleştirilmiş kökler (kelimenin herhangi bir yerinde geçerse yakalanır).
KUMAR = ["bahis", "iddaa", "kumar", "casino", "kazino", "kumarhane", "rulet", "poker", "blackjack", "jackpot", "freespin",
         "denemebonus", "bonusveren", "canlibahis", "slotoyun", "sweetbonanza", "aviator", "tipobet", "betist", "bets10", "superbet",
         "lotobet", "piabet", "casibom", "betebet", "jojobet", "matbet", "grandpasha", "holiganbet", "kingroyal", "marsbahis", "betpark"]
KUMAR = [k for k in KUMAR if k != "aviator"]
YETISKIN = ["onlyfans", "escort", "eskort", "porno", "porn", "xxx", "nsfw", "erotik", "ciplak", "yetiskinicerik", "sexy", "hotchat",
            "camgirl", "fetis", "swinger"]
MADDE = ["uyusturucu", "kokain", "eroin", "bonzai", "metamfetamin", "ekstazi"]
_KELIME = re.compile(r"\b(seks|seksi|sex|esrar|extasy)\b")  # "seksen", "esrarengiz" masum
# Küfür/argo: Türkçe harflerle, kelime başında aranır (şikâyet/sıkıntı gibi masum kelimeler yakalanmasın).
ARGO = [r"amk", r"amq", r"aq", r"mk", r"amına", r"amina", r"amcık", r"amcik", r"orospu", r"oç", r"piç", r"yarra?k", r"dalyarak",
        r"si[kq](?:ti[rk]|erim|ik|im|iyim|ecem|mek|tim|ilmiş)?", r"göt(?:ü|veren|lek)?", r"kahpe", r"şerefsiz", r"gavat", r"pezevenk",
        r"ibne", r"puşt", r"yavşak", r"gerizekalı", r"salak", r"aptal", r"ananı", r"bacını", r"sürtük", r"kaltak"]
_ARGO = re.compile(r"(?<![a-zçğıöşü])(?:" + "|".join(ARGO) + r")(?![a-zçğıöşü])")
# "...bet" ile biten bahis markaları; Türkçe masum kelimeler hariç
_BET = re.compile(r"(?<![a-z])([a-z]{0,10})bet\d*(?![a-z])")
_BET_MASUM = {"soh", "muhab", "reka", "no", "aki", "gur", "el", "rag", "nis", "mahab", "hi", "kur", "ze", "a", "ta", "al", "se"}
_YAS = re.compile(r"(?<!\d)(\+\s*18|18\s*\+|18\s*yas\s*ustu)(?!\d)")


def _kaba(s: str) -> str:
    s = (s or "").replace("İ", "i").replace("I", "ı").lower().translate(_TR).translate(_LEET)
    s = re.sub(r"[^a-z0-9+ ]", " ", s)
    return re.sub(r"(.)\1{2,}", r"\1", s)  # "kumaaar" → "kumar"


def uygunsuz(*metinler: str) -> str | None:
    """Kategori adı (kumar/bahis, +18, uyuşturucu, argo) ya da None."""
    for m in metinler:
        if not m:
            continue
        kaba = _kaba(m)
        bitisik = kaba.replace(" ", "")
        tek_harf = re.sub(r"\b(\w) (?=\w\b)", r"\1", kaba)  # "c a s i n o" → "casino"
        for alan in (bitisik, tek_harf):
            if any(k in alan for k in KUMAR):
                return "kumar/bahis"
            if any(k in alan for k in YETISKIN):
                return "+18"
            if any(k in alan for k in MADDE):
                return "uyuşturucu"
        if _KELIME.search(kaba):
            return "+18" if not _KELIME.search(kaba).group(1).startswith(("esrar", "extasy")) else "uyuşturucu"
        if _YAS.search(re.sub(r"[^a-z0-9+ ]", " ", (m or "").lower().translate(_TR))):
            return "+18"
        if any(x.group(1) not in _BET_MASUM for x in _BET.finditer(kaba)):
            return "kumar/bahis"
        tr = re.sub(r"[^a-zçğıöşü0-9 ]", " ", (m or "").replace("İ", "i").replace("I", "ı").lower())
        if _ARGO.search(tr):
            return "argo/küfür"
    return None
