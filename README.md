# Instagram Bot — Profesyonel Otomasyon Sistemi

**Sürüm:** 1.2.0 — Python 3.9+ — Instagram takip/begeni/yorum/DM/paylasim otomasyonu

Instagram hesabınız için geliştirilmiş, insan benzeri davranış motoruna sahip,
tek makinede birden fazla hesabı yönetebilen uçtan uca otomasyon sistemi.

---

## Özellikler

| Alan | Özellik |
|---|---|
| **Engajman** | Otomatik takip + beğeni + yorum (hashtag ve rakip hesap kaynaklı) |
| **Unfollow** | Belirli bekleme süresi sonrası geri takip etmeyenleri otomatik bırakma (geri takip edenler korunur) |
| **DM** | Rastgele mesaj havuzundan toplu / hedefli DM gönderimi |
| **Veri çekme** | Takipçi, takip edilen, kullanıcı, hashtag, post verileri (JSON/CSV) |
| **İçerik** | Fotoğraf, video, carousel ve story paylaşımı |
| **Çoklu hesap** | `accounts.yaml` ile tek kurulumda N hesap, hesap bazlı limitler |
| **Anti-tespit motoru** | Rastgele gecikmeler, ısınma eğrisi, saatlik üst sınır, aktivite pencereleri |
| **Hedefleme motoru** | Skorlama (biyografi anahtar kelimesi, takipçi dengesi, güncellik), filtreler |
| **Güvenlik** | Oturum kaydı (yeniden giriş yok), challenge/2FA yönetimi, hesap kısıt algılama ve otomatik soğuma (cooldown) |
| **Zamanlayıcı** | Saatlik veya belirli gün/saatlerde otomatik görev çalıştırma (daemon) |
| **Web paneli** | Tarayıcıdan canlı istatistik ve yönetim arayüzü |
| **Raporlama** | Günlük istatistik ve rapor üretimi |
| **Kuru çalışma** | `--dry-run` ile gerçek aksiyon yapmadan simülasyon |

---

## Sistem Gereksinimleri

- macOS 12+ veya Linux (Ubuntu 20.04+ önerilir)
- Python 3.9 – 3.12
- Minimum 2 GB RAM, 2 GB boş disk

---

## Kurulum (Tek Komut)

```bash
./install.sh
```

Kurulum; sanal ortam oluşturur, bağımlılıkları yükler ve `.env` dosyasını hazırlar.

### Manuel Kurulum

```bash
cd instagram-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

---

## Yapılandırma

### 1. Hesap bilgileri — `.env`

```ini
IG_PASSWORD=hesap_sifresi
```

Birden fazla hesap için `accounts.yaml`'daki `password_env` adına göre
`IG_PW_HESAP1`, `IG_PW_HESAP2` gibi değişkenler tanımlayın.

> Sifreler asla `config.yaml` veya `accounts.yaml` içine yazılmaz. Kod içine
> gömülü değildir; yalnızca ortam değişkeninden okunur.

### 2. Hesaplar — `accounts.yaml`

```yaml
accounts:
  - name: "hesap1"
    username: "kullanici_adi"
    password_env: "IG_PW_HESAP1"
    proxy: ""                          # opsiyonel: http:// veya socks5://
    enabled: true
    windows: { }                       # ornek: {hours: [18,19,20,21,22]}
    overrides: { }                     # ornek: {limits: {follows: 30, likes: 80}}
```

- `windows`: boşsa her zaman aktiftir; doluysa yalnızca belirtilen saatlerde çalışır.
- `overrides`: küresel ayarları yalnızca bu hesap için ezebilir.

### 3. Davranış ayarları — `config.yaml`

- `limits`: günlük bütçeler (takip 60, beğeni 150, yorum 20, DM 20, paylaşım 4 varsayılan).
- `delays`: aksiyonlar arası bekleme aralıkları, ısınma çarpanı, hata sonrası bekleme.
- `targeting`: kaynaklar (hashtag/rakip), filtreler (takipçi aralığı, biyografi anahtar kelimeleri), skorlama ağırlıkları.
- `comments` / `dm`: `{username}` değişkenli mesaj havuzları.

Başlangıçta tüm ayarlar geçerlilik kontrolünden geçer; hatalı değerler anında
açıklayıcı bir hata mesajıyla raporlanır.

---

## Komut Referansı

```bash
# Giriş yap, oturumu kaydet (hesap başına tek seferlik)
igbot login                      # tum aktif hesaplar
igbot login hesap1               # tek hesap
igbot login hesap1 --force       # oturumu yenile

