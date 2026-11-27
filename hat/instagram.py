"""Instagram Graph API: yorum okuma (beğeni sayısıyla), yoruma yanıt, Reels yayını, ölçüm.
IG Otopilot'un kanıtlanmış yükleme/yayın akışından uyarlandı. Ücretsizdir; Profesyonel hesap gerekir.
Gerekli izinler: instagram_business_basic, instagram_business_manage_comments, instagram_business_content_publish
(Instagram ile Giriş) ya da Facebook sayfası üzerinden eşdeğerleri.
Hesap başına .env: IG_<HESAP>_ID, IG_<HESAP>_TOKEN, (isteğe bağlı) IG_<HESAP>_API=instagram|facebook"""
from __future__ import annotations

import time
from pathlib import Path

import requests

from ortak import env, gunluk

SURUM = "v25.0"


class InstagramHatasi(RuntimeError):
    pass


class BelirsizYayin(RuntimeError):
    """Yayımlayan istek platforma GİTTİ ama sonucu alınamadı/okunamadı (zaman aşımı, bağlantı kopması, 5xx, JSON olmayan yanıt):
    paylaşım gerçekleşmiş olabilir → kayda *_belirsiz yazılır, ASLA otomatik yeniden gönderilmez (Düzelt dahil), elle kontrol."""


def _yayin_istegi(yontem: str, url: str, ad: str, **k) -> dict:
    """Geri alınamaz (yayımlayan) istek. Bağlantı hiç kurulamadıysa (ConnectTimeout) istek gitmemiştir → InstagramHatasi
    (yeniden denenebilir). Diğer ağ hataları, 5xx, okunamayan yanıt → BelirsizYayin. 4xx: platform açıkça reddetti → InstagramHatasi."""
    try:
        r = requests.request(yontem, url, **k)
    except requests.ConnectTimeout as e:
        raise InstagramHatasi(f"{ad}: bağlantı kurulamadı (istek gitmedi)") from e
    except requests.RequestException as e:
        raise BelirsizYayin(f"{ad}: istek gönderildi, yanıt alınamadı ({type(e).__name__})") from e
    if r.status_code >= 500:
        raise BelirsizYayin(f"{ad}: platform {r.status_code} döndü; yayımlanmış olabilir")
    try:
        v = r.json()
    except ValueError as e:
        if r.ok:
            raise BelirsizYayin(f"{ad}: yanıt okunamadı (JSON değil)") from e
        v = {"error": r.text[:200]}
    if r.status_code >= 400 or (isinstance(v, dict) and "error" in v):
        raise InstagramHatasi(f"{ad} {r.status_code}: {str(v.get('error', v) if isinstance(v, dict) else v)[:300]}")
    return v


