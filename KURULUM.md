# Yorumdan Tasarım — otomatik kartvizit + web sitesi dizisi

Her gün, iki hesabın (matbaa/kartvizit ve web tasarım) son bölümünün yorumlarından en çok beğeni alan **firma adı + sektör** yorumunu seçer;
mizahlı anlatımlı, tasarımın yapılışını gösteren 3B Reels'i kendiliğinden üretir ve paylaşır. İnsan onayı beklemez.

## Akış (hat/gunluk.py)
1. **Yorum topla** (hat/yorumlar.py): son bölümün yorumları + beğeni sayıları (Instagram Graph API).
2. **Firma seç** (hat/sec.py): küfür/siyaset/alkol/kumar/Turaklar elenir → Gemini firma, sektör, şehir çıkarır; büyük zincir markalar, kamu, troll, kişisel isim **reddedilir** →
   en çok beğeni (+ yazan firma sahibiyse +2). Uygun yorum yoksa `icerik/yedek-firmalar.json` (kendi markalarımız) sırası.
3. **Günün yıldızı**: kartvizitte perdah (oval kesim, kabartma, altın varak, lokal lak, kraft, çift kalın — `icerik/perdahlar.json`),
   webde Site Mucidi'de gerçekten çıkan bölüm (galeri, ürün kataloğu, SSS, harita, süreç, hakkımızda — `icerik/site-ozellikleri.json`). Son 7 bölümde tekrar etmez.
4. **Senaryo** (hat/senaryo.py): Gemini (yalnız ücretsiz katman, model otomatik keşif) `icerik/uzman-kurallari.md` ile vuruş vuruş yazar; denetim
   (kelime sayısı, yasak kelime, rakam, uzun cümle) geçmezse bir kez düzelttirir, yine olmazsa kural tabanlı yedek senaryo. Kapanış sabit, kod ekler.
5. **Ses** (hat/ses.py): Gemini TTS (Fenrir) → **dosya sonundaki 0,16 sn çöp kesilir** (cızırtının kaynağı) → Whisper ile doğrulama (benzerlik ≥ 0,62) ve cümle hizalama.
6. **Video**: kartvizit (hat/kartvizit.py + sablon/kartvizit) / web (hat/web.py + sablon/web, site Site Mucidi motoruyla üretilir, yayına alınmaz).
   Tüm sahne zamanları cümle başlarından hesaplanır. Ses miksi: konuşmada kısılan müzik, efektler, iki geçişli -14 LUFS, tepe sınırı.
7. **Kalite denetimi**: süre, ses seviyesi, sonda ani sıçrama/parazit. Geçmezse **paylaşmaz** (günlükte yazar).
8. **Paylaş** (mod=canli): Reels + ortak gönderi daveti (firma kendisi yazdıysa + @mchttasarim), ilk yorum (kural), kazanan yoruma tebrik yanıtı.
9. **Kayıt**: `durum/<hesap>-bolumler.json`, kullanılan firmalar, son espriler (tekrar etmesin).

## Çalıştırma
```
cd ~/Documents/yorumdan-tasarim
.venv/bin/python hat/gunluk.py --hesap kartvizit --deneme   # örnek yorumlarla, paylaşmadan → cikti/
.venv/bin/python hat/gunluk.py                               # ayarlar.json moduna göre iki hesap
```
Bir bölüm ~1,5–3 dk'da üretilir (Mac'te). Çıktı + açıklama metni `cikti/` altında.

## Canlıya almak için GEREKENLER (Mücahit)
1. İki yeni Instagram hesabı (Profesyonel/İşletme) ve adları → `ayarlar.json` `ig_kullanici`.
2. Her hesap için Meta uygulamasından anahtar: `.env` → `IG_KARTVIZIT_ID`, `IG_KARTVIZIT_TOKEN`, `IG_WEB_ID`, `IG_WEB_TOKEN`
   (izinler: instagram_business_basic, instagram_business_manage_comments, instagram_business_content_publish).
