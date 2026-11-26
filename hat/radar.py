"""Trend ve rakip radarı (2026-11-26, Mücahit: "Instagram/TikTok trendini takip et, tutmuş içeriklerden fikir al, rakipleri izle").

Instagram: Graph API business_discovery ile rakiplerin ve sektörde viral olan hesapların HERKESE AÇIK son paylaşımları okunur
(beğeni, yorum, tür, açıklama). Etkileşim takipçiye bölünür; hesabın kendi ortalamasının çok üstündeki paylaşım "tutmuş" sayılır.
Hashtag araması Meta'nın ayrı onayını (Public Content Access) istediği için KULLANILMAZ.
TikTok: resmî trend API'si yok; istenirse Google arama destekli Gemini ile bu haftanın Türkiye trend formatları/sesleri toplanır
(kaynak bağlantısıyla). Uydurma trend yazılmaz.
Çıktı yazara gider: tutmuş konular, kancalar, formatlar, rakibin yapmadığı farklılaşma fırsatı + kanıt bağlantıları.
Kopya YOK: fikir/format alınır, metin/görsel/marka kopyalanmaz. Güvenlik: guvenlik.uygunsuz'dan geçmeyen paylaşım hiç kullanılmaz.
Bağımlılık yok (urllib); aynı dosya diğer hatlara kopyalanır."""
from __future__ import annotations

import datetime as dt
import json
import statistics
import urllib.error
import urllib.parse
import urllib.request

try:
    from guvenlik import uygunsuz
except ImportError:  # paket içinde
    from .guvenlik import uygunsuz  # type: ignore

GRAPH = "https://graph.facebook.com/v21.0"
# Çekiliş/etiketle paylaşımları yapay etkileşimdir; "tutan" sayılmaz (2026-11-27).
import re as _re
CEKILIS = _re.compile(r"çekiliş|cekilis|kazanan|arkadaşını etiketle|etiketle|giveaway|hediye ediyoruz", _re.I)
ALAN = "business_discovery.username({u}){{username,followers_count,media.limit({n}){{caption,like_count,comments_count,media_type,media_product_type,permalink,timestamp}}}}"


def hesap_oku(ig_id: str, anahtar: str, kullanici: str, adet: int = 25) -> dict | None:
    q = {"fields": ALAN.format(u=kullanici, n=adet), "access_token": anahtar}
    try:
        with urllib.request.urlopen(f"{GRAPH}/{ig_id}?" + urllib.parse.urlencode(q), timeout=30) as r:
            b = json.loads(r.read()).get("business_discovery") or {}
    except (urllib.error.URLError, TimeoutError, ValueError):
        return None
    return {"kullanici": b.get("username", kullanici), "takipci": int(b.get("followers_count") or 0), "paylasimlar": (b.get("media") or {}).get("data", [])}


def tutanlar(hesaplar: list[dict], gun: int = 60, en_cok: int = 10) -> list[dict]:
    """Son `gun` günün paylaşımları: etkileşim/takipçi oranı ve hesabın kendi medyanına göre kat. Uygunsuz olan atılır."""
    sinir = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=gun)).isoformat()
    out = []
    for h in hesaplar:
        p = [x for x in h["paylasimlar"] if (x.get("timestamp") or "") >= sinir[:19] and not uygunsuz(x.get("caption") or "")
             and not CEKILIS.search(x.get("caption") or "")]
        if not p:
            continue
        etk = [int(x.get("like_count") or 0) + 3 * int(x.get("comments_count") or 0) for x in p]
        med = max(statistics.median(etk), 1)
        for x, e in zip(p, etk):
            out.append({"hesap": h["kullanici"], "takipci": h["takipci"], "tur": x.get("media_product_type") or x.get("media_type"),
                        "begeni": int(x.get("like_count") or 0), "yorum": int(x.get("comments_count") or 0), "kat": round(e / med, 1),
                        "oran": round(e / max(h["takipci"], 100), 4), "aciklama": (x.get("caption") or "")[:300], "link": x.get("permalink"),
                        "tarih": (x.get("timestamp") or "")[:10]})
    # hem hesabın kendine göre sıçrayanı (kat) hem takipçiye göre güçlü olanı öne al
    out.sort(key=lambda x: (min(x["kat"], 6) + 200 * x["oran"]), reverse=True)
    return out[:en_cok]


