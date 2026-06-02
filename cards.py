"""Definicje zestawu Panini FIFA 365 Adrenalyn XL 2026."""

# Kod 3-literowy -> pełna nazwa klubu. Każdy klub ma 18 kart (CODE1..CODE18).
CLUBS: dict[str, str] = {
    "BOT": "Botafogo",
    "LIV": "Liverpool FC",
    "OLM": "Olympique de Marseille",
    "PAS": "Paris Saint-Germain",
    "BLE": "Bayer 04 Leverkusen",
    "EIN": "Eintracht Frankfurt",
    "OLY": "Olympiacos FC",
    "INT": "FC Internazionale Milano",
    "MIL": "AC Milan",
    "AJA": "AFC Ajax",
    "PSV": "PSV Eindhoven",
    "SPO": "Sporting CP",
    "NAS": "Al-Nassr FC",
    "ATM": "Atlético de Madrid",
    "BAR": "FC Barcelona",
    "RMA": "Real Madrid CF",
}

# Zestawy specjalne: kod -> (nazwa, liczba kart)
SPECIAL_SETS: dict[str, tuple[str, int]] = {
    "GOL": ("Gold (Golden Ballers / Invincible)", 9),
    "FWC": ("Road to FIFA World Cup 26", 36),
    "JWL": ("Jewel (Elite Cut)", 18),
    "FAN": ("Fans' Favourites & Legends", 100),
}


def all_card_codes() -> list[str]:
    """Wszystkie kody kart w kolejności: kluby alfabetycznie, potem zestawy specjalne."""
    codes: list[str] = []
    for code in CLUBS:
        codes.extend(f"{code}{i}" for i in range(1, 19))
    for code, (_, count) in SPECIAL_SETS.items():
        codes.extend(f"{code}{i}" for i in range(1, count + 1))
    return codes


def card_label(code: str) -> str:
    """Zwraca opisową etykietę karty, np. 'AJA1 — AFC Ajax'."""
    for prefix, name in CLUBS.items():
        if code.startswith(prefix) and code[len(prefix):].isdigit():
            return f"{code} — {name}"
    for prefix, (name, _) in SPECIAL_SETS.items():
        if code.startswith(prefix) and code[len(prefix):].isdigit():
            return f"{code} — {name}"
    return code