3. Bu projeye ayrı ücretsiz Gemini anahtarı (`.env` GEMINI_API_KEY; şu an Muhit'in anahtarı kopyalandı, kotası paylaşılıyor). Ödeme hesabı BAĞLANMAZ.
4. Karar: **yapay zekâ ses etiketi** (`ayarlar.json` ai_etiketi). Meta gerçekçi yapay zekâ sesinde "AI info" etiketini istiyor.
5. `ayarlar.json` → `"mod": "canli"`, sonra zamanlayıcı: `cp sistem/com.mcht.yorumdan-tasarim.plist ~/Library/LaunchAgents/ && launchctl load ~/Library/LaunchAgents/com.mcht.yorumdan-tasarim.plist`
   (kartvizit her gün 12:15, web 19:15 — sistem/com.mcht.yorumdan-{kartvizit,web}.plist; Mac uyanık olmalı. Sunucuya taşımak istenirse Chrome + Mesa ile VDS'te de çalışır, disk durumu önce kontrol edilmeli.)
6. Müzik çeşitliliği: `icerik/muzik/` içine birkaç telifsiz (Pixabay) parça daha ekle; her bölümde rastgele seçilir.
7. İlk 5–10 bölüm için `icerik/yedek-firmalar.json`: yorum gelene kadar kendi markalarımızla tohumlanır.

## Bilinen sınırlar
- Kartvizit tasarımı monogram + firma adı + slogandır (firmanın gerçek logosu otomatik alınmaz). Arka yüzde Instagram adresi + profil karekodu.
- Web sitesi içerikleri Site Mucidi sektör örnek metinleridir ("içerik temsilidir" notu videoda). Örnek fotoğraflar Wikimedia Commons; açıklamaya kaynak satırı eklenir.
- Gemini ücretsiz kotası dolarsa yedek senaryo, TTS kotası dolarsa o gün bölüm üretilmez (robotik yedek ses kullanılmaz).
- Araştırma raporu: `arastirma/viral-arastirma.md` (algoritma sinyalleri, mizah rehberi, 30 günlük büyüme planı).

## Instagram bağlantısı (2026-11-25 kuruldu)
- @kartvizitci.tr (IG 17841462414867011) ↔ FB "Kartvizitçi" (API sayfa 1447799135087040)
- @siteci.abi (IG 17841480263876164) ↔ FB "Siteci Abi" (API sayfa 1529709613552826)
- Anahtarlar `.env`: IG_<HESAP>_ID / IG_<HESAP>_TOKEN (süresiz SAYFA anahtarı) / IG_<HESAP>_API=facebook.
- Yeniden almak gerekirse: Graph API Explorer (uygulama "Mchttasarım Marka Yönetim") → Generate Access Token → Access Token Debugger "Extend" → `/{sayfa}?fields=access_token`.
- Yeni sayfa eklemek için açılır pencere gerekmez: Facebook Ayarlar → İşletme Entegrasyonları → Mchttasarım Marka Yönetim → Gör ve düzenle → her izin bölümünde hesabı/sayfayı işaretle → Kaydet.
- Veri erişimi 90 günde bir kullanımla yenilenir; hat her gün çalıştığı sürece düşmez.

## Cüzdan Hocası (hesap "para", 2026-11-26)
- @cuzdanhocasi (IG 17841434020368521) ↔ FB "Cüzdan Hocası" (profil 61596915873234, API sayfa 1443321028870812). İşletme hesabı, Eğitim kategorisi.
- `.env`: IG_PARA_ID / IG_PARA_TOKEN (süresiz SAYFA anahtarı, expires 0) / IG_PARA_API=facebook / META_PARA_PAGE_ID.
- Anahtar yolu: İşletme Entegrasyonları'nda sayfa+IG işaretlendi → Graph Explorer kullanıcı anahtarı → Access Token Debugger "Extend" (bu kez şifre istemedi) →
  /me/accounts sayfa anahtarı. developers.facebook.com CSP'si localhost'a fetch'i engeller → anahtar panoya kopyalanıp `pbpaste` ile .env'e yazıldı, pano temizlendi.
- Hat: hat/para.py + hat/butce.py + sablon/para; launchd com.mcht.yorumdan-para her gün 20:30. Kurallar icerik/para-kurallari.md.

## Bulutta çalışma (2026-11-27) — Mac kapalıyken de
- Kod: **açık** depo github.com/mcht54/yorumdan-hat (yerel `acik` dalı → `git push acik acik:main`). Sırlar GitHub gizli ayarlarında (14 adet), `.env` gitte YOK.
- Kayıtlar: **özel** depo github.com/mcht54/yorumdan-durum = yerel `durum/` klasörü (iç içe git). `ortak.durum_esitle` her çalışmada pull → … → commit+push.
  Actions bu depoya yazma deploy anahtarıyla (sır DURUM_DEPLOY_KEY) erişir.
- Zamanlama `.github/workflows/gunluk.yml` (UTC): 09:15 Kartvizitçi, 09:30 Yılda Kaça Patlıyor?, 14:30 Maaş Kapışması, 17:30 Bütçe Kliniği. Elle deneme: Actions › gunluk › Run workflow (deneme=true).
- Açık depo olduğu için Actions kayıtlarına günlük yazılmaz (YORUMDAN_SESSIZ=1); ayrıntı durum/gunluk.log'da.
- Siteci Abi (web) Site Mucidi motoruna bağlı → Mac'te kalır (launchd 19:15), aynı durum deposunu kullanır. Panel senkronu (Mac, 10 dk) önce durum'u çeker.
- Mac'teki kartvizit ve para launchd işleri bulut doğrulanınca KALDIRILDI (çift paylaşım olmasın).
