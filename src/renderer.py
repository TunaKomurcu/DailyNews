"""
renderer.py — Jinja2 ile docs/index.html üretir.

Tasarım kararları (design.md §3.6):
  - autoescape=False: sanitizer.py zaten html.escape() uyguladı;
    Jinja2'nin ek escape'i &amp;amp; gibi çift-escape hatası üretir.
  - 500KB boyut kontrolü: önce özet 150 karaktere kırp, hâlâ büyükse kaldır.
  - Tüm dış linkler rel="noopener noreferrer" ile template'de tanımlı.
  - Öne çıkan haberler: bugünün haberleri arasından kategori başına en yeni 1 haber.
  - Konu gruplama: başlık token overlap ile ilgili haberler gruplandırılır.
"""

import logging
import re
from collections import defaultdict
from datetime import datetime, timezone, timedelta
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


# ── Öne çıkan haberler ───────────────────────────────────────────────────────

# Önemsiz kelimeler — başlık karşılaştırmasından çıkarılır
_STOP_WORDS = {
    "a", "an", "the", "and", "or", "of", "in", "to", "for", "on",
    "with", "is", "are", "was", "be", "by", "as", "at", "from",
    "that", "this", "it", "new", "using", "how", "via", "what",
}


def _title_tokens(title: str) -> set:
    """Başlığı anlamlı token setine çevirir (küçük harf, stop word filtreli)."""
    words = re.findall(r"[a-zA-Z]{3,}", title.lower())
    return {w for w in words if w not in _STOP_WORDS}


def _pick_featured(items: list, max_featured: int = 6) -> list:
    """
    Bugünün haberleri arasından öne çıkanları seçer.

    Kural: her kategoriden en yeni 1 haber, toplam max_featured adete kadar.
    Bugün yayınlanmış haber yoksa son 48 saate genişler.
    """
    now = datetime.now(tz=timezone.utc)
    cutoffs = [now - timedelta(hours=24), now - timedelta(hours=48)]

    def _get_pub(item):
        pub = item.get("published") if isinstance(item, dict) else getattr(item, "published", None)
        if isinstance(pub, str):
            try:
                return datetime.fromisoformat(pub.replace("Z", "+00:00"))
            except ValueError:
                return datetime.min.replace(tzinfo=timezone.utc)
        return pub or datetime.min.replace(tzinfo=timezone.utc)

    for cutoff in cutoffs:
        recent = [i for i in items if _get_pub(i) >= cutoff]
        if len(recent) >= 3:
            break
    else:
        recent = sorted(items, key=_get_pub, reverse=True)[:max_featured]

    # Kategori başına en yeni 1 haber seç
    seen_cats: set = set()
    featured = []
    for item in sorted(recent, key=_get_pub, reverse=True):
        cat = item.get("category") if isinstance(item, dict) else getattr(item, "category", "Genel")
        if cat not in seen_cats:
            seen_cats.add(cat)
            featured.append(item)
        if len(featured) >= max_featured:
            break

    return featured


def _find_topic_groups(items: list, min_overlap: int = 2) -> dict:
    """
    Başlık token overlap ile ilişkili haberleri gruplar.

    Returns:
        dict: url_hash → group_id (aynı group_id'ye sahip haberler ilişkili)
              Grupsuz haberler dict'e dahil edilmez.
    """
    if not items:
        return {}

    def _get_hash(item):
        return item.get("url_hash") if isinstance(item, dict) else getattr(item, "url_hash", "")

    def _get_title(item):
        return item.get("title") if isinstance(item, dict) else getattr(item, "title", "")

    tokens_by_hash = {
        _get_hash(item): _title_tokens(_get_title(item))
        for item in items
    }

    hashes = list(tokens_by_hash.keys())
    group_id = 0
    hash_to_group: dict = {}
    group_of: dict = {}  # hash → group_id

    for i in range(len(hashes)):
        for j in range(i + 1, len(hashes)):
            h1, h2 = hashes[i], hashes[j]
            t1, t2 = tokens_by_hash[h1], tokens_by_hash[h2]
            if len(t1) < 2 or len(t2) < 2:
                continue
            overlap = len(t1 & t2)
            if overlap >= min_overlap:
                # İkisi de grupsuzsa → yeni grup
                g1 = group_of.get(h1)
                g2 = group_of.get(h2)
                if g1 is None and g2 is None:
                    group_id += 1
                    group_of[h1] = group_id
                    group_of[h2] = group_id
                elif g1 is not None and g2 is None:
                    group_of[h2] = g1
                elif g2 is not None and g1 is None:
                    group_of[h1] = g2
                # İkisi de farklı grupta ise — küçüğü büyüğe birleştir
                elif g1 != g2:
                    old, new = max(g1, g2), min(g1, g2)
                    for h, g in group_of.items():
                        if g == old:
                            group_of[h] = new

    # Sadece 2+ üyeli grupları döndür
    from collections import Counter
    group_sizes = Counter(group_of.values())
    return {h: g for h, g in group_of.items() if group_sizes[g] >= 2}


# ── Ana fonksiyon ────────────────────────────────────────────────────────────

