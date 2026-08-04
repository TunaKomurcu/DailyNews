"""
sanitizer.py — XSS temizleme ve FetchedItem → NewsItem dönüşümü.

Sorumluluklar:
  - Başlık ve özet metinlerini html.escape() ile temizler
  - Özeti summary_max_chars karaktere kırpar
  - URL scheme doğrulaması yapar (sadece http/https geçer)
  - FetchedItem'ı category="Genel" ile NewsItem'a dönüştürür
    (kategori atama işi categorizer.py'e bırakılır)

Not: renderer.py Jinja2'yi autoescape=False ile kullandığından
güvenli girdi garantisi tamamen bu modülün sorumluluğundadır.
"""

import html
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlparse
from typing import List

from src.fetcher import FetchedItem

logger = logging.getLogger(__name__)

# HTML tag temizleme için basit regex (özet içindeki tag'leri kaldırır)
_HTML_TAG_RE = re.compile(r"<[^>]+>")

# Ardışık boşlukları tek boşluğa indirger
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass
class NewsItem:
    """
    Sanitize edilmiş ve kategorilere ayrılmış haber.
    renderer.py tarafından HTML üretiminde kullanılır.
    """
    title: str        # html.escape() uygulanmış başlık
    url: str          # Doğrulanmış URL (geçersizse "#")
    summary: str      # html.escape() uygulanmış, kesilmiş özet (orijinal dil)
    published: datetime  # Timezone-aware UTC
    source_name: str  # html.escape() uygulanmış kaynak adı
    url_hash: str     # Değişmez — fetcher'dan geliyor
    category: str     # Başlangıçta "Genel"; categorizer günceller
    tr_summary: str = ""  # Gemini tarafından üretilen Türkçe özet (1 cümle)


def _sanitize_url(url: str) -> str:
    """
    URL'yi doğrular. Yalnızca http ve https scheme'lerine izin verir.
    Geçersiz veya güvensiz URL'leri "#" ile değiştirir.
    """
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            logger.debug("Geçersiz URL scheme atlandı: %r", url[:80])
            return "#"
        if not parsed.netloc:
            logger.debug("Netloc eksik, URL geçersiz: %r", url[:80])
            return "#"
        return url
    except Exception:  # noqa: BLE001
        return "#"


def _clean_text(text: str) -> str:
    """
    HTML tag'lerini kaldırır, ardışık boşlukları normalleştirir.
    html.escape() bu fonksiyondan SONRA uygulanır.
    """
    text = _HTML_TAG_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text)
    return text.strip()


def _truncate(text: str, max_chars: int) -> str:
    """Metni max_chars karaktere kırpar, kesilmişse '…' ekler."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "…"


def sanitize(item: FetchedItem, summary_max_chars: int = 300) -> NewsItem:
    """
    Tek bir FetchedItem'ı sanitize ederek NewsItem'a dönüştürür.

    Args:
        item:              Ham haber (fetcher'dan)
        summary_max_chars: Özet için maksimum karakter sayısı

    Returns:
        Güvenli ve kesilmiş alanlarla dolu NewsItem (category="Genel")
    """
    # Başlık: tag temizle → html.escape
    clean_title = html.escape(_clean_text(item.title))

    # Kaynak adı: html.escape
    clean_source = html.escape(item.source_name)

    # Özet: tag temizle → kes → html.escape
    clean_summary = _clean_text(item.summary)
    clean_summary = _truncate(clean_summary, summary_max_chars)
    clean_summary = html.escape(clean_summary)

    # URL: scheme doğrula
    safe_url = _sanitize_url(item.url)

    return NewsItem(
        title=clean_title,
        url=safe_url,
        summary=clean_summary,
        published=item.published,
        source_name=clean_source,
        url_hash=item.url_hash,
        category="Genel",  # categorizer.py tarafından güncellenecek
    )


def sanitize_all(items: List[FetchedItem], summary_max_chars: int = 300) -> List[NewsItem]:
    """
    FetchedItem listesini toplu olarak sanitize eder.

    Args:
        items:             Ham haber listesi
        summary_max_chars: Özet için maksimum karakter sayısı

    Returns:
        NewsItem listesi
    """
    result = [sanitize(item, summary_max_chars) for item in items]
    logger.info("%d haber sanitize edildi.", len(result))
    return result