ISTEM = """Sen {marka} için çalışan deneyimli bir sosyal medya stratejistisin. Hedef kitle: {kitle}.
Aşağıda rakiplerin ve sektörde güçlü hesapların son 60 günde EN ÇOK TUTAN Instagram paylaşımları (kat = hesabın kendi ortalamasının
kaç katı etkileşim aldı) ve Türkiye'de son 30 günde bu alanda EN ÇOK İZLENEN YouTube Shorts videoları (izlenme) var. {tiktok}
Görevin: neden tuttuklarını çıkar ve {marka} için KOPYA OLMAYAN, kendi diliyle uygulanabilir fikirlere çevir.
Kurallar: yalnız verilen paylaşımlardan ve aramada bulduğun kaynaklardan çıkarım yap; rakam/trend UYDURMA. Rakip adını içerikte kullanma.
Argo, bahis/kumar, alkol, +18, siyaset içeren hiçbir fikir verme.
Paylaşımlar: {veri}
Yalnız JSON: {{"tutan_konular": ["..."], "kancalar": ["ilk 2 saniyede söylenen cümle kalıbı"], "formatlar": ["ör. önce-sonra, liste, mini skeç, ekran kaydı"],
"farklilasma": ["rakiplerin yapmadığı, bizim öne çıkabileceğimiz açı"], "kacinilacak": ["rakiplerde tutmayan ya da yorulmuş şey"],
"tiktok_trend": ["bu hafta Türkiye'de tutan format/ses (kaynaklıysa)"], "kanit": ["en iyi 3 paylaşımın bağlantısı"]}}"""


def ozet(sor, marka: str, kitle: str, tutan: list[dict], tiktok_metni: str = "") -> dict:
    """sor(istem) -> dict (hattın kendi Gemini sarmalayıcısı). Hata olursa boş özet; hat yine çalışır."""
    if not tutan and not tiktok_metni:
        return {}
    veri = json.dumps([{k: x.get(k) for k in ("hesap", "tur", "izlenme", "begeni", "yorum", "kat", "aciklama", "link")} for x in tutan], ensure_ascii=False)
    tk = f"Ayrıca bu haftanın Türkiye TikTok/Reels trend araştırması: {tiktok_metni[:2500]}" if tiktok_metni else ""
    try:
        v = sor(ISTEM.format(marka=marka, kitle=kitle, veri=veri, tiktok=tk)) or {}
    except Exception:  # noqa: BLE001
        return {}
    temiz = {k: [str(x)[:220] for x in (v.get(k) or []) if x and not uygunsuz(str(x))][:6]
             for k in ("tutan_konular", "kancalar", "formatlar", "farklilasma", "kacinilacak", "tiktok_trend", "kanit")}
    temiz["tarih"] = dt.date.today().isoformat()
    return temiz


def yazar_metni(o: dict) -> str:
    """Senaryo istemine eklenecek kısa bölüm."""
    if not o:
        return ""
    s = ["RAKİP VE TREND RADARI (" + o.get("tarih", "") + "; denenmiş, tutmuş içeriklerden — FİKİR al, KOPYALAMA, rakip adı geçmesin):"]
    for k, ad in (("tutan_konular", "Tutan konular"), ("kancalar", "Tutan kancalar"), ("formatlar", "Tutan formatlar"),
                  ("tiktok_trend", "TikTok/Reels trendi"), ("farklilasma", "Bizim farkımız olacak açı"), ("kacinilacak", "Kaçın")):
        if o.get(k):
            s.append(f"- {ad}: " + " | ".join(o[k][:4]))
    return "\n".join(s)


