# Değişiklik Günlüğü

Bu proje [Semantic Versioning](https://semver.org/lang/tr/) kurallarını takip eder.

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
