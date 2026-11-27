"""Ortak yardımcılar: yollar, ayarlar, günlük, Gemini (yalnız ücretsiz katman), ffmpeg."""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import re
import subprocess
import time
import urllib.error
import urllib.request

try:
    from gemini_havuz import GeminiHatasi, GunlukKota, Havuz, google_gunu, parmak  # noqa: F401
    from gemini_havuz import anahtarlar as _havuz_anahtarlar
except ImportError:  # paket olarak içe aktarılırsa (hat.ortak)
    from .gemini_havuz import GeminiHatasi, GunlukKota, Havuz, google_gunu, parmak  # noqa: F401
    from .gemini_havuz import anahtarlar as _havuz_anahtarlar

KOK = pathlib.Path(__file__).resolve().parent.parent
DURUM = KOK / "durum"
CIKTI = KOK / "cikti"
ICERIK = KOK / "icerik"
SABLON = KOK / "sablon"
IS = KOK / "is"
for d in (DURUM, CIKTI, IS):
    d.mkdir(exist_ok=True)


def ayarlar() -> dict:
    return json.loads((KOK / "ayarlar.json").read_text())


def env(ad: str, varsayilan: str = "") -> str:
    if os.environ.get(ad):
        return os.environ[ad]
    f = KOK / ".env"
    if f.exists():
        for s in f.read_text().splitlines():
            if s.startswith(ad + "="):
                return s.split("=", 1)[1].strip()
    return varsayilan


def gunluk(m: str) -> None:
    satir = f"{dt.datetime.now():%Y-%m-%d %H:%M:%S} {m}"
    if not os.environ.get("YORUMDAN_SESSIZ"):   # GitHub Actions açık depoda: günlük yalnız özel durum deposuna yazılır
        print(satir, flush=True)
    with open(DURUM / "gunluk.log", "a") as f:
        f.write(satir + "\n")


def oku(ad: str, varsayilan=None):
    f = DURUM / ad
    return json.loads(f.read_text()) if f.exists() else varsayilan


def yaz(ad: str, veri) -> None:
    (DURUM / ad).write_text(json.dumps(veri, ensure_ascii=False, indent=1))


def ff(*arg, sessiz=True):
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", *map(str, arg)], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError("ffmpeg: " + r.stderr[-600:])


def sure(f) -> float:
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(f)],
                                capture_output=True, text=True).stdout.strip() or 0)


class Kota(RuntimeError):
    """Günlük ücretsiz kota doldu: ücretliye GEÇİLMEZ (projede ödeme hesabı yok), bu tur atlanır."""


# Günlük istek bütçesi (kullanıcı kararı: ücretsiz katman ASLA aşılmaz). Ücretsiz katman model başına günde yüzlerce
# istek veriyor; hat günde 2 bölüm için ~10 istek harcar. Bu tavan, hata/döngüde bile katmanın çok altında kalmayı garanti eder.
# 2026-11-28 anahtar havuzu: tavan ANAHTAR BAŞINADIR (toplam = anahtar sayısı × tavan; her anahtar ayrı Gmail'in ayrı
# ücretsiz projesi). Canlı rezerv sabit kalır: denemeler toplam tavanın CANLI_REZERV kadar altında durur.
GUNLUK_TAVAN = {"tts": 12, "metin": 60}
CANLI_REZERV = {"tts": 10, "metin": 45}   # denemeler bunun altına inemez (5 canlı bölüm × ~2 ses denemesi)  # 2026-11-26: günde 4 video (Cüzdan Hocası 2 slot); ücretsiz katmanın altında, ödeme hesabı YOK


def anahtarlar() -> list[str]:
    """Gemini anahtar havuzu: GEMINI_API_KEY, GEMINI_API_KEY_2 … _9, virgüllü GEMINI_API_KEYS (ortam, sonra .env)."""
    return _havuz_anahtarlar(os.environ, KOK / ".env")


_HAVUZ = None


def havuz() -> Havuz:
    """Dolu işaretleri durum/gemini-havuz.json'da (yalnız anahtar parmak izi; durum deposuyla Mac ↔ Actions paylaşılır)."""
    global _HAVUZ
    if _HAVUZ is None:
        _HAVUZ = Havuz(DURUM / "gemini-havuz.json", anahtarlar, gunluk=lambda m: gunluk(m))
    return _HAVUZ


