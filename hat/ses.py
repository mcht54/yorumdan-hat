"""Anlatım sesi: Gemini TTS (ücretsiz) → kuyruk paraziti kesimi → Whisper ile doğrulama ve cümle hizalama.
Kurallar: TTS'e yalnız okunacak metin gider (yönerge sesli okunur); Gemini dosya sonundaki ~0,16 sn çöp MUTLAKA kesilir."""
from __future__ import annotations

import base64
import difflib
import pathlib
import subprocess

import numpy as np

from ortak import env, ff, gemini, gunluk, normal, okunus

TTS_MODELLER = ["gemini-3.8-flash-tts", "gemini-2.5-flash-preview-tts"]
_whisper = None


def _pcm(f, sr=48000) -> np.ndarray:
    ham = subprocess.run(["ffmpeg", "-v", "error", "-i", str(f), "-f", "s16le", "-ac", "1", "-ar", str(sr), "-"], capture_output=True).stdout
    return np.frombuffer(ham, np.int16).astype(np.float32) / 32768


def kuyruk_kes(giris: pathlib.Path, cikti: pathlib.Path) -> float:
    """Sondaki çöp bloğu: ≥100 ms sessizlik (< -60 dB) + ardından yüksek blok (> -40 dB) son 0,6 sn içinde aranır."""
    a = _pcm(giris); P = 960
    db = [20 * np.log10(np.sqrt(np.mean(a[i:i + P] ** 2)) + 1e-9) for i in range(0, len(a) - P, P)]
    n = len(db); i = n - 1
    while i > n - 30 and not all(d <= -60 for d in db[max(0, i - 4):i + 1]):
        i -= 1
    if i <= n - 30 or max(db[i + 1:] or [-99]) < -40:
        ff("-i", giris, "-ar", "48000", "-ac", "1", cikti)
    else:
        j = i
        while j > 0 and db[j] <= -60:
            j -= 1
        kes = min(((i + j) / 2) * P / 48000, (j + 1) * P / 48000 + 0.25)
        ff("-i", giris, "-af", f"atrim=0:{kes:.3f},afade=t=out:st={kes - 0.03:.3f}:d=0.03", "-ar", "48000", "-ac", "1", cikti)
    b = _pcm(cikti)
    son = 20 * np.log10(np.sqrt(np.mean(b[-2400:] ** 2)) + 1e-9)
    if son > -50:
        raise RuntimeError(f"ses kuyruğunda parazit kaldı ({son:.0f} dB)")
    return len(b) / 48000


def seslendir(metin: str, cikti: pathlib.Path, ses: str = "Fenrir") -> str:
    metin = okunus(metin)
    son = None
    for model in TTS_MODELLER:
        try:
            g = gemini(model, {"contents": [{"parts": [{"text": metin}]}], "generationConfig": {"responseModalities": ["AUDIO"],
                       "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": ses}}}}})
            ham = base64.b64decode(g["candidates"][0]["content"]["parts"][0]["inlineData"]["data"])
            h = cikti.with_suffix(".ham.pcm"); h.write_bytes(ham)
            giris = ["-i", h] if ham[:4] == b"RIFF" else ["-f", "s16le", "-ar", "24000", "-ac", "1", "-i", h]
            ham_wav = cikti.with_suffix(".ham.wav"); ff(*giris, "-ar", "48000", ham_wav); h.unlink()
            kuyruk_kes(ham_wav, cikti)
            return model
        except Exception as e:  # noqa: BLE001
            son = e; gunluk(f"tts {model} olmadı: {str(e)[:200]}")
    raise RuntimeError(f"anlatım sesi üretilemedi: {son}")


def dok(wav: pathlib.Path) -> list[dict]:
    global _whisper
    from faster_whisper import WhisperModel
    if _whisper is None:
        _whisper = WhisperModel("small", compute_type="int8")
    seg, _ = _whisper.transcribe(_pcm(wav, 16000), language="tr", word_timestamps=True)
    return [{"w": w.word.strip(), "s": float(w.start), "e": float(w.end)} for s in seg for w in s.words]


def hizala(cumleler: list[str], kelimeler: list[dict]) -> tuple[list[float], float]:
    """Her cümlenin başlangıç saniyesi + metin benzerliği. Senaryo kelimeleri ile Whisper kelimeleri sıralı eşlenir."""
    sk, sahip = [], []
    for ci, c in enumerate(cumleler):
        for w in normal(okunus(c)).split():
            sk.append(w); sahip.append(ci)
    wk = [normal(k["w"]).strip() for k in kelimeler]
    sm = difflib.SequenceMatcher(None, sk, wk, autojunk=False)
    es = {}
    for blk in sm.get_matching_blocks():
        for d in range(blk.size):
            es[blk.a + d] = blk.b + d
    # yaklaşık eşleme (Whisper'ın böldüğü/yanlış yazdığı kelimeler): kalanları komşulardan doğrusal ara değerle
    bas = []
    for ci in range(len(cumleler)):
        idx = [i for i, s in enumerate(sahip) if s == ci]
        t = None
        for i in idx:
            if i in es:
                t = kelimeler[es[i]]["s"] - (0 if i == idx[0] else 0.25 * (i - idx[0])); break
        bas.append(t)
    son = kelimeler[-1]["e"] if kelimeler else 0
    for ci in range(len(bas)):
        if bas[ci] is None:
            onceki = next((bas[j] for j in range(ci - 1, -1, -1) if bas[j] is not None), 0.0)
            sonraki = next((bas[j] for j in range(ci + 1, len(bas)) if bas[j] is not None), son)
            bas[ci] = (onceki + sonraki) / 2
    for ci in range(1, len(bas)):  # tekdüze artan
        bas[ci] = max(bas[ci], bas[ci - 1] + 0.3)
    bas[0] = 0.0
    benz = difflib.SequenceMatcher(None, " ".join(sk), " ".join(wk), autojunk=False).ratio()
    return bas, benz