class Instagram:
    def __init__(self, hesap: str):
        k = hesap.upper()
        self.kimlik = env(f"IG_{k}_ID")
        self.anahtar = env(f"IG_{k}_TOKEN")
        api = env(f"IG_{k}_API", "instagram")
        self.kok = f"https://graph.{'instagram' if api == 'instagram' else 'facebook'}.com/{SURUM}"

    @property
    def hazir(self) -> bool:
        return bool(self.kimlik and self.anahtar)

    def _istek(self, yontem: str, yol: str, **p) -> dict:
        p["access_token"] = self.anahtar
        try:
            r = requests.request(yontem, f"{self.kok}/{yol}", params=p if yontem == "GET" else None,
                                 data=p if yontem != "GET" else None, timeout=120)
            v = r.json()
        except (requests.RequestException, ValueError) as e:
            raise InstagramHatasi(f"{yol}: {type(e).__name__}") from e
        if r.status_code >= 400 or "error" in v:
            raise InstagramHatasi(f"{yol}: {v.get('error', v)}")
        return v

    def son_medyalar(self, adet: int = 5) -> list[dict]:
        return self._istek("GET", f"{self.kimlik}/media", fields="id,permalink,timestamp,media_type,caption", limit=adet).get("data", [])

    def yorumlar(self, medya_id: str) -> list[dict]:
        """Üst düzey yorumlar: metin, kullanıcı adı, beğeni sayısı, zaman. Sayfalamayı izler (en çok 500)."""
        out, yol, p = [], f"{medya_id}/comments", {"fields": "id,text,username,like_count,timestamp", "limit": 50}
        while yol and len(out) < 500:
            v = self._istek("GET", yol, **p)
            out += v.get("data", [])
            sonraki = v.get("paging", {}).get("next")
            if not sonraki:
                break
            yol, p = sonraki.split(f"{SURUM}/", 1)[1].split("?", 1)[0], dict(x.split("=", 1) for x in sonraki.split("?", 1)[1].split("&") if not x.startswith("access_token"))
        return out

    def yanitla(self, yorum_id: str, mesaj: str) -> dict:
        return self._istek("POST", f"{yorum_id}/replies", message=mesaj)

    def yorum_yaz(self, medya_id: str, mesaj: str) -> dict:
        return self._istek("POST", f"{medya_id}/comments", message=mesaj)

    def _yukle(self, video: Path, **alanlar) -> str:
        kap = self._istek("POST", f"{self.kimlik}/media", upload_type="resumable", **alanlar)
        with open(video, "rb") as f:
            r = requests.post(kap["uri"], data=f, timeout=600, headers={
                "Authorization": f"OAuth {self.anahtar}", "offset": "0", "file_size": str(video.stat().st_size)})
        if r.status_code >= 400:
            raise InstagramHatasi(f"yükleme {r.status_code}: {r.text[:300]}")
        for _ in range(60):
            d = self._istek("GET", kap["id"], fields="status_code,status")
            if d.get("status_code") == "FINISHED":
                return kap["id"]
            if d.get("status_code") in ("ERROR", "EXPIRED"):
                raise InstagramHatasi(f"işleme hatası: {d.get('status')}")
            time.sleep(10)
        raise InstagramHatasi("işleme zaman aşımı")

    def reels(self, video: Path, aciklama: str, ortaklar: list[str] | None = None, kapak_ms: int = 300) -> dict:
        aciklama = aciklama_denetle(aciklama)
        alan = dict(media_type="REELS", caption=aciklama, share_to_feed="true", thumb_offset=str(kapak_ms))
        if ortaklar:  # ortak gönderi daveti (API'de en çok 3 kullanıcı adı)
            alan["collaborators"] = str(ortaklar[:3]).replace("'", '"')
        for tekrar in range(4):   # yeni hesaplarda rupload ara ara ProcessingFailedError veriyor → bekle, yeni kapsayıcıyla dene
            try:
                kap = self._yukle(video, **alan); break
            except InstagramHatasi as e:
                # 2026-11-26: yorum yazan gizli/geçersiz hesap ortak eklenince Instagram TÜM paylaşımı reddediyor (2207018)
                # → ortak daveti olmadan aynı videoyla yeniden dene (paylaşım düşmesin)
                if alan.get("collaborators") and ("2207018" in str(e) or "Invalid user id" in str(e) or "erişilemiyor" in str(e)):
                    gunluk(f"ortak eklenemedi ({alan['collaborators']}: gizli/geçersiz hesap) → ortaksız paylaşılıyor")
                    alan.pop("collaborators")
                    continue
                if "ProcessingFailed" not in str(e) or tekrar == 3:
                    raise
                gunluk(f"yükleme reddedildi, {90 * (tekrar + 1)} sn sonra yeniden denenecek")
                time.sleep(90 * (tekrar + 1))
        for deneme in range(5):
            try:   # "not ready" Instagram'ın açık reddi (yayımlanmadı) → bekleyip aynı kapsayıcıyla yeniden; yanıtsızlık → BelirsizYayin
                m = _yayin_istegi("POST", f"{self.kok}/{self.kimlik}/media_publish", "instagram media_publish", timeout=120,
                                  data={"creation_id": kap, "access_token": self.anahtar})
                break
            except InstagramHatasi as e:
                if "not ready" in str(e).lower() and deneme < 4:
                    time.sleep(15); continue
                raise
        if not m.get("id"):
            raise BelirsizYayin("instagram media_publish: yanıtta medya kimliği yok")
        try:   # yayın TAMAM: bağlantı okunamasa da medya kimliği döner (yeniden paylaşılmaz)
            b = self._istek("GET", m["id"], fields="id,permalink,timestamp")
        except InstagramHatasi as e:
            gunluk(f"Reels yayında ama bağlantısı okunamadı ({e}); medya {m['id']}")
            b = {"id": m["id"], "permalink": None}
        gunluk(f"Reels yayında: {b.get('permalink')}")
        return b