def _butce(model: str, anahtar_sayisi: int = 1) -> None:
    tur = "tts" if "tts" in model else "metin"
    yol = DURUM / "gemini-sayac.json"
    # 2026-11-28: Google'ın ücretsiz günlük kotası Pasifik gece yarısı (TR 11:00) sıfırlanır → sayaç da o günü sayar
    bugun = google_gunu()
    try:
        v = json.loads(yol.read_text())
    except Exception:  # noqa: BLE001
        v = {}
    if v.get("gun") != bugun:
        v = {"gun": bugun, "tts": 0, "metin": 0}
    tavan = GUNLUK_TAVAN[tur] * max(1, anahtar_sayisi)
    if v[tur] >= tavan:
        raise Kota(f"{model}: hattın günlük {tur} bütçesi ({tavan} = {max(1, anahtar_sayisi)} anahtar × {GUNLUK_TAVAN[tur]}) doldu, "
                   "yarına kadar Gemini çağrılmaz")
    # deneme/kuru bölümler canlı paylaşımların payını yemesin (2026-11-28: 7 deneme bölümü günün sesini bitirdi, 2 video kaçtı)
    if os.environ.get("YORUMDAN_DENEME") == "1" and v[tur] >= tavan - CANLI_REZERV[tur]:
        raise Kota(f"{model}: deneme bölümü için {tur} payı bitti (canlı paylaşımlara {CANLI_REZERV[tur]} ayrıldı)")
    v[tur] += 1
    v["anahtar"] = max(1, anahtar_sayisi)
    yol.write_text(json.dumps(v))


def gemini(model: str, govde: dict, zaman: int = 180) -> dict:
    """Anahtar havuzuyla çağırır: günlük kotası dolan anahtar (model × anahtar) bugün atlanır, sıradakine geçilir.
    Hepsi doluysa Kota (çağıran Groq yedeğine düşer). Bütçe sayacı yalnız gerçekten istek atılacaksa artar."""
    h = havuz()
    n = h.sayi()
    if not n:
        raise RuntimeError("GEMINI_API_KEY yok (.env)")
    if h.hepsi_dolu(model):
        raise Kota(f"{model}: {n} anahtarın hepsinin bugünkü ücretsiz kotası dolu (TR 11:00'de yenilenir)")
    _butce(model, n)
    try:
        return h.cagir(model, govde, zaman=zaman, deneme=3)
    except GunlukKota as e:
        raise Kota(str(e)) from e
    except GeminiHatasi as e:
        raise RuntimeError(f"gemini {e}") from e


_modeller: list[str] | None = None


def metin_modelleri() -> list[str]:
    """Hesabın erişebildiği flash modelleri (kararlı > önizleme, yeni > eski, tam > lite). Ücretsiz katman."""
    global _modeller
    if _modeller is None:
        adlar = []
        for k in anahtarlar()[:3]:   # ilk anahtar geçersizse sıradakiyle listele
            try:
                req = urllib.request.Request("https://generativelanguage.googleapis.com/v1beta/models?pageSize=200", headers={"x-goog-api-key": k})
                adlar = [m["name"].removeprefix("models/") for m in json.load(urllib.request.urlopen(req, timeout=30)).get("models", [])
                         if "generateContent" in m.get("supportedGenerationMethods", [])]
                break
            except Exception as e:  # noqa: BLE001
                gunluk(f"model listesi alınamadı [{parmak(k)}]: {type(e).__name__}")
        atla = ("image", "tts", "audio", "live", "embed", "vision", "thinking", "learnlm", "robotics", "computer")
        def puan(ad):
            m = re.search(r"gemini-(\d+(?:\.\d+)?)", ad)
            return (not re.search(r"preview|exp", ad), float(m.group(1)) if m else 0, "lite" not in ad, -len(ad))
        _modeller = sorted({a for a in adlar if "flash" in a and not any(x in a for x in atla)}, key=puan, reverse=True)[:5]
        gunluk("metin modelleri: " + ", ".join(_modeller))
    return _modeller


def json_sor(sistem: str, istem: str, sicaklik: float = 0.9) -> dict:
    son = None
    for model in metin_modelleri():
        try:
            g = gemini(model, {"systemInstruction": {"parts": [{"text": sistem}]},
                               "contents": [{"role": "user", "parts": [{"text": istem}]}],
                               "generationConfig": {"temperature": sicaklik, "responseMimeType": "application/json"}})
            t = g["candidates"][0]["content"]["parts"][0]["text"]
            t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t.strip())
            return json.loads(t)
        except Kota as e:
            son = e; gunluk(str(e))
        except Exception as e:  # noqa: BLE001
            son = e; gunluk(f"gemini {model} olmadı: {str(e)[:200]}")
    g = groq_json(sistem, istem, sicaklik)  # Gemini düşünce ücretsiz Groq yedeği
    if g is not None:
        return g
    raise RuntimeError(f"metin üretilemedi: {son}")


GROQ_MODELLER = ("qwen/qwen3.8-27b", "openai/gpt-oss-120b")  # 2026-11-26 Groq'ta sunulan, Türkçesi iyi olanlar


