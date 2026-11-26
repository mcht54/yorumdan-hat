"""Son bölümün yorumlarını toplar. Deneme modunda test/ornek/yorumlar.json kullanılır (ağa çıkmaz)."""
from __future__ import annotations

import json

from instagram import Instagram
from ortak import KOK, gunluk, oku


def topla(hesap: str, deneme: bool = False) -> tuple[str | None, list[dict]]:
    """(son bölüm medya id, yorumlar). Yorum: {id, text, username, like_count, timestamp}."""
    if deneme:
        v = json.loads((KOK / "test/ornek/yorumlar.json").read_text())
        return v["medya_id"], v["yorumlar"]
    ig = Instagram(hesap)
    if not ig.hazir:
        raise RuntimeError(f"{hesap}: Instagram bağlantısı yok (.env IG_{hesap.upper()}_ID / _TOKEN)")
    kayit = oku(f"{hesap}-bolumler.json", [])
    medya = kayit[-1]["medya_id"] if kayit and kayit[-1].get("medya_id") else None
    if not medya:  # ilk gün ya da kayıt yoksa: hesaptaki son Reels
        son = [m for m in ig.son_medyalar(5) if m.get("media_type") in ("VIDEO", "REELS")]
        medya = son[0]["id"] if son else None
    if not medya:
        return None, []
    y = ig.yorumlar(medya)
    gunluk(f"{hesap}: {len(y)} yorum toplandı ({medya})")
    return medya, y
