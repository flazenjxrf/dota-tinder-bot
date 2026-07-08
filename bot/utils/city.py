import re

_CITY_GROUPS: dict[str, list[str]] = {
    "Москва": [
        "москва", "мск", "msk", "moskva", "moscow", "moskwa", "maskva",
        "г москва", "г. москва", "moscow city",
    ],
    "Санкт-Петербург": [
        "санкт-петербург", "санкт петербург", "санктпетербург", "спб", "spb",
        "питер", "piter", "petrograd", "ленинград", "saint petersburg",
        "sankt-peterburg", "sankt peterburg", "st petersburg", "st. petersburg",
        "petersburg",
    ],
    "Новосибирск": ["новосибирск", "novosibirsk", "novosib"],
    "Екатеринбург": ["екатеринбург", "ekaterinburg", "yekaterinburg", "екб", "ekb"],
    "Казань": ["казань", "kazan"],
    "Нижний Новгород": ["нижний новгород", "нижний", "nizhniy novgorod", "nizhny novgorod", "nn"],
    "Челябинск": ["челябинск", "chelyabinsk"],
    "Самара": ["самара", "samara"],
    "Омск": ["омск", "omsk"],
    "Ростов-на-Дону": ["ростов-на-дону", "ростов на дону", "ростов", "rostov", "rostov-on-don"],
    "Уфа": ["уфа", "ufa"],
    "Красноярск": ["красноярск", "krasnoyarsk"],
    "Воронеж": ["воронеж", "voronezh"],
    "Пермь": ["пермь", "perm"],
    "Волгоград": ["волгоград", "volgograd"],
    "Краснодар": ["краснодар", "krasnodar"],
    "Саратов": ["саратов", "saratov"],
    "Тюмень": ["тюмень", "tyumen"],
    "Тольятти": ["тольятти", "togliatti", "tolyatti"],
    "Ижевск": ["ижевск", "izhevsk"],
    "Барнаул": ["барнаул", "barnaul"],
}


def _city_key(city: str) -> str:
    normalized = city.strip().lower().replace("ё", "е")
    normalized = re.sub(r"[\s\-_.]+", "", normalized)
    return normalized


_CITY_ALIASES: dict[str, str] = {}
for canonical, variants in _CITY_GROUPS.items():
    _CITY_ALIASES[_city_key(canonical)] = canonical
    for variant in variants:
        _CITY_ALIASES[_city_key(variant)] = canonical


def _title_unknown(city: str) -> str:
    parts = re.split(r"([\s\-]+)", city.strip())
    return "".join(part.capitalize() if not re.match(r"[\s\-]+", part) else part for part in parts)


def normalize_city(city: str | None) -> str | None:
    """Приводит город к каноническому виду для сравнения в БД."""
    if not city or not city.strip():
        return None

    raw = city.strip()
    key = _city_key(raw)
    if key in _CITY_ALIASES:
        return _CITY_ALIASES[key]

    return _title_unknown(raw)


def get_normalized_city(city: str | None, normalized_city: str | None = None) -> str | None:
    """Возвращает normalized_city из БД или вычисляет его из city."""
    if normalized_city and normalized_city.strip():
        return normalized_city.strip()
    return normalize_city(city)
