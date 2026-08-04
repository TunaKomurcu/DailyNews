"""
renderer.py — Jinja2 ile docs/index.html üretir.

Tasarım kararları (design.md §3.6):
  - autoescape=False: sanitizer.py zaten html.escape() uyguladı;
    Jinja2'nin ek escape'i &amp;amp; gibi çift-escape hatası üretir.
  - 500KB boyut kontrolü: önce özet 150 karaktere kırp, hâlâ büyükse kaldır.
  - Tüm dış linkler rel="noopener noreferrer" ile template'de tanımlı.
"""

import logging
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)

# Kategori → emoji eşlemesi
_CATEGORY_ICONS = {
    "Araştırma":             "🔬",
    "Mühendislik/Mimari":    "⚙️",
    "Ürün/Şirket Haberleri": "🏢",
    "Kullanıcıyı Etkileyen": "👥",
    "Regülasyon/Politika":   "⚖️",
    "Yatırım/Startup":       "💰",
    "Açık Kaynak":           "🌐",
    "Genel":                 "📰",
}

# Türkçe ay adları
_TR_MONTHS = [
    "", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
]


# ── Jinja2 özel filtreler ────────────────────────────────────────────────────

def _filter_format_date(value) -> str:
    """
    datetime veya ISO string'i "4 Ağustos 2026, 09:00" formatına çevirir.
    Geçersiz değerlerde boş string döner.
    """
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return ""
    if isinstance(value, datetime):
        return f"{value.day} {_TR_MONTHS[value.month]} {value.year}, {value.hour:02d}:{value.minute:02d}"
    return ""


def _filter_slugify(value: str) -> str:
    """
    Kategori adını HTML id'sine uygun slug'a çevirir.
    "Mühendislik/Mimari" → "muhendislik-mimari"
    """
    replacements = {
        "ı": "i", "ğ": "g", "ü": "u", "ş": "s",
        "ö": "o", "ç": "c", "İ": "i", "Ğ": "g",
        "Ü": "u", "Ş": "s", "Ö": "o", "Ç": "c",
    }
    s = value.lower()
    for tr_char, en_char in replacements.items():
        s = s.replace(tr_char, en_char)
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def _filter_category_icon(value: str) -> str:
    """Kategori adına göre emoji döndürür."""
    return _CATEGORY_ICONS.get(value, "📰")


# ── Yardımcı fonksiyonlar ────────────────────────────────────────────────────

def _build_env(templates_dir: str) -> Environment:
    """
    Jinja2 Environment oluşturur.
    autoescape=False — sanitizer.py çift-escape'i önlemek için.
    """
    env = Environment(
        loader=FileSystemLoader(templates_dir),
        autoescape=False,  # sanitizer.py zaten html.escape() uyguladı
    )
    env.filters["format_date"] = _filter_format_date
    env.filters["slugify"] = _filter_slugify
    env.filters["category_icon"] = _filter_category_icon
    return env


def _group_by_category(items: list, category_order: List[str]) -> dict:
    """
    Item listesini (dict veya NewsItem) kategoriye göre gruplar.
    category_order'daki sıraya göre sıralanmış dict döner.
    """
    groups: dict = defaultdict(list)
    for item in items:
        cat = item.get("category") if isinstance(item, dict) else getattr(item, "category", "Genel")
        groups[cat].append(item)
    # Sadece category_order'da tanımlı kategorileri döndür; bilinmeyenleri "Genel"e yönlendir
    result = {}
    for cat in category_order:
        result[cat] = groups.get(cat, [])
    # category_order'da olmayan kategorileri "Genel"e ekle
    known = set(category_order)
    for cat, cat_items in groups.items():
        if cat not in known:
            result.setdefault("Genel", []).extend(cat_items)
    return result


