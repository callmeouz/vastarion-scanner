def tr_lower(text: str) -> str:
    """Turkce buyuk-kucuk harf donusumu. I->i, İ->i kuralini uygular."""
    if not text:
        return ""
    text = text.replace('I', 'ı').replace('İ', 'i')
    return text.lower()


def normalize_turkish(text: str) -> str:
    """
    Turkce karakterleri ASCII karsiliklarina cevirir.
    Arama sirasinda case-insensitive ve aksansiz eslesme saglar.
    """
    if not text:
        return ""
    replacements = {
        'ı': 'i', 'İ': 'i', 'I': 'i',
        'ğ': 'g', 'Ğ': 'g',
        'ü': 'u', 'Ü': 'u',
        'ş': 's', 'Ş': 's',
        'ö': 'o', 'Ö': 'o',
        'ç': 'c', 'Ç': 'c',
    }
    text = text.lower()
    for tr_char, eng_char in replacements.items():
        text = text.replace(tr_char, eng_char)
    return text


def get_preview_snippet(content: str, keyword: str, context_length: int = 40) -> str:
    """Icerik icinde aranan kelimenin etrafindaki metni dondurur."""
    if not content or not keyword:
        return ""
    content_lower = normalize_turkish(content)
    keyword_lower = normalize_turkish(keyword)

    idx = content_lower.find(keyword_lower)
    if idx == -1:
        return content[:context_length * 2] + "..."

    start = max(0, idx - context_length)
    end = min(len(content), idx + len(keyword) + context_length)

    snippet = content[start:end].replace('\n', ' ').strip()
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(content) else ""
    return f"{prefix}{snippet}{suffix}"
