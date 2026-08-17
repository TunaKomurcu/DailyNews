# Daily AI News

An automation project that collects daily artificial intelligence news from RSS feeds, categorizes them, and publishes them as a static HTML page to GitHub Pages.

## How It Works

1. GitHub Actions runs automatically every day at 04:00 UTC (07:00 Turkey time).
2. News from the last 24 hours is collected from arXiv, OpenAI Blog, Anthropic Blog, Hacker News, and TechCrunch AI sources.
3. Each news item is categorized using the Google Gemini API.
4. A static HTML page is generated and written to the `docs/` directory.
5. It is published via GitHub Pages.

## Installation (Local Execution)

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Set the API key

**Windows PowerShell:**
```powershell
$env:GEMINI_API_KEY = "your-api-key-here"
```

**Linux / macOS:**
```bash
export GEMINI_API_KEY="your-api-key-here"
```

You can get the Gemini API key for free from [Google AI Studio](https://aistudio.google.com/apikey).

### 3. Run

```bash
python -m src.main
```

At the end of the run, you can see the result by opening the `docs/index.html` file in your browser.

## GitHub Actions Setup

1. Push this repository to GitHub.
2. Add the `GEMINI_API_KEY` secret under **Settings → Secrets and variables → Actions**.
3. Under **Settings → Pages**, select the `main` branch and the `docs/` folder as the source.
4. The workflow runs automatically every day; you can also trigger it manually from the **Actions** tab.

## Configuration

Edit the `config.yml` file to change RSS sources or categories.
Each source can be disabled by setting `enabled: false`.

## Project Structure

```
DailyNews/
├── .github/workflows/daily_news.yml   # Daily automation
├── src/
│   ├── main.py                        # Entry point
│   ├── fetcher.py                     # RSS fetching
│   ├── deduplicator.py                # Deduplication
│   ├── sanitizer.py                   # XSS sanitization
│   ├── categorizer.py                 # Categorization with Gemini
│   └── renderer.py                    # HTML generation
├── templates/index.html.j2            # Jinja2 page template
├── data/history.json                  # Last 7 days news history
├── docs/index.html                    # Generated static page
├── config.yml                         # Source and category settings
└── requirements.txt                   # Python dependencies
```

## Technologies Used

- **Python 3.9+**
- **feedparser** — RSS parsing
- **google-genai** — Gemini 2.5 Flash-Lite categorization
- **Jinja2** — HTML template engine
- **GitHub Actions** — Daily automation
- **GitHub Pages** — Free static hosting
