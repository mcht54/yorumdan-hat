"""Günün senaryosu: Gemini (ücretsiz) uzman kurallarıyla vuruş vuruş anlatım + tasarım kararları yazar.
Gemini yoksa ya da kurallara uymazsa kural tabanlı yedek senaryo kullanılır (yayın durmaz)."""
from __future__ import annotations

import json
import random
import re

from ortak import ICERIK, gunluk, json_sor, oku

KAPANIS = {
    "kartvizit": "Her gün yeni bir firma, yeni bir tasarım! Sıradaki kartvizit senin olsun: yorumlara firma adını ve sektörünü yaz, en çok beğeni alan kazanır!",
    "web": "Her gün yeni bir firma, yeni bir site! Sıradaki web sitesi senin olsun: yorumlara firma adını ve sektörünü yaz, en çok beğeni alan kazanır!",
}
# 2026-11-25 kullanıcı: "espri ve bilgi mizahını genişlet, aynı konulara sıkışma, viral olsun". Son bölümlerin çoğu
# "X font seçsek Y sanılırdı" kalıbındaydı → her bölüm iki FARKLI mizah türüyle yazılır; tür son 2 bölümde tekrar etmez.
MIZAH = {
    "bilgi": "BİLGİ MİZAHI: uzman-kurallari.md 'Bilgi havuzu'ndan gerçek bir bilgi + tebessüm (ör. 'Karekod aslında Japonya'da araba parçası saymak için icat edildi; şimdi dönerin menüsünü sayıyor.'). Havuz dışı bilgi ve rakam uydurma.",
    "esnaf_repligi": "ESNAF REPLİĞİ: o sektörün her gün duyulan gerçek cümlesi ('Abi bir bakar mısın, sadece uçlarından', 'Usta bu araba ne zaman çıkar?') ve tasarımın buna cevabı.",
    "mini_sahne": "MİNİ SAHNE: iki kısa cümlelik müşteri-esnaf diyaloğu ('Müşteri: Açık mısınız? Siteci Abi: Sitede yazıyor kardeşim, sabah sekiz.').",
    "kendine_takilma": "KENDİNE TAKILMA: tasarımcının/Siteci Abi'nin kendi hâline gülmesi (kahvesi soğur, rengi seçemez, gözü kâğıda takılır).",
    "abarti": "TATLI ABARTI: tasarımın etkisini sevimli abartmak ('O kadar parlak ki kartı güneş gözlüğüyle verin.').",
    "uclemeli": "ÜÇLEME: iki normal öğe, üçüncüsü sürpriz ('Telefon, adres ve... annenizin yemek yedin mi sorusu yok.').",
    "kelime_oyunu": "KELİME OYUNU: sektörün kendi kelimesiyle çift anlam ('Lastikçiye köşesi yuvarlak kart; yolda patlak olmasın.'). Zorlamaysa başka tür seç.",
    "beklenti_kirma": "BEKLENTİ KIRMA: cümle bir yöne gider, son kelime ters köşe yapar ('Bu sitede her şey var: menü, harita, bir de... bayatlamayan ekmek.').",
}
YASAK_KALIP = r"sanıl(ır|ırdı|ır mı)|sanırlar|sanırdı|sanırsınız"  # "X yapsak Y sanılırdı" kalıbı aşırı tekrarlandı


def mizah_sec(tur: str) -> list[str]:
    """Bu bölüm için iki farklı mizah türü: son 2 bölümde kullanılanlar dışından."""
    son = [t for x in oku(f"{tur}-son-mizah.json", [])[-2:] for t in x]
    aday = [k for k in MIZAH if k not in son] or list(MIZAH)
    if len(aday) < 3:
        aday = list(MIZAH)
    if tur == "web" and "mini_sahne" in aday and random.random() < 0.6:  # Siteci Abi: paylaşılan an müşteri-esnaf sahnesi
        return ["mini_sahne"] + random.sample([k for k in aday if k != "mini_sahne"], 2)
    return random.sample(aday, 3)


YASAK_KELIME = ["muhteşem", "inanılmaz", "haydi", "kaçırmayın", "keşfedelim", "kanka", "turaklar", "garanti", "en iyi", "bir numara"]

