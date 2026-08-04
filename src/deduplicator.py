"""
deduplicator.py — Haber geçmişini yönetir ve tekrar eden haberleri filtreler.

İki ana sorumluluğu var:
  1. Gelen FetchedItem listesini history.json'daki hash setine karşı filtreler
     (aynı URL farklı kaynaklardan gelse de yakalar).
  2. Yeni kategorilenen haberleri geçmişe ekler, history_days'den eski
     kayıtları temizler.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Set

from src.fetcher import FetchedItem

logger = logging.getLogger(__name__)

# history.json şeması:
# {
#   "last_updated": "2026-08-04T07:05:00Z" | null,
#   "items": [ { ...NewsItem alanları... }, ... ]
# }


def _load_raw(history_path: str) -> dict:
    """
    history.json dosyasını yükler.
    Dosya yoksa veya bozuksa boş geçmiş sözlüğü döndürür.
    """
    path = Path(history_path)
    if not path.exists():
        logger.info("history.json bulunamadı, boş geçmiş başlatılıyor: %s", history_path)
        return {"last_updated": None, "items": []}

    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        # Temel şema kontrolü
        if "items" not in data:
            logger.warning("history.json 'items' anahtarı eksik, sıfırlanıyor.")
            return {"last_updated": None, "items": []}
        return data
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("history.json okunamadı (%s), boş geçmiş başlatılıyor.", exc)
        return {"last_updated": None, "items": []}


def _save_raw(data: dict, history_path: str) -> None:
    """history.json dosyasına yazar. Klasör yoksa oluşturur."""
    path = Path(history_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.debug("history.json kaydedildi: %s", history_path)


def load_seen_hashes(history_path: str) -> Set[str]:
    """
    Geçmişte kayıtlı tüm url_hash değerlerini bir set olarak döndürür.
    Tekilleştirme için hızlı O(1) arama sağlar.
    """
    data = _load_raw(history_path)
    hashes = {item["url_hash"] for item in data["items"] if "url_hash" in item}
    logger.debug("%d hash yüklendi.", len(hashes))
    return hashes


def deduplicate(items: List[FetchedItem], history_path: str) -> List[FetchedItem]:
    """
    Daha önce görülmüş haberleri listeden çıkarır.

    Args:
        items:        fetch_all()'dan gelen FetchedItem listesi
        history_path: history.json dosya yolu

    Returns:
        Yalnızca yeni (daha önce görülmemiş) haberleri içeren liste
    """
    seen = load_seen_hashes(history_path)
    new_items = [item for item in items if item.url_hash not in seen]

    # Aynı çalıştırmada birden fazla kaynaktan gelen duplicate'leri de temizle
    # (fetch_all içinde aynı URL iki kaynaktan gelmiş olabilir)
    unique: dict[str, FetchedItem] = {}
    for item in new_items:
        if item.url_hash not in unique:
            unique[item.url_hash] = item

    result = list(unique.values())
    logger.info(
        "Tekilleştirme: %d toplam → %d geçmişte var → %d yeni",
        len(items),
        len(items) - len(result),
        len(result),
    )
    return result


def update_history(new_items: list, history_path: str, history_days: int) -> None:
    """
    Yeni haberleri history.json'a ekler ve eski kayıtları temizler.

    Args:
        new_items:    Kategorilendirme sonrası NewsItem listesi (dict veya dataclass)
        history_path: history.json dosya yolu
        history_days: Kaç günlük geçmiş tutulsun
    """
    data = _load_raw(history_path)
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=history_days)

    # Mevcut kayıtlardan süresi dolmayanları tut
    kept = []
    removed = 0
    for item in data["items"]:
        pub_str = item.get("published")
        if pub_str:
            try:
                pub_dt = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
                if pub_dt >= cutoff:
                    kept.append(item)
                else:
                    removed += 1
            except ValueError:
                kept.append(item)  # Parse edilemeyen tarihi sil değil, tut
        else:
            kept.append(item)

    if removed:
        logger.info("%d eski kayıt temizlendi (%d günden eski).", removed, history_days)

    # Yeni haberleri dict'e çevir
    for item in new_items:
        if hasattr(item, "__dataclass_fields__"):
            # dataclass → dict
            from dataclasses import asdict
            item_dict = asdict(item)
            # datetime → ISO string
            if isinstance(item_dict.get("published"), datetime):
                item_dict["published"] = item_dict["published"].isoformat()
        elif isinstance(item, dict):
            item_dict = item.copy()
            if isinstance(item_dict.get("published"), datetime):
                item_dict["published"] = item_dict["published"].isoformat()
        else:
            logger.warning("Bilinmeyen item tipi, atlandı: %r", type(item))
            continue
        kept.append(item_dict)

    data["items"] = kept
    data["last_updated"] = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    _save_raw(data, history_path)
    logger.info(
        "Geçmiş güncellendi: %d yeni eklendi, toplam %d kayıt.",
        len(new_items),
        len(kept),
    )


def load_all_items(history_path: str) -> list:
    """
    history.json'daki tüm kayıtları dict listesi olarak döndürür.
    renderer.py tarafından HTML üretimi için kullanılır.
    """
    data = _load_raw(history_path)
    return data["items"]
