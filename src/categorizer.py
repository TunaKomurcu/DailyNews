"""
categorizer.py — Google Gemini API ile haber kategorilendirme.

Tasarım kararları (design.md §3.4):
  - Model: gemini-2.5-flash (ücretsiz katman: 10 RPM, 1000/gün)
  - 20'lik batch'ler — tek prompt, tek API çağrısı
  - Satır sayısı doğrulaması: eşleşmezse tüm batch → "Genel"
  - Exponential backoff: 429/geçici hata → retry_delay veya 1s→2s→4s, max 3 retry
  - Geçersiz kategori adı → "Genel" fallback
  - GEMINI_API_KEY ortam değişkeni yoksa açıklayıcı hatayla dur
"""

import logging
import os
import re
import time
from typing import List

logger = logging.getLogger(__name__)

# Prompt şablonu — başlıklar numaralandırılmış satırlar olarak eklenir
_PROMPT_TEMPLATE = """\
Aşağıdaki {n} haber başlığını verilen kategorilerden birine ata.

Kategoriler: {categories}

Kurallar:
- Her satır için YALNIZCA kategori adını döndür (başka hiçbir şey yazma)
- Satır sırası gönderdiğimle AYNI olmalı
- Emin olamadığın haberler için "Genel" yaz
- Toplam {n} satır döndür, ne eksik ne fazla

Haberler:
{titles}"""


def _build_client():
    """
    Gemini API istemcisini oluşturur.
    GEMINI_API_KEY ortam değişkeni yoksa RuntimeError fırlatır.
    """
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY ortam değişkeni ayarlanmamış. "
            "Google AI Studio'dan (https://aistudio.google.com/apikey) "
            "ücretsiz bir anahtar alıp 'GEMINI_API_KEY' olarak ayarlayın."
        )
    from google import genai
    return genai.Client(api_key=api_key)


def _parse_response(response_text: str, expected_count: int, valid_categories: set) -> List[str]:
    """
    Gemini yanıtını satırlara ayırır ve doğrular.

    Satır sayısı expected_count ile eşleşmezse None döndürür
    (çağıran kod tüm batch'i "Genel" yapacak).

    Her satırdaki kategori adı valid_categories'de yoksa "Genel" atar.
    """
    # Boş satırları ve baştaki/sondaki boşlukları temizle
    lines = [ln.strip() for ln in response_text.strip().splitlines()]
    lines = [ln for ln in lines if ln]

    # Bazen Gemini "1. Araştırma" gibi numaralı yanıt verebilir — sayıyı sıyır
    cleaned: List[str] = []
    for line in lines:
        # "1. Kategori" veya "1) Kategori" formatını temizle
        m = re.match(r"^\d+[.)]\s*(.+)$", line)
        cleaned.append(m.group(1).strip() if m else line)

    if len(cleaned) != expected_count:
        return []  # Satır sayısı uyuşmuyor → çağıran "Genel" yapacak

    result: List[str] = []
    for cat in cleaned:
        if cat in valid_categories:
            result.append(cat)
        else:
            logger.debug("Bilinmeyen kategori '%s' → 'Genel'", cat)
            result.append("Genel")
    return result