SEMA = {
    "kartvizit": """{
 "kanca": "1 cümle. Firma adı + sektör + merak. (ör. 'Bugün yorumlardan bir dönerci geldi: Lezzet Durağı!')",
 "tanitim": "1-2 kısa cümle, sıcak bir giriş esprisi (tasarımcının kendine takılması).",
 "font": ["'Önce yazı tipi.' gibi kısa cümle", "yanlış yazı tipi (Comic Sans) ekranda; bunun esprisi sektöre bağlı ('X değil Y sanılırdı' kalıbı YASAK)", "doğru yazı tipine geçişi anlatan kısa cümle"],
 "renk": ["'Renk...' gibi kısa cümle", "sektöre hiç uymayan renk ekranda (yanlis_renk_ad ile birebir aynı renk); espri yanlış fonttakinden FARKLI bir mekanizmayla", "doğru renkleri söyleyen kısa cümle"],
 "perdah": ["günün perdahını açılış anıyla anlatan cümle", "perdahla sektörü bağlayan sıcak espri"],
 "arka": ["arka yüze ne koyduğumuzu anlatan kısa cümle (Instagram adresi ve karekod)", "kısa tamamlayıcı cümle"],
 "maket": ["'Ve işte, baskıya hazır!' benzeri", "açılış esprisine geri dönen (callback) kısa cümle"],
 "slogan": "kart üstü 2-4 kelimelik, iddiasız sıcak slogan (ör. 'Lezzetin durağı')",
 "yanlis_renk_ad": "esprideki yanlış renk adı (ör. 'pembe-mor')",
 "yanlis_renk": ["#hex", "#hex"],
 "dogru_renk": {"ana": "#hex koyu ya da zemin rengi", "vurgu": "#hex canlı vurgu", "yazi": "#hex"},
 "font_stil": "modern | klasik | guclu | samimi",
 "kapak_baslik": "kapak/ilk kare için 2-4 kelime (ör. 'Dönerciye kartvizit')",
 "aciklama": "Instagram açıklaması: ilk satır '<Firma> için <perdah> kartvizit tasarımı – Gün <n>', sonra 2 kısa cümle; hashtag yok",
 "soru": "yorumda TEK KELİMEYLE cevaplanacak iki seçenekli soru, bu bölümün tasarım kararıyla ilgili (ör. 'Kraft mı parlak mı?', 'Koyu mu açık mı?'); en fazla 6 kelime, soru işaretiyle biter",
 "etiketler": ["en fazla 5 hashtag: 2 tür, 1 sektör, 1 şehir, 1 seri (#yorumdantasarım)"]
}""",
    "web": """{
 "kanca": "1 cümle. Firma adı + sektör + merak.",
 "tanitim": "1-2 kısa cümle; bugün ona yepyeni bir site yaptığımızı sıcak bir espriyle söyle (sitesi olmadığını iddia etme).",
 "kapak": ["'Önce kapak fotoğrafı.' gibi kısa cümle", "yanlış fotoğraf anı: verilen YANLIŞ_FOTO sektörünün fotoğrafı konuyor; espri sektöre bağlı ('yanlışlıkla X koyduk, usta uyardı' kalıbını tekrar etme)", "doğru, sektöre uygun fotoğrafa geçiş cümlesi"],
 "baslik": ["sitenin başlığını yazarken söylenen kısa cümle"],
 "icerik": ["hizmet/ürün kartlarının dizildiğini anlatan kısa cümle", "sektöre bağlı sıcak espri; esnafın kendini göreceği, arkadaşına göndereceği an"],
 "ozellik": ["günün Site Mucidi özelliğini açılış anıyla anlatan cümle", "özelliği sektöre bağlayan espri"],
 "cihaz": "'Telefonda da hazır, bilgisayarda da!' benzeri",
 "hazir": "'Bu site Site Mucidi'nde satışa hazır bekliyor.' benzeri; callback espri eklenebilir",
 "site_baslik": "sitenin ana başlığı, 3-6 kelime, iddiasız",
 "site_alt": "site alt başlığı, 8-14 kelime, iddiasız",
 "kapak_baslik": "kapak için 2-4 kelime",
 "aciklama": "Instagram açıklaması: ilk satır '<Firma> için <özellik> web sitesi tasarımı – Gün <n>', sonra 2 kısa cümle; hashtag yok",
 "soru": "yorumda TEK KELİMEYLE cevaplanacak iki seçenekli soru, bu bölümün tasarım kararıyla ilgili (ör. 'Kraft mı parlak mı?', 'Koyu mu açık mı?'); en fazla 6 kelime, soru işaretiyle biter",
 "etiketler": ["en fazla 5 hashtag"]
}""",
}


def kurallar() -> str:
    return (ICERIK / "uzman-kurallari.md").read_text()


