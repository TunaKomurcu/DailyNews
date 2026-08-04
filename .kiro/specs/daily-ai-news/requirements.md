# Requirements Document

## Introduction

Günlük olarak yapay zeka haberlerini RSS kaynaklarından toplayan, Google Gemini API ile kategorilere ayıran ve GitHub Pages'de statik bir HTML sayfası olarak yayınlayan otomasyon sistemi.

- **Hedef:** Her sabah güncel AI haberlerini otomatik topla, kategorile ve yayınla
- **Altyapı:** Tamamen ücretsiz — Python, GitHub Actions, GitHub Pages, Gemini API ücretsiz katman
- **Kullanıcı:** Türkçe arayüz, İngilizce içerik; ek kurulum veya hesap gerektirmez

## Requirements

### Fonksiyonel Gereksinimler

#### 1. Haber Toplama

- **FR-1.1**: Sistem aşağıdaki RSS kaynaklarından haber başlıklarını çekebilmeli:
  - arXiv AI kategorisi
  - OpenAI Blog
  - Anthropic Blog
  - Hacker News (AI ile ilgili)
  - TechCrunch AI
- **FR-1.2**: Sadece son 24 saat içinde yayınlanan haberleri filtrelemeli
- **FR-1.3**: Her haber için başlık, özet (varsa), yayın tarihi ve kaynak URL bilgilerini saklamalı
- **FR-1.4**: Aynı haberin tekrar eklenmemesi için benzersizlik kontrolü yapmalı

#### 2. Haber Kategorilendirme

- **FR-2.1**: Her haber başlığı LLM API kullanılarak otomatik kategorilere ayrılmalı
- **FR-2.2**: Desteklenen kategoriler:
  - Araştırma (Research)
  - Mühendislik/Mimari (Engineering/Architecture)
  - Ürün/Şirket Haberleri (Product/Company News)
  - Kullanıcıyı Etkileyen (User Impact)
  - Regülasyon/Politika (Regulation/Policy)
  - Yatırım/Startup (Investment/Startup)
  - Açık Kaynak (Open Source)
- **FR-2.3**: Her haber yalnızca bir kategoriye atanmalı
- **FR-2.4**: Kategorilendirme sırasında hata durumunda haber "Genel" kategorisine atanmalı

#### 3. Statik Sayfa Üretimi

- **FR-3.1**: Kategorilere göre gruplanmış HTML sayfası üretilmeli
- **FR-3.2**: Her haber için başlık (orijinal kaynağa link), kısa özet (varsa), yayın tarihi ve kaynak adı gösterilmeli
- **FR-3.3**: Sayfa responsive tasarıma sahip olmalı (mobil uyumlu)
- **FR-3.4**: Son güncellenme tarihi ve saati sayfada görünmeli
- **FR-3.5**: Kategoriler arasında kolay gezinme için navigasyon menüsü olmalı

#### 4. Otomatik Çalışma

- **FR-4.1**: GitHub Actions ile her gün sabah 04:00 UTC (07:00 Türkiye saati) otomatik çalışmalı
- **FR-4.2**: Manuel tetikleme seçeneği de bulunmalı
- **FR-4.3**: Başarılı çalıştıktan sonra otomatik olarak GitHub Pages'e deploy edilmeli
- **FR-4.4**: Hata durumunda log kaydı tutulmalı

### Teknik Gereksinimler

#### 5. Teknoloji Stack

- **TR-5.1**: Python 3.9+ kullanılmalı
- **TR-5.2**: RSS parsing için `feedparser` kütüphanesi kullanılmalı
- **TR-5.3**: LLM için Google Gemini API (`google-genai` SDK) kullanılmalı
- **TR-5.4**: Tarih işlemleri için `python-dateutil` kullanılmalı
- **TR-5.5**: HTTP istekleri için `requests` kütüphanesi kullanılmalı

#### 6. API ve Dış Servisler

- **TR-6.1**: Gemini API ücretsiz katman limitleri aşılmamalı (dakikada 15 istek, günde 1.000 istek)
- **TR-6.2**: API anahtarı GitHub Secrets üzerinden güvenli şekilde saklanmalı
- **TR-6.3**: API çağrıları rate-limiting'e uygun şekilde yapılmalı
- **TR-6.4**: API hataları graceful şekilde handle edilmeli

#### 7. Veri Yönetimi

- **TR-7.1**: Geçmiş haberler basit bir JSON dosyasında saklanmalı (son 7 gün)
- **TR-7.2**: Her çalıştırmada yeni haberler mevcut listeye eklenip eski haberler temizlenmeli
- **TR-7.3**: Veri dosyası GitHub repository'de tutulmalı

#### 8. Deployment

- **TR-8.1**: GitHub Pages üzerinden yayınlanmalı (ücretsiz)
- **TR-8.2**: Statik HTML/CSS/JS dosyaları `main` branch içindeki `docs/` klasöründe bulunmalı; GitHub Pages ayarlarında kaynak olarak `docs/` klasörü seçilmeli (ayrı `gh-pages` branch'ine gerek yok)
- **TR-8.3**: Python kodu, yapılandırma dosyaları ve `docs/` klasörü aynı `main` branch'de birlikte bulunmalı

### Performans Gereksinimleri

- **PR-1**: Toplam çalışma süresi 10 dakikayı geçmemeli (GitHub Actions limiti)
- **PR-2**: Günlük ortalama 50-100 haber işlenebilmeli
- **PR-3**: Üretilen HTML dosyası 500KB'ı geçmemeli (hızlı yükleme)

### Güvenlik Gereksinimleri

- **SR-1**: API anahtarları asla kod içinde bulunmamalı
- **SR-2**: RSS feed'lerden gelen içerik XSS'e karşı sanitize edilmeli
- **SR-3**: External link'ler `rel="noopener noreferrer"` attribute'larına sahip olmalı

### Bakım ve Genişletilebilirlik

- **MR-1**: Yeni RSS kaynağı eklemek kolay olmalı (yapılandırma dosyası)
- **MR-2**: Yeni kategori eklemek kolay olmalı
- **MR-3**: Kod düzgün dokümante edilmeli
- **MR-4**: GitHub Actions workflow başarısız çalışmaları bildirecek şekilde yapılandırılmalı

### Kapsam Dışı

- Kullanıcı authentication sistemi
- Yorum veya sosyal etkileşim özellikleri
- Email bildirim sistemi
- Backend database
- Analytics/tracking
- Multi-language desteği (ilk sürüm: Türkçe arayüz, İngilizce içerik)

## Glossary

| Terim | Açıklama |
|-------|----------|
| RSS | Really Simple Syndication — web içeriği yayınlamak için standart XML formatı |
| FetchedItem | RSS'ten çekilen ham haber verisi (sanitize veya kategorilenmemiş) |
| NewsItem | Sanitize edilmiş ve kategorilere ayrılmış nihai haber verisi |
| url_hash | Bir haberin URL'sinden üretilen SHA-256[:16] özeti — tekilleştirme anahtarı |
| history.json | Son 7 günlük haber geçmişini tutan JSON dosyası |
| Genel | Kategorilendirme başarısız olduğunda atanan varsayılan (fallback) kategori |
| batch | Gemini API'ye tek seferde gönderilen haber grubu (max 20 başlık) |
| GitHub Pages | GitHub üzerinde ücretsiz statik site barındırma servisi |
| docs/ | GitHub Pages'in kaynak olarak kullandığı klasör (main branch içinde) |