def _categorize_batch(
    client,
    titles: List[str],
    model: str,
    categories: List[str],
    max_retries: int,
) -> List[str]:
    """
    Tek bir batch (≤20 başlık) için Gemini API çağrısını yapar.

    Başarısız olursa (retry tükenir veya satır uyuşmazlığı) tüm batch
    için "Genel" listesi döndürür.
    """
    valid_categories = set(categories)
    n = len(titles)
    numbered_titles = "\n".join(f"{i+1}. {t}" for i, t in enumerate(titles))
    prompt = _PROMPT_TEMPLATE.format(
        n=n,
        categories=", ".join(categories),
        titles=numbered_titles,
    )

    last_exc = None
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
            )
            result_text = response.text
            parsed = _parse_response(result_text, n, valid_categories)

            if not parsed:
                # Satır sayısı uyuşmazlığı
                lines_got = len([ln for ln in result_text.strip().splitlines() if ln.strip()])
                logger.warning(
                    "Batch satır sayısı uyuşmazlığı — beklenen: %d, gelen: %d. "
                    "Tüm batch 'Genel' atandı.",
                    n, lines_got,
                )
                return ["Genel"] * n

            return parsed

        except Exception as exc:  # noqa: BLE001
            # 429 veya geçici hata kontrolü
            exc_str = str(exc)
            is_rate_limit = "429" in exc_str or "RESOURCE_EXHAUSTED" in exc_str.upper()
            is_transient = any(
                kw in exc_str.upper()
                for kw in ("503", "500", "UNAVAILABLE", "INTERNAL")
            )

            if is_rate_limit or is_transient:
                # API yanıtında retryDelay varsa onu kullan, yoksa exponential backoff
                retry_delay = None
                try:
                    import json as _json
                    # exc_str içinde retryDelay saniye değeri olabilir
                    delay_match = re.search(r"retryDelay.*?'(\d+)s'", exc_str)
                    if delay_match:
                        retry_delay = int(delay_match.group(1)) + 2  # biraz ekstra
                except Exception:
                    pass

                wait = retry_delay if retry_delay else 2 ** attempt  # 1s, 2s, 4s
                # Rate limit için minimum 7s bekle (10 RPM = 6s/istek, güvenli taraf)
                if is_rate_limit:
                    wait = max(wait, 7)
                logger.warning(
                    "API hatası (deneme %d/%d): %s — %ds bekleniyor.",
                    attempt + 1, max_retries, exc_str[:120], wait,
                )
                time.sleep(wait)
                last_exc = exc
            else:
                # Beklenmeyen hata — retry'a gerek yok
                logger.error("Beklenmeyen API hatası: %s", exc_str[:200])
                last_exc = exc
                break

    logger.error(
        "%d deneme başarısız. Batch 'Genel' atandı. Son hata: %s",
        max_retries, last_exc,
    )
    return ["Genel"] * n


def categorize(items: list, config: dict) -> list:
    """
    NewsItem listesindeki her habere Gemini API ile kategori atar.
    items listesi in-place güncellenir ve aynı liste döndürülür.

    Args:
        items:  sanitize_all()'dan gelen NewsItem listesi
        config: config.yml içeriği (llm, categories anahtarları beklenir)

    Returns:
        category alanı güncellenmiş NewsItem listesi
    """
    if not items:
        logger.info("Kategorilendirme: item yok, atlanıyor.")
        return items

    llm_cfg = config.get("llm", {})
    model = llm_cfg.get("model", "gemini-3.5-flash-lite")
    batch_size = int(llm_cfg.get("batch_size", 20))
    max_retries = int(llm_cfg.get("max_retries", 3))
    categories = config.get("categories", ["Genel"])

    client = _build_client()
    logger.info(
        "Kategorilendirme başlıyor: %d haber, %d'lik batch, model=%s",
        len(items), batch_size, model,
    )

    for batch_start in range(0, len(items), batch_size):
        batch = items[batch_start: batch_start + batch_size]
        titles = [item.title for item in batch]

        logger.info(
            "Batch %d-%d işleniyor (%d başlık)...",
            batch_start + 1, batch_start + len(batch), len(batch),
        )

        assigned = _categorize_batch(client, titles, model, categories, max_retries)

        for item, category in zip(batch, assigned):
            item.category = category

        # Batch'ler arası bekleme — ücretsiz katman 10 RPM = max 1 istek/6s
        # 7s bekleyerek güvenli tarafta kalıyoruz
        if batch_start + batch_size < len(items):
            time.sleep(7)

    categorized_counts: dict[str, int] = {}
    for item in items:
        categorized_counts[item.category] = categorized_counts.get(item.category, 0) + 1

    logger.info("Kategorilendirme tamamlandı: %s", categorized_counts)
    return items