def _trim_summaries(items: list, max_chars: int) -> list:
    """
    Item listesindeki tüm özet alanlarını max_chars'a kırpar.
    item dict ise "summary" key'ini, dataclass ise summary alanını günceller.
    Orijinal listeyi in-place değil, kopyasını döndürür.
    """
    trimmed = []
    for item in items:
        if isinstance(item, dict):
            new = dict(item)
            summary = new.get("summary", "")
            if len(summary) > max_chars:
                new["summary"] = summary[:max_chars].rstrip() + "…"
            trimmed.append(new)
        else:
            # dataclass — yeni instance oluşturmak yerine shallow copy yeter
            import copy
            new = copy.copy(item)
            if len(new.summary) > max_chars:
                new.summary = new.summary[:max_chars].rstrip() + "…"
            trimmed.append(new)
    return trimmed


def _clear_summaries(items: list) -> list:
    """Tüm özet alanlarını boşaltır (500KB aşıldığında son çare)."""
    cleared = []
    for item in items:
        if isinstance(item, dict):
            new = dict(item)
            new["summary"] = ""
            cleared.append(new)
        else:
            import copy
            new = copy.copy(item)
            new.summary = ""
            cleared.append(new)
    return cleared


def _make_date_label(dt: datetime) -> str:
    """datetime → "4 Ağustos 2026" biçiminde Türkçe tarih."""
    return f"{dt.day} {_TR_MONTHS[dt.month]} {dt.year}"


# ── Ana fonksiyon ────────────────────────────────────────────────────────────

def render(items: list, config: dict) -> None:
    """
    NewsItem / dict listesinden docs/index.html üretir.

    Args:
        items:  history.json'dan yüklenen tüm haberler (son 7 gün)
        config: config.yml içeriği
    """
    paths = config.get("paths", {})
    output_path = paths.get("output_html", "docs/index.html")
    template_path = paths.get("template", "templates/index.html.j2")
    output_max_kb = int(config.get("output_max_kb", 500))
    category_order = config.get("categories", ["Genel"])

    templates_dir = str(Path(template_path).parent)
    template_name = Path(template_path).name

    now_utc = datetime.now(tz=timezone.utc)
    date_label = _make_date_label(now_utc)
    generated_at = now_utc.strftime("%Y-%m-%d %H:%M")

    env = _build_env(templates_dir)
    template = env.get_template(template_name)

    # İlk render denemesi
    working_items = list(items)
    categories = _group_by_category(working_items, category_order)
    total_count = sum(len(v) for v in categories.values())

    html_str = template.render(
        categories=categories,
        category_order=category_order,
        total_count=total_count,
        generated_at=generated_at,
        date_label=date_label,
    )

    max_bytes = output_max_kb * 1024

    # 500KB kontrolü — Adım 1: özetleri 150 karaktere kırp
    if len(html_str.encode("utf-8")) > max_bytes:
        logger.warning(
            "HTML boyutu %d KB > %d KB limitini aşıyor. Özetler 150 karaktere kırpılıyor.",
            len(html_str.encode("utf-8")) // 1024, output_max_kb,
        )
        working_items = _trim_summaries(working_items, max_chars=150)
        categories = _group_by_category(working_items, category_order)
        html_str = template.render(
            categories=categories,
            category_order=category_order,
            total_count=total_count,
            generated_at=generated_at,
            date_label=date_label,
        )

    # 500KB kontrolü — Adım 2: özetleri tamamen kaldır
    if len(html_str.encode("utf-8")) > max_bytes:
        logger.warning(
            "HTML hâlâ %d KB > %d KB. Özetler tamamen kaldırılıyor.",
            len(html_str.encode("utf-8")) // 1024, output_max_kb,
        )
        working_items = _clear_summaries(working_items)
        categories = _group_by_category(working_items, category_order)
        html_str = template.render(
            categories=categories,
            category_order=category_order,
            total_count=total_count,
            generated_at=generated_at,
            date_label=date_label,
        )

    # Çıktıyı yaz
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_str, encoding="utf-8")

    final_kb = len(html_str.encode("utf-8")) // 1024
    logger.info(
        "docs/index.html üretildi: %d haber, %d KB (%s)",
        total_count, final_kb, output_path,
    )
