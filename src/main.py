"""
main.py — Günlük AI Haber Toplayıcı giriş noktası.

Çalıştırma: python -m src.main

Adımlar:
  1. config.yml yükle
  2. RSS kaynaklarından son 24 saatin haberlerini çek
  3. Daha önce görülmüş haberleri eleyin (tekilleştirme)
  4. Sanitize et: FetchedItem → NewsItem (html.escape, URL doğrulama)
  5. Gemini API ile kategorilere ayır
  6. Yeni haberleri history.json'a ekle, eski kayıtları temizle
  7. Tüm geçmişi (son 7 gün) yükle
  8. docs/index.html üret
"""

import logging
import sys
import time
from pathlib import Path

import yaml

from src.fetcher import fetch_all
from src.deduplicator import deduplicate, update_history, load_all_items
from src.sanitizer import sanitize_all
from src.categorizer import categorize
from src.renderer import render, render_archive_page, build_archive_index, get_items_for_date

# ── Logging yapılandırması ───────────────────────────────────────────────────

def _setup_logging() -> None:
    """Konsola INFO ve üstünü yazar; timestamp + seviye + mesaj formatı."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


# ── Config yükleme ───────────────────────────────────────────────────────────

def _load_config(config_path: str = "config.yml") -> dict:
    """
    config.yml dosyasını yükler.
    Dosya yoksa veya parse edilemezse hata fırlatır.
    """
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(
            f"config.yml bulunamadı: {config_path}\n"
            "Proje kökünden çalıştırdığınızdan emin olun: python -m src.main"
        )
    with path.open(encoding="utf-8") as f:
        config = yaml.safe_load(f)
    if not config:
        raise ValueError("config.yml boş veya geçersiz.")
    return config


# ── Ana akış ────────────────────────────────────────────────────────────────

def main() -> None:
    _setup_logging()
    logger = logging.getLogger(__name__)
    start_time = time.time()

    logger.info("=" * 55)
    logger.info("Günlük AI Haber Toplayıcı başlatılıyor")
    logger.info("=" * 55)

    # ── 1. Config ───────────────────────────────────────────────
    logger.info("Adım 1/8 — Yapılandırma yükleniyor...")
    config = _load_config("config.yml")
    history_path = config.get("paths", {}).get("history", "data/history.json")
    history_days = int(config.get("history_days", 7))
    summary_max_chars = int(config.get("summary_max_chars", 300))
    logger.info(
        "  Kaynak sayısı: %d, Kategori sayısı: %d, Geçmiş: %d gün",
        sum(1 for s in config.get("sources", []) if s.get("enabled", True)),
        len(config.get("categories", [])),
        history_days,
    )

    # ── 2. RSS Toplama ───────────────────────────────────────────
    logger.info("Adım 2/8 — RSS kaynaklarından haberler çekiliyor...")
    fetched = fetch_all(config["sources"])
    logger.info("  Çekilen toplam haber: %d", len(fetched))

    if not fetched:
        logger.warning("  Hiç haber çekilemedi. Kaynakları ve internet bağlantısını kontrol edin.")

    # ── 3. Tekilleştirme ─────────────────────────────────────────
    logger.info("Adım 3/8 — Daha önce görülen haberler eleniyor...")
    new_fetched = deduplicate(fetched, history_path)
    logger.info("  Yeni haber sayısı: %d", len(new_fetched))

    # ── 4. Sanitizasyon ──────────────────────────────────────────
    logger.info("Adım 4/8 — Haberler sanitize ediliyor...")
    clean_items = sanitize_all(new_fetched, summary_max_chars=summary_max_chars)
    logger.info("  Sanitize edilen haber: %d", len(clean_items))

    # ── 5. Kategorilendirme ──────────────────────────────────────
    if clean_items:
        logger.info("Adım 5/8 — Gemini API ile kategorilere ayrılıyor...")
        categorized = categorize(clean_items, config)
        cat_counts: dict = {}
        for item in categorized:
            cat_counts[item.category] = cat_counts.get(item.category, 0) + 1
        logger.info("  Kategori dağılımı: %s", cat_counts)
    else:
        logger.info("Adım 5/8 — Yeni haber yok, kategorilendirme atlandı.")
        categorized = []

    # ── 6. Geçmişi Güncelle ──────────────────────────────────────
    logger.info("Adım 6/8 — Geçmiş güncelleniyor (history.json)...")
    update_history(categorized, history_path, history_days=history_days)

    # ── 7. Tüm Geçmişi Yükle ────────────────────────────────────
    logger.info("Adım 7/8 — Son %d günlük haberler yükleniyor...", history_days)
    all_items = load_all_items(history_path)
    logger.info("  Toplam gösterilecek haber: %d", len(all_items))

    # ── 8. HTML Üret ─────────────────────────────────────────────
    logger.info("Adım 8/8 — docs/index.html üretiliyor...")
    from datetime import date as _date
    today_str = _date.today().strftime("%Y-%m-%d")
    today_items = get_items_for_date(all_items, today_str)
    if today_items:
        render_archive_page(today_items, today_str, config)
    else:
        logger.info("Bugun arsiv atlandi")
    archive_links = build_archive_index(config)
    logger.info("Arsiv: %d gun", len(archive_links))
    render(all_items, config, archive_links=archive_links)

    # ── Özet ─────────────────────────────────────────────────────
    elapsed = time.time() - start_time
    logger.info("=" * 55)
    logger.info(
        "Tamamlandı: %d yeni haber işlendi, %d toplam haber sayfada. (%.1fs)",
        len(categorized),
        len(all_items),
        elapsed,
    )
    logger.info("=" * 55)


if __name__ == "__main__":
    main()