def _metinler(tur: str, s: dict) -> list[tuple[str, str]]:
    """Vuruş adı + cümle listesi (anlatım sırası)."""
    sira = ["kanca", "tanitim", "font", "renk", "perdah", "arka", "maket"] if tur == "kartvizit" else \
           ["kanca", "tanitim", "kapak", "baslik", "icerik", "ozellik", "cihaz", "hazir"]
    out = []
    for v in sira:
        d = s.get(v)
        for c in (d if isinstance(d, list) else [d]):
            if c and str(c).strip():
                out.append((v, str(c).strip()))
    out.append(("kapanis", KAPANIS[tur]))
    return out


def denetle(tur: str, s: dict) -> list[str]:
    sorun = []
    metin = " ".join(c for _, c in _metinler(tur, s))
    kelime = len(metin.split()) - len(KAPANIS[tur].split())
    if not 55 <= kelime <= 85:
        sorun.append(f"anlatım {kelime} kelime (55-85 olmalı)")
    for y in YASAK_KELIME:
        if y in metin.lower():
            sorun.append(f"yasak kelime: {y}")
    if re.search(r"\d", metin.replace(KAPANIS[tur], "")):
        sorun.append("rakam var (sayılar yazıyla)")
    if re.search(YASAK_KALIP, metin.lower()):
        sorun.append("'X değil Y sanılırdı' kalıbı yasak (son bölümlerde aşırı tekrarlandı); başka espri mekanizması kullan")
    if metin.count("!") > 7:
        sorun.append("çok ünlem")
    for v in (["font", "renk", "perdah", "arka", "maket"] if tur == "kartvizit" else ["kapak", "icerik", "ozellik"]):
        if not isinstance(s.get(v), list) or len(s[v]) < 2:
            sorun.append(f"{v} en az 2 cümle olmalı")
    for v, c in _metinler(tur, s):
        if v != "kapanis" and len(c.split()) > 16:
            sorun.append(f"uzun cümle: {c[:40]}…")
    return sorun


def yaz(tur: str, firma: dict, gun: int, yildiz: dict, yanlis_foto: str = "") -> dict:
    ornek = oku(f"{tur}-son-espriler.json", [])[-8:]
    mz = mizah_sec(tur)
    istem = f"""Tür: {'kartvizit' if tur == 'kartvizit' else 'web sitesi'} bölümü, Gün {gun}.
Firma: {firma['firma']} · Sektör: {firma['sektor']} · Şehir: {firma.get('sehir') or '-'}
{('HESAP SAHİBİNİN İSTEĞİ (öncelikli; bölümü bu isteğe göre kur, tema/özel gün/espri isteğini uygula): ' + firma['istek']) if firma.get('istek') else 'Seçilen yorum (@' + (firma.get('kullanici') or '-') + ', ' + str(firma.get('begeni', 0)) + ' beğeni): "' + firma.get('yorum', '') + '"'}
Günün yıldızı: {yildiz['ad']} — açılış anı: {yildiz['acilis']}
{('YANLIŞ_FOTO (espri için yanlışlıkla konan fotoğrafın sektörü): ' + yanlis_foto) if yanlis_foto else ''}
ESPRİ SAYISI: en az 4-5 espri — tanıtımda, yanlış yazı tipinde, yanlış renk/fotoğrafta, perdah/özellikte ve kapanışta (açılışa geri dönüş).
BU BÖLÜMÜN MİZAH TÜRLERİ (sınır değil; esprileri bu türlere dağıt, art arda iki espri aynı mekanizma olmasın):
1. {MIZAH[mz[0]]}
2. {MIZAH[mz[1]]}
3. {MIZAH[mz[2]]}
{firma.get('_radar') or ''}
Son bölümlerde kullanılan espriler (konusu da kalıbı da tekrar etmesin): {json.dumps(ornek, ensure_ascii=False)}
Şu JSON şemasını doldur (yalnız JSON):
{SEMA[tur]}"""
    kim = "Sen Siteci Abi'sin: sıcak, esprili, esnaf dostu bir Türk web tasarımcısı-anlatıcı." if tur == "web" else "Sen sıcak, esprili bir Türk tasarımcı-anlatıcısın."
    sistem = kim + " Kısa Reels anlatımı yazarsın. Aşağıdaki kurallara harfiyen uy.\n\n" + kurallar()
    for deneme in range(2):
        try:
            s = json_sor(sistem, istem + ("" if deneme == 0 else f"\nÖnceki denemede sorunlar vardı, düzelt: {sorunlar}"), 0.95)
        except Exception as e:  # noqa: BLE001
            gunluk(f"senaryo yazılamadı: {e}"); break
        sorunlar = denetle(tur, s)
        if not sorunlar:
            s["_kaynak"] = "gemini"; s["_mizah"] = mz
            return s
        gunluk(f"senaryo denetimi: {sorunlar}")
    gunluk("yedek senaryo kullanılıyor")
    return yedek(tur, firma, gun, yildiz, yanlis_foto)