# Durum ve istatistik
igbot status

# Engajman (takip + begeni + yorum)
igbot engage hesap1 --budget 20
igbot engage hesap1 --hashtags python coding --competitors rakib_hesap --comment
igbot engage hesap1 --dry-run    # gercek aksiyon yapmaz, simule eder
igbot engage hesap1 --once       # tek hedef isler (test icin)

# Unfollow (geri takip etmeyenleri birak)
igbot unfollow hesap1                          # config.yaml'daki unfollow ayarlariyla
igbot unfollow hesap1 --budget 30 --grace-days 5
igbot unfollow hesap1 --include-followers      # bizi takip edenleri de birak
igbot unfollow hesap1 --dry-run                # simule et

# DM
igbot dm hesap1 --usernames kullanici1 kullanici2
igbot dm hesap1 --list kullanicilar.txt --budget 15

# Veri cekme
igbot scrape hesap1 --type followers --target kullanici --amount 200 --out data/followerler.csv
igbot scrape hesap1 --type hashtag --target python --amount 50
igbot scrape hesap1 --type user --target kullanici

# Icerik paylasimi
igbot post hesap1 --media foto.jpg --caption "Aciklama #hashtag"
igbot post hesap1 --media a.jpg b.jpg --caption "Carousel"
igbot post hesap1 --media video.mp4 --story

# Hedef havuzu yonetimi
igbot targets list --account hesap1 --status pending
igbot targets clear --status processed
igbot targets blacklist hesap1 --pk 123456

# Zamanlayici gorevleri
igbot tasks list
igbot tasks add --name "sabah" --account hesap1 --action engage '{"at":["09:00"]}'
igbot tasks rm --id 3
igbot tasks toggle --id 3
igbot run --once        # vadesi gelen gorevleri bir kez calistir
igbot run               # zamanlayiciyi arka planda calistir (daemon)

# Web paneli
igbot dashboard --host 127.0.0.1 --port 8787

# Gunluk rapor
igbot report --out data/rapor.md

# Surum
igbot --version
```

`igbot` komutunun yerine `python bot.py` de kullanılabilir.

---

## Web Paneli

`igbot dashboard` komutuyla başlatılır; varsayılan adres `http://127.0.0.1:8787`.
Tarayıcıdan hesap durumu, günlük istatistikler, hedef havuzu ve son işlemler
izlenebilir. Yalnızca yerel makinede dinler (`127.0.0.1`); uzaktan erişim
gerekiyorsa ters proxy (Nginx + TLS) veya SSH tüneli kullanılmalıdır.

Panelden hesap başına engajman, **unfollow** ve DM işleri başlatılabilir;
görevler ve hedef havuzu yönetilebilir.