def ara(gemini_anahtari: str, soru: str, modeller=("gemini-flash-latest", "gemini-2.5-flash")) -> str:
    """Google arama destekli Gemini (TikTok/Reels trendleri için). Metin + kaynak bağlantıları; olmazsa ""."""
    govde = json.dumps({"contents": [{"parts": [{"text": soru}]}], "tools": [{"google_search": {}}],
                        "generationConfig": {"temperature": 0.3}}).encode()
    for m in modeller:
        try:
            req = urllib.request.Request(f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent", data=govde,
                                         headers={"Content-Type": "application/json", "x-goog-api-key": gemini_anahtari})
            with urllib.request.urlopen(req, timeout=90) as r:
                c = json.loads(r.read())["candidates"][0]
            metin = "".join(p.get("text", "") for p in c["content"]["parts"])
            kaynak = [w["web"]["uri"] for w in (c.get("groundingMetadata") or {}).get("groundingChunks", []) if "web" in w][:6]
            return metin[:3000] + ("\nKaynaklar: " + " ".join(kaynak) if kaynak else "")
        except Exception:  # noqa: BLE001
            continue
    return ""


TIKTOK_SORU = ("Bu hafta ({tarih}) Türkiye'de TikTok ve Instagram Reels'te {konu} alanında hangi video formatları, akımlar ve sesler "
               "viral oluyor? Yalnız bulduğun kaynaklara dayan, uydurma. Argo, bahis, kumar, +18 içerikleri dahil etme. 5 maddede, kısa yaz.")


def yt_erisim(istemci: str, sir: str, yenileme: str) -> str:
    """YouTube OAuth yenileme anahtarından kısa ömürlü erişim anahtarı ("" olursa YouTube trendi atlanır)."""
    try:
        veri = urllib.parse.urlencode({"client_id": istemci, "client_secret": sir, "refresh_token": yenileme, "grant_type": "refresh_token"}).encode()
        with urllib.request.urlopen(urllib.request.Request("https://oauth2.googleapis.com/token", data=veri), timeout=30) as r:
            return json.loads(r.read()).get("access_token", "")
    except Exception:  # noqa: BLE001
        return ""


def yt_trend(erisim: str, sorgular: list[str], gun: int = 30, en_cok: int = 8, api_anahtari: str = "") -> list[dict]:
    """Türkiye'de son `gun` günde en çok izlenen Shorts (sorgu başına 10 aday → izlenmeye göre). Ücretsiz kota: sorgu başına ~101 birim.
    Kimlik: OAuth erişim anahtarı ya da YouTube API anahtarı."""
    if not erisim and not api_anahtari:
        return []
    h = {"Authorization": f"Bearer {erisim}"} if erisim else {}
    ek = {"key": api_anahtari} if api_anahtari and not erisim else {}
    sinir = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=gun)).strftime("%Y-%m-%dT%H:%M:%SZ")
    idler = []
    for q in sorgular[:4]:
        p = {"part": "id", "q": q, "type": "video", "videoDuration": "short", "regionCode": "TR", "relevanceLanguage": "tr",
             "publishedAfter": sinir, "order": "viewCount", "maxResults": 10, **ek}
        try:
            with urllib.request.urlopen(urllib.request.Request("https://www.googleapis.com/youtube/v3/search?" + urllib.parse.urlencode(p), headers=h), timeout=30) as r:
                idler += [x["id"]["videoId"] for x in json.loads(r.read()).get("items", []) if x.get("id", {}).get("videoId")]
        except Exception:  # noqa: BLE001
            continue
    if not idler:
        return []
    try:
        p = {"part": "snippet,statistics", "id": ",".join(dict.fromkeys(idler))[:2000], **ek}
        with urllib.request.urlopen(urllib.request.Request("https://www.googleapis.com/youtube/v3/videos?" + urllib.parse.urlencode(p), headers=h), timeout=30) as r:
            v = json.loads(r.read()).get("items", [])
    except Exception:  # noqa: BLE001
        return []
    out = []
    for x in v:
        sn, st = x.get("snippet", {}), x.get("statistics", {})
        baslik = sn.get("title", "")
        if uygunsuz(baslik, sn.get("description", "")[:300], sn.get("channelTitle", "")):
            continue
        out.append({"hesap": sn.get("channelTitle", ""), "tur": "YouTube Shorts", "izlenme": int(st.get("viewCount") or 0),
                    "begeni": int(st.get("likeCount") or 0), "yorum": int(st.get("commentCount") or 0), "kat": 0,
                    "aciklama": baslik[:200], "link": f"https://www.youtube.com/shorts/{x['id']}"})
    out.sort(key=lambda x: -x["izlenme"])
    return out[:en_cok]
