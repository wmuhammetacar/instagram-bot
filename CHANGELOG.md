# Değişiklik Günlüğü

Bu proje [Semantic Versioning](https://semver.org/lang/tr/) kurallarını takip eder.

## [1.2.0] — 2026-08-09

### Eklendi

- **Anti-tespit — kademeli ısınma (warmup):** hesap yaşına göre günlük limitler
  `start_fraction`'dan tam limite kademeli açılır (`config.yaml` `warmup`).
- **Anti-tespit — insansı gezinme (humanize):** takipten önce belirli olasılıkla
  profil görüntülenir (`user_info` + kısa bekleme) (`config.yaml` `humanize`).
- **Anti-tespit — bölge tutarlılığı:** oturuma locale/country/timezone_offset
  uygulanır (proxy bölgesiyle uyumlu olmalı; `system` veya hesap bazında).
- **Bildirim sistemi:** challenge, kısıt (restriction) ve hata olaylarında
  Telegram / Discord / genel webhook uyarısı (`config.yaml` `notifications`;
  anahtarlar ortam değişkeninden de okunabilir). Bağlantı hataları yutulur,
  ana akışı asla durdurmaz.
- **Dönüşüm analitiği:** kaynak bazlı takip → geri-takip oranı. Takip aksiyonu
  hedef kaynağını meta'ya yazar; unfollow akışı geri takip edeni `followback`
  olarak kaydeder. `igbot analyze <hesap> [--since]`, `/api/analytics` ucu.
- **Panel:** raporda saatlik dağılım SVG grafiği (hesap + metrik seçici) ve
  kaynak dönüşüm tablosu.
- **Dağıtım:** `Dockerfile`, `docker-compose.yml` (bot + dashboard servisleri),
  `deploy/igbot.service` systemd birimi, `.dockerignore`.
- **Proxy sağlık kontrolü:** bağlanmadan önce proxy doğrulanır ve çıkış IP'si
  loglanır; doğrulanamazsa (varsayılan) bağlantı durur (`system.proxy_check`,
  `system.proxy_required`).
- **CI:** pytest-cov ile kapsam raporu.

### Düzeltmeler

- `merged_account` tabanına `unfollow` eklendi: `config.yaml` `unfollow` ayarları
  önceden yok sayılıp yalnızca varsayılanlar kullanılıyordu.
- `Repo.set_state` / `Repo.update_task` boş alanla çağrıldığında geçersiz SQL
  (`SET  WHERE`) üretiyordu; artık no-op.
- `bot.py` çıkışta veritabanı bağlantısını `atexit` ile kapatır.

## [1.1.0] — 2026-08-07

### Eklendi

- **Unfollow motoru:** geçmişte takip edilip belirli bekleme süresi (`grace_days`)
  sonrasında geri takip etmeyenleri otomatik bırakma. `keep_followers` ile geri
  takip edenler korunur. `igbot unfollow` komutu, `config.yaml` `unfollow` bölümü,
  zamanlayıcı `unfollow` aksiyonu ve günlük/saatlik `unfollows` limiti.
- Web paneli değişiklik yapan uçlarına `X-Auth-Token` koruması
  (`system.dashboard_token` / `IG_DASHBOARD_TOKEN`).
- Aktivite pencereleri için saat dilimi (timezone) desteği.
- Hedefleme: `skip_mutual` filtresi (bizi zaten takip edenleri atla).
- Web paneli: unfollow işi başlatma (buton + modal), `unfollow` görev tipi,
  günlük unfollow metresi ve raporda "Bırakma" satırı.
- Web paneli: 🔑 token düğmesi — token `localStorage`'da saklanır, her isteğe
  `X-Auth-Token` olarak eklenir, 401'de otomatik sorulur (token korumalı panel
  artık arayüzden de kullanılabilir).

### Düzeltmeler

- Rapor/durum aksiyon sayaçları her zaman 0 gösteriyordu: `actions` tablosu tekil
  aksiyon adı (`follow`) yazarken rapor çoğul anahtar (`follows`) beklediğinden
  eşleşme olmuyordu. Eşleme eklendi.
- Panel saatlik grafiği (`/api/hourly`, `hourly_series`) aynı tekil/çoğul
  uyuşmazlığı yüzünden hep 0 dönüyordu; `action_type` tekile normalize ediliyor.
- `scrape --type user --out *.csv`: tek sözlük sonucu CSV yazarken `data[0]`
  ile çöküyordu; sözlük artık listeye sarılıyor.

- `session.call` retry döngüsü: `except ... as exc` sonrası silinen `exc`e
  erişildiği için geçici/ağ hatalarında retry çalışmıyor, `UnboundLocalError`
  fırlıyordu. Giderildi.
- `db.hourly_actions`: olmayan `hour` sütununa başvurduğu için panel saatlik
  grafiği çöküyordu; saat `created_at`ten türetiliyor.
- Panel token karşılaştırması sabit zamanlı (`secrets.compare_digest`).
- `.env` ayrıştırma: değerdeki çevreleyen tırnaklar ve `export` öneki artık
  doğru işleniyor.
- Zamanlayıcı: aynı güne ait en erken vakit seçiliyor; görev kilidi iş bitene
  kadar tutuluyor.
- Engajman: beğeni + yorum aynı gönderiyi kullanır, medya hedef başına tek çekilir.

## [1.0.0] — 2026-08-06

İlk ticari sürüm. Bu sürümde sistemi satılabilir ürün seviyesine taşıyan
tüm altyapı tamamlanmıştır.

### Eklendi

- Çoklu hesap yönetimi (`accounts.yaml`, hesap bazlı `overrides`, proxy desteği)
- Engajman motoru: takip, beğeni, yorum (hashtag + rakip hesap kaynaklı hedefleme)
- Hedefleme motoru: biyografi anahtar kelimesi, takipçi dengesi ve güncellik skorlaması
- Anti-tespit motoru: ısınma eğrisi, aksiyon tipine özel gecikmeler, saatlik üst sınır,
  aktivite pencereleri, hata sonrası yavaşlatma
- Güvenlik: oturum kaydı, challenge/2FA yönetimi, kısıt (restriction) algılama ve
  otomatik soğuma, kara liste
- Zamanlayıcı daemon: saatlik / belirli gün-saat görevleri, `tasks` CLI yönetimi
- Web kontrol paneli (FastAPI + statik arayüz, 127.0.0.1:8787)
- Günlük rapor üretimi, durum ekranı, kuru çalışma (dry-run) modu
- SQLite deposu: hedef havuzu, işlem geçmişi, günlük/saatlik limit kayıtları
- Veri çekme: takipçi, takip edilen, kullanıcı, hashtag, post (JSON/CSV)
- İçerik paylaşımı: fotoğraf, video, carousel, story
- Paketleme: `pyproject.toml`, `igbot` CLI giriş noktası, `--version`
- Yapılandırma doğrulama motoru: hatalı ayarlar anında açıklayıcı hata mesajıyla reddedilir
- Tek komut kurulum: `install.sh`
- 40 birim testi (engajman, güvenlik, hedefleme, veritabanı, zamanlayıcı)

### Düzeltmeler

- `Runner._perform` çağrılarında keyword-only parametre hatası (TypeError) giderildi
- Başarısız aksiyonlarda aynı hedefin sonsuz tekrar denenmesi giderildi
- Günlük yorum limiti kontrolü eklendi (önceden yorum bütçesi işlemiyordu)
- Hata sonrası bekleme tabanı gürültü eklemesinden sonra uygulanıyor (asla alt sınıra düşmez)
- Eski mimariden kalan `actions.py` kalıntıları temizlendi