_DENETLENMIS: dict = {}


def aciklama_denetle(metin: str, platform: str = "instagram") -> str:
    """Ortak açıklama denetçisi (2026-11-27): TDK yazım, kesik satır, soru işareti, 3-5 hashtag. Aynı metin bir kez
    denetlenir (IG/FB/YT aynı açıklamayı kullanır). Hata paylaşımı durdurmaz."""
    if metin in _DENETLENMIS:
        return _DENETLENMIS[metin]
    try:
        import json as _json
        import aciklama_denetim as ad
        import ortak
        r = ad.denetle(metin, platform, llm=lambda istem: _json.dumps(
            ortak.json_sor("Sen titiz bir Türkçe editörsün. Yalnız istenen JSON'u döndür.", istem, sicaklik=0.1), ensure_ascii=False))
        if r["duzeltmeler"] or r["hatalar"]:
            gunluk(f"açıklama denetimi: düzeltme={r['duzeltmeler'][:6]} uyarı={r['hatalar'][:3]}")
        yeni = r["metin"] or metin
    except Exception as e:  # noqa: BLE001
        gunluk(f"açıklama denetimi çalışmadı: {type(e).__name__}")
        yeni = metin
    _DENETLENMIS[metin] = yeni
    _DENETLENMIS[yeni] = yeni
    return yeni


def facebook_reels(hesap: str, video: Path, aciklama: str) -> str:
    aciklama = aciklama_denetle(aciklama, "facebook")
    """Aynı videoyu hesabın Facebook sayfasına Reels olarak yayımlar (sayfa anahtarı = IG_<HESAP>_TOKEN; pages_manage_posts gerekir).
    Hata fırlatabilir; çağıran yakalar (Instagram paylaşımını etkilemez)."""
    k = hesap.upper()
    sayfa, t = env(f"META_{k}_PAGE_ID"), env(f"IG_{k}_TOKEN")
    if not (sayfa and t):
        raise InstagramHatasi(f"{hesap}: Facebook sayfası bilgisi yok")
    g = f"https://graph.facebook.com/{SURUM}"
    r = requests.post(f"{g}/{sayfa}/video_reels", data={"upload_phase": "start", "access_token": t}, timeout=60)
    if not r.ok:
        raise InstagramHatasi(f"facebook başlatma {r.status_code}: {r.text[:200]}")
    vid = r.json()["video_id"]
    veri = video.read_bytes()
    u = requests.post(f"https://rupload.facebook.com/video-upload/{SURUM}/{vid}", data=veri, timeout=900,
                      headers={"Authorization": f"OAuth {t}", "offset": "0", "file_size": str(len(veri))})
    if not u.ok:
        raise InstagramHatasi(f"facebook yükleme {u.status_code}: {u.text[:200]}")
    j = _yayin_istegi("POST", f"{g}/{sayfa}/video_reels", f"facebook yayın (video {vid})", timeout=120, data={
        "upload_phase": "finish", "video_id": vid, "video_state": "PUBLISHED", "description": aciklama, "access_token": t})
    if j.get("success") is not True:   # Meta açıkça başarısız dedi: yayımlanmadı
        raise InstagramHatasi(f"facebook yayın başarısız: {str(j)[:200]}")
    gunluk(f"Facebook Reels yayında: https://www.facebook.com/reel/{vid}")
    return f"https://www.facebook.com/reel/{vid}"


