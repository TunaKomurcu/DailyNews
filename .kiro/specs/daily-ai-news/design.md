## Overview

Günlük AI haber toplayıcı; RSS kaynaklarından son 24 saatin haberlerini çeken, Google Gemini API ile 7 kategoriye ayıran ve GitHub Pages'de statik bir HTML sayfası olarak yayınlayan otomasyon sistemidir. Tüm altyapı ücretsizdir: Python + GitHub Actions + GitHub Pages.

Veri akışı:

```
RSS → fetcher → deduplicator → sanitizer → categorizer → history.json
                                                                  ↓
                                                            renderer → docs/index.html
```

Her gün 04:00 UTC (07:00 Türkiye saati) GitHub Actions otomatik çalışır. Üretilen `docs/index.html` aynı `main` branch'e commit edilir; GitHub Pages `docs/` klasörünü kaynak olarak kullanır.

---

## Architecture

### Proje Klasör Yapısı

```
DailyNews/
├── .github/
│   └── workflows/
│       └── daily_news.yml          # GitHub Actions workflow
├── src/
│   ├── __init__.py
│   ├── main.py                     # Giriş noktası, tüm adımları orkestre eder
│   ├── fetcher.py                  # RSS kaynaklarından haber çeker
│   ├── categorizer.py              # Gemini API ile kategorilendirme
│   ├── deduplicator.py             # Tekil haber kontrolü
│   ├── renderer.py                 # Jinja2 ile HTML üretimi
│   └── sanitizer.py                # XSS temizleme yardımcısı
├── templates/
│   └── index.html.j2               # Ana Jinja2 template
├── data/
│   └── history.json                # Son 7 günlük haber geçmişi
├── docs/
│   └── index.html                  # Üretilen statik sayfa (GitHub Pages)
├── config.yml                      # RSS kaynakları ve kategori tanımları
├── requirements.txt                # Python bağımlılıkları
└── README.md
```

### GitHub Actions Workflow (`.github/workflows/daily_news.yml`)

```yaml
name: Daily AI News

on:
  schedule:
    - cron: '0 4 * * *'    # 04:00 UTC = 07:00 Turkey time (UTC+3)
  workflow_dispatch:         # Manuel tetikleme

jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      contents: write        # docs/ klasörünü commit etmek için

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'

      - name: Bağımlılıkları kur
        run: pip install -r requirements.txt

      - name: Haberleri çek ve sayfayı oluştur
        env:
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
        run: python -m src.main

      - name: Değişiklikleri commit et
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add docs/index.html data/history.json
          git diff --staged --quiet || git commit -m "chore: günlük haber güncellemesi $(date -u +%Y-%m-%d)"
          git push
```

**Notlar:**
- `git diff --staged --quiet ||` komutu: değişiklik yoksa commit atlamak için
- Tek job, tek branch — ayrı deploy adımına gerek yok

### Zamanlama ve Performans Bütçesi

| Adım | Tahmini Süre |
|------|-------------|
| RSS fetch (5 kaynak, sıralı) | ~30 sn |
| Tekilleştirme | < 1 sn |
| Sanitizasyon | < 1 sn |
| Gemini API (5 batch × ~3 sn) | ~15-45 sn |
| Geçmiş güncelleme | < 1 sn |
| HTML render | < 2 sn |
| **Toplam** | **< 90 sn** |

GitHub Actions limiti 10 dakika (600 sn) — büyük bütçe var.

### Bağımlılıklar (`requirements.txt`)

```
feedparser==6.0.11
google-genai==2.16.0
Jinja2==3.1.4
python-dateutil==2.9.0
requests==2.32.3
PyYAML==6.0.2
```

Tüm versiyonlar sabitlenmiştir (floating range yok).

---

## Components and Interfaces

### `main.py` — Orkestratör

Tüm adımları sırayla çalıştırır. `python -m src.main` ile çağrılır.

```python
def main():
    config = load_config("config.yml")
    fetched = fetch_all(config["sources"])           # fetcher.py
    new_items = deduplicate(fetched, history_path)   # deduplicator.py
    clean_items = sanitize_all(new_items)            # sanitizer.py
    categorized = categorize(clean_items, config)    # categorizer.py
    update_history(categorized, history_path)        # deduplicator.py
    all_items = load_all_items(history_path)         # deduplicator.py
    render(all_items, config)                        # renderer.py
```

### `fetcher.py` — RSS Haber Çekici

Her RSS kaynağından son 24 saatin haberlerini çeker.