def render(items: list, config: dict, archive_links: list = None) -> None:
    """
    NewsItem / dict listesinden docs/index.html üretir.

    Args:
        items:         history.json'dan yüklenen tüm haberler (son 7 gün)
        config:        config.yml içeriği
        archive_links: build_archive_index()'ten gelen arşiv linkleri
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

    # Öne çıkan haberler ve konu grupları
    featured = _pick_featured(working_items, max_featured=int(config.get("featured_count", 6)))
    topic_groups = _find_topic_groups(working_items)
    logger.info("Öne çıkan: %d haber, İlgili grup: %d haber", len(featured), len(topic_groups))

    def _render(cats, w_items):
        return template.render(
            categories=cats,
            category_order=category_order,
            total_count=total_count,
            generated_at=generated_at,
            date_label=date_label,
            featured=featured,
            topic_groups=topic_groups,
            is_archive=False,
            archive_date=None,
            archive_links=archive_links or [],
        )

    html_str = _render(categories, working_items)

    max_bytes = output_max_kb * 1024

    # 500KB kontrolü — Adım 1: özetleri 150 karaktere kırp
    if len(html_str.encode("utf-8")) > max_bytes:
        logger.warning(
            "HTML boyutu %d KB > %d KB limitini aşıyor. Özetler 150 karaktere kırpılıyor.",
            len(html_str.encode("utf-8")) // 1024, output_max_kb,
        )
        working_items = _trim_summaries(working_items, max_chars=150)
        categories = _group_by_category(working_items, category_order)
        html_str = _render(categories, working_items)

    # 500KB kontrolü — Adım 2: özetleri tamamen kaldır
    if len(html_str.encode("utf-8")) > max_bytes:
        logger.warning(
            "HTML hâlâ %d KB > %d KB. Özetler tamamen kaldırılıyor.",
            len(html_str.encode("utf-8")) // 1024, output_max_kb,
        )
        working_items = _clear_summaries(working_items)
        categories = _group_by_category(working_items, category_order)
        html_str = _render(categories, working_items)

    # Çıktıyı yaz
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_str, encoding="utf-8")

    final_kb = len(html_str.encode("utf-8")) // 1024
    logger.info(
        "docs/index.html üretildi: %d haber, %d KB (%s)",
        total_count, final_kb, output_path,
    )


# ── Arşiv fonksiyonları ──────────────────────────────────────────────────────

def render_archive_page(items: list, date_str: str, config: dict) -> None:
    """
    Belirli bir güne ait haberleri docs/archive/YYYY-MM-DD.html olarak yazar.

    Args:
        items:    O güne ait haberler (dict listesi)
        date_str: "2026-08-04" formatında tarih
        config:   config.yml içeriği
    """
    paths = config.get("paths", {})
    docs_dir = Path(paths.get("output_html", "docs/index.html")).parent
    template_path = paths.get("template", "templates/index.html.j2")
    output_max_kb = int(config.get("output_max_kb", 500))
    category_order = config.get("categories", ["Genel"])

    templates_dir = str(Path(template_path).parent)
    template_name = Path(template_path).name

    archive_dir = docs_dir / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    output_path = archive_dir / f"{date_str}.html"

    try:
        dt = datetime.fromisoformat(date_str)
    except ValueError:
        dt = datetime.now(tz=timezone.utc)

    date_label = _make_date_label(dt)
    generated_at = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M")

    env = _build_env(templates_dir)
    template = env.get_template(template_name)

    working_items = list(items)
    categories = _group_by_category(working_items, category_order)
    total_count = sum(len(v) for v in categories.values())
    topic_groups = _find_topic_groups(working_items)

    html_str = template.render(
        categories=categories,
        category_order=category_order,
        total_count=total_count,
        generated_at=generated_at,
        date_label=date_label,
        featured=[],         # Arşiv sayfasında öne çıkanlar yok
        topic_groups=topic_groups,
        is_archive=True,
        archive_date=date_str,
        archive_links=[],
    )

    if len(html_str.encode("utf-8")) > output_max_kb * 1024:
        working_items = _trim_summaries(working_items, max_chars=150)
        categories = _group_by_category(working_items, category_order)
        html_str = template.render(
            categories=categories, category_order=category_order,
            total_count=total_count, generated_at=generated_at,
            date_label=date_label, featured=[], topic_groups=topic_groups,
            is_archive=True, archive_date=date_str, archive_links=[],
        )

    output_path.write_text(html_str, encoding="utf-8")
    logger.info("Arşiv sayfası üretildi: %s (%d haber)", output_path.name, total_count)


def build_archive_index(config: dict) -> list:
    """
    docs/archive/ klasöründeki tüm YYYY-MM-DD.html dosyalarını tarar,
    tarih sırasında (yeniden eskiye) arşiv link listesi döndürür.

    Returns:
        [{"date": "2026-08-04", "label": "4 Ağustos 2026", "url": "archive/2026-08-04.html"}, ...]
    """
    paths = config.get("paths", {})
    docs_dir = Path(paths.get("output_html", "docs/index.html")).parent
    archive_dir = docs_dir / "archive"

    if not archive_dir.exists():
        return []

    links = []
    for f in sorted(archive_dir.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].html"), reverse=True):
        date_str = f.stem  # "2026-08-04"
        try:
            dt = datetime.fromisoformat(date_str)
            label = _make_date_label(dt)
        except ValueError:
            label = date_str
        links.append({
            "date": date_str,
            "label": label,
            "url": f"archive/{f.name}",
        })

    return links


def get_items_for_date(all_items: list, date_str: str) -> list:
    """
    Tüm geçmiş haberler arasından belirli bir güne ait olanları döndürür.

    Args:
        all_items: history.json'dan yüklenen tüm haberler
        date_str:  "2026-08-04" formatında tarih

    Returns:
        O güne ait haber listesi
    """
    result = []
    for item in all_items:
        pub = item.get("published") if isinstance(item, dict) else getattr(item, "published", None)
        if isinstance(pub, str):
            if pub.startswith(date_str):
                result.append(item)
        elif isinstance(pub, datetime):
            if pub.strftime("%Y-%m-%d") == date_str:
                result.append(item)
    return result