def groq_json(sistem: str, istem: str, sicaklik: float = 0.9) -> dict | None:
    """Ücretsiz Groq yedeği. YALNIZ ücretsiz katman: anahtar kartsız ücretsiz hesaptan; 429 (kota) gelince hemen durur,
    yeniden denemez, başka/ücretli sağlayıcıya geçmez. Anahtar yoksa None."""
    anahtar = env("GROQ_API_KEY")
    if not anahtar:
        return None
    for model in GROQ_MODELLER:
        govde = json.dumps({"model": model, "temperature": sicaklik, "response_format": {"type": "json_object"},
                            "messages": [{"role": "system", "content": sistem}, {"role": "user", "content": istem}]}).encode()
        req = urllib.request.Request("https://api.groq.com/openai/v1/chat/completions", data=govde,
                                     headers={"Authorization": f"Bearer {anahtar}", "Content-Type": "application/json", "User-Agent": "yorumdan-hat/1"})
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                v = json.loads(json.load(r)["choices"][0]["message"]["content"])
            gunluk(f"metin Groq ({model}) ile yazıldı (Gemini yoktu)")
            return v
        except urllib.error.HTTPError as e:
            if e.code == 429:  # dakikalık sınırsa kısa bekleyip aynı ücretsiz anahtarla bir kez daha; günlükse dur. Ücretliye geçilmez.
                try:
                    bekle = float(e.headers.get("retry-after") or 0)
                except ValueError:
                    bekle = 0
                if 0 < bekle <= 65 and not globals().get("_groq_bekledi"):
                    globals()["_groq_bekledi"] = True
                    time.sleep(bekle)
                    try:
                        with urllib.request.urlopen(req, timeout=90) as r:
                            return json.loads(json.load(r)["choices"][0]["message"]["content"])
                    except Exception:  # noqa: BLE001
                        pass
                gunluk("Groq ücretsiz kotası doldu; yedek yok")
                return None
            gunluk(f"groq {model} {e.code}; sıradaki model")
        except Exception as e:  # noqa: BLE001
            gunluk(f"groq {model} olmadı: {str(e)[:120]}")
    return None


def normal(s: str) -> str:
    s = s.replace("İ", "i").replace("I", "ı").lower()
    return re.sub(r"[^a-zçğıöşü0-9 ]", " ", s)


OKUNUS = [("Mchttasarım Reklam Ajansı", "Me-Ce-He-Te Tasarım Reklam Ajansı"), ("Mchttasarım", "Me-Ce-He-Te Tasarım"), ("MCHT", "Me-Ce-He-Te")]


def okunus(s: str) -> str:
    for a, b in OKUNUS:
        s = s.replace(a, b)
    return s


def durum_esitle(yon: str) -> None:
    """durum/ özel git deposu (mcht54/yorumdan-durum) ise: 'al' = pull, 'ver' = commit + push (çakışmada rebase ile 3 deneme).
    Mac ve GitHub Actions aynı kayıtları kullanır; böylece çift paylaşım kapısı ("bugün zaten paylaşıldı") iki yerde de geçerli."""
    import subprocess
    if not (DURUM / ".git").exists():
        return
    g = lambda *a: subprocess.run(["git", "-C", str(DURUM), *a], capture_output=True, text=True, timeout=120)  # noqa: E731
    if yon == "al":
        r = g("pull", "--rebase", "-q")
        if r.returncode:
            g("rebase", "--abort")
            g("-c", "user.name=yorumdan-hat", "-c", "user.email=yorumdan-hat@users.noreply.github.com", "pull", "--no-rebase", "-X", "theirs", "--no-edit", "-q")
        return
    g("add", "-A")
    if g("diff", "--cached", "--quiet").returncode == 0:
        return
    g("-c", "commit.gpgsign=false", "-c", "user.name=yorumdan-hat", "-c", "user.email=yorumdan-hat@users.noreply.github.com",
      "commit", "-qm", f"durum {dt.datetime.now():%Y-%m-%d %H:%M} ({os.environ.get('YORUMDAN_KAYNAK', 'mac')})")
    for _ in range(3):
        if g("push", "-q").returncode == 0:
            return
        if g("pull", "--rebase", "-q").returncode:   # çakışma: rebase'i bırak, birleştir (çakışan JSON'da bizim sürüm kalır)
            g("rebase", "--abort")
            g("-c", "user.name=yorumdan-hat", "-c", "user.email=yorumdan-hat@users.noreply.github.com",
              "pull", "--no-rebase", "-X", "ours", "--no-edit", "-q")
    print("durum push olmadı (3 deneme)", flush=True)