def yedek(tur: str, firma: dict, gun: int, yildiz: dict, yanlis_foto: str = "") -> dict:
    f, sk = firma["firma"], firma["sektor"].lower()
    if tur == "kartvizit":
        return {"_kaynak": "yedek", "kanca": f"Bugün yorumlardan bir {sk} geldi: {f}!", "tanitim": "Kollarımızı sıvadık, kahvemizi koyduk. Başlıyoruz.",
                "font": ["Önce yazı tipi.", "Comic Sans mı? Yok, o kadar da rahat değiliz.", "Net, okunaklı, güven veren bir yazı tipi."],
                "renk": ["Renk...", "Pembe-mor mu? Bu kartvizit değil, doğum günü balonu olur.", "Sektöre yakışan, sıcak ve sade renkler."],
                "perdah": [f"Bugünün sürprizi: {yildiz['ad']}.", "Elinize alınca fark edeceksiniz, söz."],
                "arka": ["Arkasına Instagram adresi ve bir karekod.", "Okutan direkt sizi bulur."],
                "maket": ["Ve işte, baskıya hazır!", "Kahvemiz soğudu ama kart sıcacık oldu."],
                "slogan": "Güvenin adresi", "yanlis_renk_ad": "pembe-mor", "yanlis_renk": ["#ff4fd8", "#8a2be2"],
                "dogru_renk": {"ana": "#14161c", "vurgu": "#d0021b", "yazi": "#ffffff"}, "font_stil": "modern",
                "kapak_baslik": f"{firma['sektor']} kartviziti", "aciklama": f"{f} için {yildiz['ad']} kartvizit tasarımı – Gün {gun}\nYorumlardan gelen firmaya kartvizit tasarladık.",
                "etiketler": ["#kartvizit", "#kartvizittasarımı", "#" + re.sub(r"\W", "", sk), "#sakarya", "#yorumdantasarım"]}
    return {"_kaynak": "yedek", "kanca": f"Bugün yorumlardan bir {sk} geldi: {f}!", "tanitim": "Ama bir sorun var: web sitesi yok. Hemen başlıyoruz.",
            "kapak": ["Önce kapak fotoğrafı.", f"Bu ne? Bir {yanlis_foto or 'başka sektör'} fotoğrafı mı? Yanlış dosya!", "İşte, tam sektöre uygun bir kapak."],
            "baslik": ["Başlığı yazıyoruz."], "icerik": ["Hizmetler tek tek diziliyor.", "Müşteri ne arıyorsa ilk bakışta görsün."],
            "ozellik": [f"Bugünün özelliği: {yildiz['ad']}.", "Tek dokunuşla iş tamam."], "cihaz": "Telefonda da hazır, bilgisayarda da!",
            "hazir": "Bu site, Site Mucidi'nde satışa hazır bekliyor.", "site_baslik": f"{f}", "site_alt": f"{firma.get('sehir') or 'Sakarya'}'da güvenilir {sk} hizmeti; bize ulaşın, yardımcı olalım.",
            "kapak_baslik": f"{firma['sektor']} sitesi", "aciklama": f"{f} için {yildiz['ad']} web sitesi tasarımı – Gün {gun}\nYorumlardan gelen firmaya web sitesi yaptık.",
            "etiketler": ["#websitesi", "#webtasarım", "#" + re.sub(r"\W", "", sk), "#sakarya", "#yorumdantasarım"]}


def yildiz_sec(tur: str, sektor_anahtar: str) -> dict:
    """Günün perdahı/özelliği: son 7 bölümde kullanılanı seçme; sektöre uygun olana öncelik."""
    liste = json.loads((ICERIK / ("perdahlar.json" if tur == "kartvizit" else "site-ozellikleri.json")).read_text())
    son = [b.get("yildiz") for b in oku(f"{tur}-bolumler.json", [])[-7:]]
    adaylar = [x for x in liste if x["kod"] not in son] or liste
    uygun = [x for x in adaylar if sektor_anahtar in x.get("uygun", [])]
    return random.choice(uygun or adaylar)


def anlatim(tur: str, s: dict) -> list[tuple[str, str]]:
    return _metinler(tur, s)