Değişiklik yapan uçlar (login, engage, unfollow, dm, hedef temizleme/kara liste,
görev ekle/sil) için token koruması vardır: `config.yaml` içindeki
`system.dashboard_token` veya `IG_DASHBOARD_TOKEN` ortam değişkeni tanımlanırsa
bu istekler `X-Auth-Token` başlığı ister. Token boşsa panel korumasızdır ve
yalnızca `127.0.0.1` üzerinden kullanılmalıdır. Token tanımlıysa panelde
sağ üstteki 🔑 düğmesiyle token girilir; tarayıcıda `localStorage`'da saklanır
ve her isteğe otomatik eklenir (401 alınırsa panel token'ı sorar).

---

## Zamanlayıcı

`config.yaml` içindeki `tasks` bölümü, `igbot tasks` komutlarıyla veya
`igbot run` daemon'u ile yönetilir. Örnek görev:

```yaml
tasks:
  - name: "sabah_engajman"
    account: "hesap1"
    action: "engage"
    params: { budget: 15, like: true, comment: true }
    schedule: { at: ["09:00", "21:00"], days: [1, 2, 3, 4, 5] }
    enabled: true
```

---

## Dağıtım (Docker / systemd)

### Docker Compose

```bash
cp .env.example .env          # sifreleri doldurun
docker compose build
docker compose up -d bot      # zamanlayici daemon
docker compose up -d dashboard  # web paneli (127.0.0.1:8787)
```

`data/` dizini kalıcı hacim olarak bağlanır (SQLite, oturumlar, loglar).
Paneli uzaktan açacaksanız `system.dashboard_token` tanımlayın ve TLS'li bir
ters proxy arkasına alın.

### systemd

`deploy/igbot.service` örnek birim dosyasını `/etc/systemd/system/` altına
kopyalayıp yollarını düzenleyin:

```bash
sudo cp deploy/igbot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now igbot
journalctl -u igbot -f
```

### Proxy güvenliği

`accounts.yaml` içinde `proxy` tanımlıysa, sistem bağlanmadan önce proxy'yi
doğrular ve çıkış IP'sini loglar (`system.proxy_check`). Proxy doğrulanamazsa
gerçek IP sızmaması için **bağlantı durdurulur** (`system.proxy_required: true`,
varsayılan). Uyarı verip proxysuz devam için `proxy_required: false` yapın.

### Anti-tespit ayarları

- `warmup`: yeni hesaplarda günlük limitleri kademeli açar (hesap yaşına göre).
- `humanize`: takipten önce olasılıkla profil görüntüler (insansı gezinme).
- `system.locale/country/timezone_offset`: bölge tutarlılığı (proxy ile uyumlu).

### Bildirimler

`config.yaml` `notifications` ile challenge/kısıt/hata olaylarında Telegram,
Discord veya webhook uyarısı alın (anahtarlar ortam değişkeninden de okunabilir).

---

## Güvenlik ve Sorumluluk

**Bu sistemle çalışmak Instagram kullanım koşullarına aykırı kabul edilebilir
ve hesap kilitlenmesi / kalıcı yasaklama riski taşır.** Satıcı bu riskten
sorumlu değildir. Riskleri en aza indirmek için:

- Günlük limitleri asla varsayılan değerlerin üzerine çıkarmayın
  (takip 60, beğeni 150, yorum 20, DM 20).
- `delays.min` değerini düşürmeyin; 30–120 sn aralığı sağlıklıdır.
- Yeni hesaplarda düşük limitlerle test edin, hesabı "ısındırarak" artırın.
- Uzun süre aynı içerikle binlerce benzer yorum/DM göndermeyin.
- 2FA açık hesaplarda ilk girişte kod terminalden sorulur; giriş oturumu
  kaydedilir, tekrar sorulmaz.
- Proxy desteği mevcuttur: `accounts.yaml` içinde `proxy` alanını doldurun.

---

## Mimari

```
bot.py                  # CLI giris noktasi (igbot)
config.yaml             # kuresel ayarlar
accounts.yaml           # hesap tanimlari (sifreler .env'den okunur)
insta_bot/
  config.py             # yapilandirma + dogrulama + cevresel degiskenler
  db.py                 # SQLite deposu: hedefler, limitler, islem gecmisi, gorevler
  session.py            # giris, oturum kaydi, challenge/2FA yonetimi
  security.py           # gecikme motoru, limit motoru, cooldown, aktivite penceresi
  targeting.py          # hedef toplama, filtreleme, skorlama
  engagement.py         # Runner: engajman ve DM is akisi
  scraper.py            # veri cekme (JSON/CSV)
  poster.py             # icerik paylasimi
  scheduler.py          # gorev zamanlayici
  metrics.py            # gunluk istatistik ve raporlar
  api.py                # web paneli REST arayuzu
  web/                  # panel arayuzu (HTML/JS/CSS)
  factory.py            # hesap baglanti fabrikasi
data/                   # SQLite veritabani, oturumlar, loglar, ciktilar
tests/                  # birim testleri (engajman, unfollow, guvenlik, api, db, ...)
```

---

## Geliştirici Notları

```bash
source .venv/bin/activate
pip install -e ".[dev]"       # pytest, httpx, ruff
ruff check .                  # lint (kod kalitesi)
python -m pytest              # birim testleri — hepsi gecmeli
```

Her sürüm yayınlanmadan önce hem `ruff check .` hem de test suite'i yeşil
olmalıdır. Her push ve PR'da GitHub Actions (`.github/workflows/ci.yml`)
Python 3.9/3.11/3.12 üzerinde lint + testleri otomatik çalıştırır.

---

## Sürüm Geçmişi

Değişiklikler için [CHANGELOG.md](CHANGELOG.md) dosyasına bakın.

---

## Lisans

Bu yazılım **özel lisanstır**; kopyalama, dağıtma, değiştirme ve yeniden satış
yapılmaz. Detaylar için [LICENSE](LICENSE) dosyasını inceleyin.
