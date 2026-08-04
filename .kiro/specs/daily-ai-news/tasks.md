# Implementation Plan:

## Overview

Proje 10 görev halinde uygulanır. Görev 1-2 altyapı ve yapılandırma; Görev 3-8 modül implementasyonları; Görev 9 deployment otomasyonu; Görev 10 uçtan uca yerel testtir.

## Task Dependency Graph

Görev 1 → Görev 2 → Görev 3, 4, 5, 6, 7 (paralel) → Görev 8 → Görev 9 → Görev 10

```json
{
  "waves": [
    {
      "wave": 1,
      "tasks": ["Görev 1"],
      "description": "Proje iskeleti ve bağımlılıklar"
    },
    {
      "wave": 2,
      "tasks": ["Görev 2"],
      "description": "RSS kaynak yapılandırması"
    },
    {
      "wave": 3,
      "tasks": ["Görev 3", "Görev 4", "Görev 5", "Görev 6", "Görev 7"],
      "description": "Modül implementasyonları (paralel)"
    },
    {
      "wave": 4,
      "tasks": ["Görev 8"],
      "description": "Ana script entegrasyonu"
    },
    {
      "wave": 5,
      "tasks": ["Görev 9"],
      "description": "GitHub Actions workflow"
    },
    {
      "wave": 6,
      "tasks": ["Görev 10"],
      "description": "Uçtan uca yerel test"
    }
  ]
}
```

## Tasks

### Görev 1: Proje İskeleti ve Bağımlılıklar

- [ ] 1. Klasör yapısını oluştur: src/, data/, docs/, templates/, .github/workflows/
- [ ] 2. requirements.txt dosyasını oluştur (pinned versiyonlar)
- [ ] 3. src/__init__.py dosyasını oluştur
- [ ] 4. Boş placeholder dosyalarını oluştur: data/history.json, docs/index.html
- [ ] 5. README.md dosyasını oluştur (kurulum ve çalıştırma talimatları)

### Görev 2: RSS Kaynak Listesi

- [ ] 1. config.yml dosyasını oluştur: tüm RSS kaynakları, kategori listesi, ayarlar
- [ ] 2. Kaynak ekleme/çıkarmanın sadece config.yml değişikliğiyle yapılabildiğini doğrula

### Görev 3: RSS Toplama Modülü

- [ ] 1. src/fetcher.py dosyasını oluştur, FetchedItem dataclass tanımla
- [ ] 2. feedparser ile RSS parse et, son 24 saat filtresi uygula
- [ ] 3. Timezone-aware UTC normalizasyonu yap
- [ ] 4. Başlık/URL eksikse atla; kaynak hata verirse log yaz ve devam et
- [ ] 5. url_hash = sha256(url)[:16] üret

### Görev 4: Tekilleştirme Modülü

- [ ] 1. src/deduplicator.py dosyasını oluştur, history.json yükle/kaydet fonksiyonları
- [ ] 2. Gelen haberleri mevcut hash setine karşı filtrele
- [ ] 3. update_history() fonksiyonunu yaz: yeni haberleri ekle, 7 günden eski kayıtları temizle
- [ ] 4. history.json yoksa boş geçmişle başlat

### Görev 5: Sanitizasyon Modülü

- [ ] 1. src/sanitizer.py dosyasını oluştur, html.escape() ile başlık ve özet temizleme
- [ ] 2. Özeti summary_max_chars (300) karaktere kırp
- [ ] 3. URL scheme doğrulaması yap (sadece http/https; geçersizse #)
- [ ] 4. FetchedItem -> NewsItem dönüşümünü gerçekleştir

### Görev 6: LLM Kategorileştirme Modülü

- [ ] 1. src/categorizer.py dosyasını oluştur, google-genai SDK ile gemini-2.5-flash bağlantısı
- [ ] 2. 20'lik batch prompt oluştur ve API'ye gönder
- [ ] 3. Satır sayısı doğrulaması ekle: eşleşmezse tüm batch Genel kategorisine düşür ve WARNING log yaz
- [ ] 4. Exponential backoff uygula: 429/geçici hata için 1s, 2s, 4s bekleme, max 3 retry
- [ ] 5. Geçersiz kategori adını Genel'e düşür
- [ ] 6. GEMINI_API_KEY ortam değişkeni yoksa açıklayıcı hatayla dur

### Görev 7: HTML Üretim Modülü

- [ ] 1. templates/index.html.j2 oluştur: responsive inline CSS, nav menüsü, kategori bölümleri
- [ ] 2. Tüm dış linklere target="_blank" rel="noopener noreferrer" ekle
- [ ] 3. src/renderer.py oluştur: Jinja2 autoescape=False, kategoriye göre gruplama
- [ ] 4. Türkçe tarih formatı (date_label) uygula
- [ ] 5. 500KB boyut kontrolü ekle: önce özet kırp, hala büyükse özet kaldır
- [ ] 6. Çıktıyı docs/index.html olarak yaz

### Görev 8: Ana Script

- [ ] 1. src/main.py oluştur: tüm modülleri sırayla çağıran main() fonksiyonu
- [ ] 2. Her adımda log mesajı ekle (çekilen/yeni/kategorilenen haber sayıları)
- [ ] 3. python -m src.main ile çalışabilir hale getir

### Görev 9: GitHub Actions Workflow

- [ ] 1. .github/workflows/daily_news.yml oluştur: cron 0 4 * * * (07:00 Türkiye saati)
- [ ] 2. GEMINI_API_KEY secret'ını ortam değişkenine aktar
- [ ] 3. docs/index.html ve data/history.json değişikliklerini commit et ve push et
- [ ] 4. Değişiklik yoksa commit atlamayı sağla
- [ ] 5. workflow_dispatch ile manuel tetikleme desteği ekle

### Görev 10: Yerelde Test

- [ ] 1. GEMINI_API_KEY ortam değişkenini set et
- [ ] 2. pip install -r requirements.txt ile bağımlılıkları kur
- [ ] 3. python -m src.main ile uçtan uca çalıştır
- [ ] 4. docs/index.html dosyasının tarayıcıda doğru render ettiğini doğrula
- [ ] 5. data/history.json içeriğinin beklendiği gibi güncellendiğini kontrol et

## Notes

- Görev 1-9 tamamlanmıştır; tüm modüller yazılmış ve birim testleri geçmiştir.
- Görev 10 gerçek GEMINI_API_KEY gerektirmektedir.
- GitHub Pages kurulumu: Settings > Pages > Source: main branch, /docs klasörü.
- Gemini API anahtarı Google AI Studio üzerinden ücretsiz alınabilir: https://aistudio.google.com/apikey
