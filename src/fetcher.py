"""
fetcher.py — RSS kaynaklarından son 24 saatin haberlerini çeker.

Her kaynak bağımsız olarak işlenir; bir kaynak hata verirse diğerleri
etkilenmez. Tüm tarihler timezone-aware UTC'ye normalize edilir.
"""

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import List, Optional

import feedparser

logger = logging.getLogger(__name__)


@dataclass
class FetchedItem:
    """RSS'ten çekilen ham haber. Henüz sanitize veya kategorilenmemiş."""
    title: str
    url: str
    summary: str       # Özet metin; feed'de yoksa boş string
    published: datetime  # Timezone-aware UTC
    source_name: str   # Kaynak adı (config'deki name alanı)
    url_hash: str      # sha256(url)[:16] — tekilleştirme anahtarı


def _compute_hash(url: str) -> str:
    """URL'den 16 karakterlik SHA-256 özeti üretir."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def _parse_datetime(entry: feedparser.FeedParserDict) -> Optional[datetime]:
    """
    feedparser entry'sinden timezone-aware UTC datetime döndürür.
    published_parsed → updated_parsed → None sırasıyla dener.
    feedparser time.struct_time nesnelerini UTC'ye dönüştürür.
    """
    import calendar

    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t is not None:
            try:
                # time.struct_time → Unix timestamp (UTC varsayılır) → datetime
                ts = calendar.timegm(t)
                return datetime.fromtimestamp(ts, tz=timezone.utc)
            except (TypeError, ValueError, OverflowError):
                continue
    return None


def _fetch_source(source: dict, cutoff: datetime) -> List[FetchedItem]:
    """
    Tek bir RSS kaynağından cutoff tarihinden sonraki haberleri döndürür.

    Args:
        source: config.yml'deki tek bir kaynak sözlüğü
                {"name": ..., "url": ..., "enabled": ..., "max_items": ...}
        cutoff: Bu tarihten önce yayınlanan haberler atlanır (UTC)

    Returns:
        FetchedItem listesi (boş olabilir, max_items ile sınırlı)
    """
    name = source["name"]
    url = source["url"]
    max_items = source.get("max_items")  # None ise limit yok
    items: List[FetchedItem] = []

    logger.info("Çekiliyor: %s (%s)", name, url)

    try:
        # feedparser kendi içinde HTTP isteğini yönetir;
        # request_headers ile timeout benzeri kontrol için
        # önce requests ile indirip feedparser'a string olarak verebiliriz.
        # Bu yaklaşım timeout kontrolü sağlar.
        import requests

        resp = requests.get(url, timeout=15, headers={"User-Agent": "DailyAINews/1.0"})
        resp.raise_for_status()
        feed = feedparser.parse(resp.text)
    except requests.exceptions.Timeout:
        logger.warning("Timeout: %s — kaynak atlandı", name)
        return items
    except requests.exceptions.RequestException as exc:
        logger.warning("HTTP hatası: %s — %s — kaynak atlandı", name, exc)
        return items
    except Exception as exc:  # noqa: BLE001
        logger.warning("Beklenmeyen hata: %s — %s — kaynak atlandı", name, exc)
        return items

    if feed.bozo and not feed.entries:
        # bozo=True: parse hatası var; entries boşsa kaynaktan veri gelmedi
        logger.warning("Feed parse hatası: %s — %s", name, feed.bozo_exception)
        return items

    for entry in feed.entries:
        # --- Zorunlu alanlar ---
        title = getattr(entry, "title", "").strip()
        link = getattr(entry, "link", "").strip()

        if not title or not link:
            logger.debug("Başlık veya URL eksik, atlandı: %r", entry)
            continue

        # --- Tarih kontrolü ---
        pub_dt = _parse_datetime(entry)
        if pub_dt is None:
            # Tarih yoksa haberi dahil et ama uyar
            logger.debug("Tarih bilgisi yok, dahil ediliyor: %s", title[:60])
            pub_dt = datetime.now(tz=timezone.utc)

        if pub_dt < cutoff:
            continue  # 24 saatten eski

        # --- Özet ---
        summary = ""
        for attr in ("summary", "description", "content"):
            val = getattr(entry, attr, None)
            if val:
                # content bir liste olabilir (feedparser)
                if isinstance(val, list) and val:
                    val = val[0].get("value", "")
                summary = str(val).strip()
                if summary:
                    break

        items.append(FetchedItem(
            title=title,
            url=link,
            summary=summary,
            published=pub_dt,
            source_name=name,
            url_hash=_compute_hash(link),
        ))

        # max_items limitine ulaşıldıysa dur
        if max_items and len(items) >= max_items:
            logger.debug("max_items=%d limitine ulaşıldı: %s", max_items, name)
            break

    limit_str = f" (max_items={max_items} ile sınırlı)" if max_items else ""
    logger.info("  → %d haber bulundu (son 24 saat)%s: %s", len(items), limit_str, name)
    return items


def fetch_all(sources: list) -> List[FetchedItem]:
    """
    Tüm etkin kaynaklardan son 24 saatin haberlerini çeker.

    Args:
        sources: config.yml'deki sources listesi

    Returns:
        Tüm kaynaklardan birleştirilmiş FetchedItem listesi
    """
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=24)
    logger.info("24 saat kesim zamanı (UTC): %s", cutoff.isoformat())

    all_items: List[FetchedItem] = []

    for source in sources:
        if not source.get("enabled", True):
            logger.info("Devre dışı kaynak atlandı: %s", source.get("name"))
            continue
        items = _fetch_source(source, cutoff)
        all_items.extend(items)

    logger.info("Toplam çekilen haber: %d", len(all_items))
    return all_items