1. `config.yml`'den etkin kaynakları yükle
2. Her kaynak için `requests.get(url, timeout=15)` + `feedparser.parse()`
3. `published_parsed` / `updated_parsed` → timezone-aware UTC datetime
4. `now_utc - 24h` filtresi; başlık/URL eksikse atla
5. `url_hash = sha256(url)[:16]` üret
6. Hata durumunda log yaz, diğer kaynaklara devam et

### `deduplicator.py` — Tekilleştirici ve Geçmiş Yöneticisi

- `deduplicate()`: gelen `FetchedItem` listesini `history.json`'daki hash setine karşı filtreler; aynı çalıştırmada çapraz kaynak duplicate'leri de temizler
- `update_history()`: yeni haberleri ekler, `history_days`'den eski kayıtları siler
- `load_all_items()`: renderer için son 7 günlük tüm haberleri döndürür

### `sanitizer.py` — XSS Temizleyici

`FetchedItem → NewsItem` dönüşümünü yapar:

- `html.escape()` ile başlık, özet ve kaynak adı temizlenir
- Özet `summary_max_chars` (300) karaktere kırpılır
- URL'ler `urllib.parse` ile doğrulanır; sadece `http`/`https` geçer, geçersizse `#`

### `categorizer.py` — Gemini Kategori Atayıcı

Model: `gemini-2.5-flash` (ücretsiz: 15 RPM, 1000/gün)

- 20'lik batch'ler halinde numaralı prompt gönderilir
- Yanıt satır sayısı gönderilen başlık sayısıyla tam eşleşmezse tüm batch `"Genel"` atanır
- Geçersiz kategori adı → `"Genel"` fallback

```python
from google import genai
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=prompt,
)
```

### `renderer.py` — HTML Üretici

`NewsItem` listesinden `docs/index.html` üretir.

- Jinja2 `Environment(autoescape=False)` — `sanitizer.py` zaten `html.escape()` uyguladı; çift-escape (`&amp;amp;`) önlenir
- Kategorilere göre gruplama, Türkçe tarih formatı, sticky nav menüsü
- 500KB boyut kontrolü: önce özetleri 150 karaktere kırp, hâlâ büyükse tamamen kaldır

### `config.yml` — Yapılandırma

Yeni kaynak veya kategori eklemek için tek dokunuş noktası:

```yaml
sources:
  - name: "arXiv AI"
    url: "https://rss.arxiv.org/rss/cs.AI"
    enabled: true
  - name: "OpenAI Blog"
    url: "https://openai.com/blog/rss.xml"
    enabled: true
  - name: "Anthropic Blog"
    url: "https://www.anthropic.com/rss.xml"
    enabled: true
  - name: "Hacker News AI"
    url: "https://hnrss.org/newest?q=AI+LLM+machine+learning&points=20"
    enabled: true
  - name: "TechCrunch AI"
    url: "https://techcrunch.com/category/artificial-intelligence/feed/"
    enabled: true

categories:
  - "Araştırma"
  - "Mühendislik/Mimari"
  - "Ürün/Şirket Haberleri"
  - "Kullanıcıyı Etkileyen"
  - "Regülasyon/Politika"
  - "Yatırım/Startup"
  - "Açık Kaynak"
  - "Genel"  # fallback

history_days: 7
summary_max_chars: 300
output_max_kb: 500
```

### Jinja2 Template (`templates/index.html.j2`)

- Responsive inline CSS (harici dosya yok), max-width 900px
- Sticky nav menüsü — her kategoriye anchor link
- Tüm dış linkler `target="_blank" rel="noopener noreferrer"`
- Özel Jinja2 filtreleri: `format_date` (Türkçe), `slugify` (HTML id), `category_icon` (emoji)

---

## Data Models

### FetchedItem — Ham Haber

RSS'ten çekilen hammadde, henüz sanitize veya kategorilenmemiş:

```python
@dataclass
class FetchedItem:
    title: str          # Haber başlığı
    url: str            # Orijinal kaynak URL'i
    summary: str        # Özet metin (feedparser'dan, yoksa "")
    published: datetime # Yayın tarihi (timezone-aware UTC)
    source_name: str    # Kaynak adı (ör. "TechCrunch AI")
    url_hash: str       # SHA-256(url)[:16] — tekilleştirme anahtarı
```

### NewsItem — Kategorilere Ayrılmış Haber

Sanitize ve kategorilendirme sonrası nihai veri:

