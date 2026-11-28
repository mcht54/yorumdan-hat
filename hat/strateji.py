"""İçerik stratejisti kuralları (kullanıcı kuralı 2026-11-28; tek kaynak ~/Documents/mcht-icerik-ortak/icerik-stratejisti.md).
Kural metni icerik/uzman-kurallari.md ve icerik/para-kurallari.md içinde; burada yalnız istem eki + açılış denetimi var."""
from __future__ import annotations

import json
import re

# Kural 2: şemaya İSTEĞE BAĞLI alan. Ayrıştırıcılar bu alanı okumaz; gelmezse hiçbir şey bozulmaz.
KANCA_ADAYLARI_SEMA = (' "kanca_adaylari": ["isteğe bağlı: yazmadan önce düşündüğün 5 FARKLI tipte kanca '
                       '(merak boşluğu, beklenmedik gerçek/karşıtlık, doğrudan soru, sonucu başta gösterme, hata/uyarı, somut sahne/an); '
                       'her biri 1 cümle. \\"kanca\\" alanına bunların içerikle karşılanabilen EN GÜÇLÜSÜNÜ yaz"],\n')


def sema_ekle(sema: str) -> str:
    """JSON şema metninin başına (ilk '{' sonrasına) kanca_adaylari satırını ekler."""
    i = sema.index("{") + 1
    return sema[:i] + "\n" + KANCA_ADAYLARI_SEMA.rstrip("\n") + sema[i:]


def istem_eki(son_kancalar: list) -> str:
    """Kural 1-2-7: açılış, 5 kanca ve son kancaları tekrar etmeme talimatı."""
    son = [str(x) for x in (son_kancalar or []) if str(x).strip()][-8:]
    return ("AÇILIŞ (içerik stratejisti kuralı): selam, 'merhaba', 'arkadaşlar', kendini tanıtma, 'bugün size … anlatacağım' YOK; "
            "ilk cümle doğrudan kanca. Önce en az 5 farklı tipte kanca düşün, 'kanca_adaylari' alanına yaz, en güçlüsünü 'kanca' yap.\n"
            + (f"Son paylaşımların açılışları (bunları, kanca tiplerini ve kalıplarını TEKRARLAMA): {json.dumps(son, ensure_ascii=False)}\n" if son else ""))


# Kural 1: açılışta selam/giriş kalıbı
_BAS = re.compile(r"^\W*(merhaba|selam(lar|lar?ı?n?)?|sevgili\s+(takipçiler|izleyiciler)|herkese\s+(merhaba|selam)|hoş\s*geldin\w*)\b", re.I)
_ICINDE = re.compile(r"\b(arkadaşlar|bugün\s+size|ben\s+\w+\s*,?\s*(bugün|şimdi)\s+size)\b", re.I)


def acilis_sorunu(*cumleler) -> list[str]:
    """İlk cümle(ler)de selam/giriş kalıbı varsa sorun listesi döner (boş liste = temiz)."""
    sorun = []
    for i, c in enumerate(x for x in cumleler if x):
        c = " ".join(map(str, c)) if isinstance(c, list) else str(c)
        if (i == 0 and _BAS.search(c)) or _ICINDE.search(c.lower()):
            sorun.append(f"açılışta selam/giriş kalıbı var ('{c[:40]}…'): selam, 'arkadaşlar', 'bugün size' yok; ilk cümle doğrudan kanca olsun")
            break
    return sorun
