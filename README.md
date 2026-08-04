# Daily AI News

RSS kaynaklarından günlük yapay zeka haberlerini toplayıp kategorilere ayıran
ve statik bir HTML sayfası olarak GitHub Pages'e yayınlayan otomasyon projesi.

## Nasıl Çalışır?

1. Her gün 04:00 UTC (07:00 Türkiye saati) GitHub Actions otomatik çalışır
2. arXiv, OpenAI Blog, Anthropic Blog, Hacker News ve TechCrunch AI kaynaklarından
   son 24 saatin haberleri toplanır
3. Her haber Google Gemini API ile kategorilere ayrılır
4. Statik bir HTML sayfası üretilir ve `docs/` klasörüne yazılır
5. GitHub Pages üzerinden yayınlanır

## Kurulum (Yerel Çalıştırma)

### 1. Bağımlılıkları yükle

```bash
pip install -r requirements.txt
```

### 2. API anahtarını ayarla

**Windows PowerShell:**
```powershell
$env:GEMINI_API_KEY = "your-api-key-here"
```

**Linux / macOS:**
```bash
export GEMINI_API_KEY="your-api-key-here"
```

Gemini API anahtarını [Google AI Studio](https://aistudio.google.com/apikey)'dan ücretsiz alabilirsiniz.

### 3. Çalıştır

```bash
python -m src.main
```

Çalıştırma sonunda `docs/index.html` dosyasını tarayıcıda açarak sonucu görebilirsiniz.

## GitHub Actions Kurulumu

1. Bu repoyu GitHub'a push edin
2. **Settings → Secrets and variables → Actions** bölümünden `GEMINI_API_KEY` secret'ını ekleyin
3. **Settings → Pages** bölümünden source olarak `main` branch, `docs/` klasörünü seçin
4. Workflow her gün otomatik çalışır; **Actions** sekmesinden manuel de tetikleyebilirsiniz

## Yapılandırma

RSS kaynaklarını veya kategorileri değiştirmek için `config.yml` dosyasını düzenleyin.
Her kaynağın `enabled: false` yapılarak devre dışı bırakılabilir.

## Proje Yapısı

```
DailyNews/
├── .github/workflows/daily_news.yml   # Günlük otomasyon
├── src/
│   ├── main.py                        # Giriş noktası
│   ├── fetcher.py                     # RSS toplama
│   ├── deduplicator.py                # Tekilleştirme
│   ├── sanitizer.py                   # XSS temizleme
│   ├── categorizer.py                 # Gemini ile kategorilendirme
│   └── renderer.py                    # HTML üretimi
├── templates/index.html.j2            # Jinja2 sayfa şablonu
├── data/history.json                  # Son 7 günlük haber geçmişi
├── docs/index.html                    # Üretilen statik sayfa
├── config.yml                         # Kaynak ve kategori ayarları
└── requirements.txt                   # Python bağımlılıkları
```

## Kullanılan Teknolojiler

- **Python 3.9+**
- **feedparser** — RSS parse
- **google-genai** — Gemini 2.5 Flash-Lite kategorilendirme
- **Jinja2** — HTML şablon motoru
- **GitHub Actions** — günlük otomasyon
- **GitHub Pages** — ücretsiz statik hosting