YT_MARKA = {"kartvizit": "Kartvizitçi", "web": "Siteci Abi", "para": "Cüzdan Hocası"}


def youtube_metni(hesap: str, metin: str, ig_kullanici: str) -> tuple[str, str]:
    """IG açıklamasını YouTube'a uyarlar (Mücahit Çakır kanalı, karma içerik): başlıkta seri adı, yorumla seçim IG'de."""
    satirlar = metin.strip().splitlines()
    ilk = (satirlar[0] if satirlar else "Yeni bölüm").strip()
    baslik = f"{YT_MARKA.get(hesap, '')} | {ilk}".strip(" |")
    baslik = (baslik[:90].rstrip(" .–-") + " #shorts")[:100]
    govde = []
    for s in satirlar:
        if "Sıradaki bütçe senin olsun" in s:
            s = f"💬 Yarının bütçesi Instagram'daki videonun yorumlarından seçiliyor: instagram.com/{ig_kullanici}"
        if "yorumlarından seçilecek" in s:
            s = f"💬 Yarının firması Instagram'daki videonun yorumlarından seçiliyor: instagram.com/{ig_kullanici}"
        s = s.replace("@sitemucidi", "Site Mucidi (sitemucidi.com.tr)")
        govde.append(s)
    return baslik, "\n".join(govde)[:4900]


def youtube_shorts(hesap: str, video: Path, metin: str, ig_kullanici: str) -> str:
    metin = aciklama_denetle(metin, "youtube")
    """Aynı videoyu YouTube Shorts olarak yükler (YT_CLIENT_ID/SECRET/REFRESH_TOKEN; Mücahit Çakır kanalı).
    Hata fırlatabilir; çağıran yakalar (Instagram paylaşımını etkilemez)."""
    cid, sec, rt = env("YT_CLIENT_ID"), env("YT_CLIENT_SECRET"), env("YT_REFRESH_TOKEN")
    if not (cid and sec and rt):
        raise RuntimeError("YouTube anahtarı yok")
    r = requests.post("https://oauth2.googleapis.com/token", timeout=30, data={
        "client_id": cid, "client_secret": sec, "refresh_token": rt, "grant_type": "refresh_token"})
    r.raise_for_status()
    a = r.json()["access_token"]
    baslik, acik = youtube_metni(hesap, metin, ig_kullanici)
    etiket = [w.lstrip("#") for w in metin.split() if w.startswith("#")][:15]
    govde = {"snippet": {"title": baslik, "description": acik, "tags": etiket, "categoryId": "22",
                         "defaultLanguage": "tr", "defaultAudioLanguage": "tr"},
             "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}}
    b = requests.post("https://www.googleapis.com/upload/youtube/v3/videos", params={"uploadType": "resumable", "part": "snippet,status"},
                      headers={"Authorization": f"Bearer {a}", "X-Upload-Content-Type": "video/mp4",
                               "X-Upload-Content-Length": str(video.stat().st_size)}, json=govde, timeout=60)
    b.raise_for_status()
    with open(video, "rb") as f:   # asıl yükleme = yayın: gittikten sonra yanıtsızlık → BelirsizYayin
        y = _yayin_istegi("PUT", b.headers["Location"], "youtube yükleme", data=f, headers={"Content-Type": "video/mp4"}, timeout=900)
    if not y.get("id"):
        raise BelirsizYayin("youtube yükleme: yanıtta video kimliği yok")
    link = "https://youtube.com/shorts/" + y["id"]
    gunluk(f"YouTube Shorts yayında: {link}")
    return link