```python
@dataclass
class NewsItem:
    title: str          # html.escape() uygulanmış başlık
    url: str            # Doğrulanmış URL (geçersizse "#")
    summary: str        # html.escape() uygulanmış, max 300 karakter
    published: datetime # Timezone-aware UTC
    source_name: str    # html.escape() uygulanmış kaynak adı
    url_hash: str       # Değişmez — fetcher'dan geliyor
    category: str       # Kategori adı (başlangıçta "Genel")
```

### history.json — Geçmiş Kaydı

Son 7 günlük haberleri depolar; tekilleştirme ve HTML üretiminde kullanılır:

```json
{
  "last_updated": "2026-08-04T07:05:00Z",
  "items": [
    {
      "url_hash": "a1b2c3d4e5f6g7h8",
      "title": "...",
      "url": "...",
      "summary": "...",
      "published": "2026-08-04T06:00:00Z",
      "source_name": "...",
      "category": "Araştırma"
    }
  ]
}
```

---

## Error Handling

| Durum | Davranış |
|-------|----------|
| RSS kaynağı timeout (15s) | Log yaz, diğer kaynaklara devam et |
| RSS parse hatası (bozo feed) | Log yaz, o kaynağı atla |
| Eksik başlık veya URL | O entry'yi sessizce atla |
| Tarih bilgisi yok | Şimdiki zamanı kullan, devam et |
| `history.json` bozuk/eksik | Boş geçmişle başlat |
| Gemini 429 / 503 | Exponential backoff: 1s → 2s → 4s, max 3 retry |
| Gemini yanıt satır sayısı uyuşmazlığı | Tüm batch `"Genel"` atanır, WARNING log |
| Gemini bilinmeyen kategori | O haber `"Genel"` atanır |
| `GEMINI_API_KEY` eksik | `RuntimeError` ile program durur |
| HTML 500KB limitini aşıyor | Önce özetleri 150 karaktere kırp; hâlâ aşıyorsa tamamen kaldır |
| Geçersiz URL scheme | URL `"#"` ile değiştirilir |

---

## Correctness Properties

### Property 1: Tekillik

**Validates: Requirements 1.4**

Aynı URL, aynı çalıştırmada birden fazla kaynaktan gelse de yalnızca bir kez eklenir (`url_hash` kontrolü).

### Property 2: XSS Güvenliği

**Validates: Requirements 2**

`sanitizer.py`'deki `html.escape()` tüm kullanıcı taraflı içeriği kapsar; `autoescape=False` sadece çift-escape'i önler, XSS korumasını kaldırmaz.

### Property 3: Kategori Geçerliliği

**Validates: Requirements 2.3, 2.4**

Gemini'den dönen her değer geçerli kategoriler listesine karşı doğrulanır; bilinmeyen değer asla HTML'e yazılmaz.

### Property 4: Boyut Garantisi

**Validates: Requirements 3**

Render sonrası UTF-8 byte sayısı her zaman `output_max_kb * 1024`'ün altında kalır (iki aşamalı fallback).

### Property 5: Veri Tutarlılığı

**Validates: Requirements 7.1, 7.2**

`history.json` her çalıştırmada atomik olarak yazılır; kesintide bozuk state oluşmaz (Python `json.dump` tek geçişte yazar).

### Property 6: Zaman Filtresi

**Validates: Requirements 1.2**

`now_utc - 24h` kontrolü timezone-aware UTC üzerinde yapılır; DST kayması yaşanmaz.

---

## Testing Strategy

Otomatik test altyapısı kurulmamıştır; doğrulama aşağıdaki şekilde yapılır:

### Birim Düzey (manuel çalıştırma)
Her modül `python _test_<modul>.py` scriptiyle bağımsız test edilmiştir:

- `fetcher.py`: hash üretimi, datetime parse, `enabled=False` filtresi
- `deduplicator.py`: tekilleştirme, geçmiş yükleme/kaydetme, 7 gün temizliği
- `sanitizer.py`: XSS temizleme, URL doğrulama, özet kesme
- `categorizer.py`: satır doğrulama, fallback, mock client ile batch akışı
- `renderer.py`: filtreler, gruplama, 500KB koruma, uçtan uca render

### Entegrasyon Düzey
`python -m src.main` ile gerçek RSS + Gemini API ile uçtan uca çalıştırma. `docs/index.html` tarayıcıda açılarak görsel doğrulama yapılır.

### GitHub Actions
Her `push` ve günlük cron'da workflow otomatik çalışır; başarısız çalışmalar Actions sekmesinde kırmızı olarak işaretlenir.
