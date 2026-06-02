import hashlib
import uuid
from collections import defaultdict

import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection

from cards import CLUBS, SPECIAL_SETS, card_label


@st.cache_resource
def _get_session_store() -> dict:
    """Server-side store: {token: username}. Przetrwa reruns i refreshe."""
    return {}


def hash_pin(pin: str) -> str:
    """Zwraca SHA-256 hash PINu."""
    return hashlib.sha256(pin.encode()).hexdigest()

st.set_page_config(page_title="Wymiana Kart FIFA 2026", layout="wide")

# Tłumaczenie wbudowanych tekstów Streamlit na polski
st.markdown("""
<style>
    /* "Select all" → "Zaznacz wszystko" */
    div[data-testid="stMultiSelect"] span[data-testid="InputInstructions"] {
        visibility: hidden;
    }
    div[data-testid="stMultiSelect"] span[data-testid="InputInstructions"]::after {
        content: "Zaznacz wszystko";
        visibility: visible;
    }
    /* Większy nagłówek expanderów */
    div[data-testid="stExpander"] summary p {
        font-size: 1.2rem !important;
    }
    /* Kolor nazwy użytkownika w expanderze */
    div[data-testid="stExpander"] summary strong {
        color: #09AB3B !important;
    }
    /* Niebieski przycisk primary z białym tekstem */
    button[kind="primary"], button[data-testid="stBaseButton-primary"] {
        background-color: #1E88E5 !important;
        border-color: #1E88E5 !important;
        color: #FFFFFF !important;
        font-size: 1.1rem !important;
        padding: 0.6rem 1.5rem !important;
    }
    button[kind="primary"] p, button[data-testid="stBaseButton-primary"] p {
        color: #FFFFFF !important;
        font-size: 1.1rem !important;
    }
    /* Czarny tekst w zaznaczonych tagach multiselect */
    span[data-baseweb="tag"] {
        background-color: #FFD700 !important;
        color: #000000 !important;
    }
    span[data-baseweb="tag"] span {
        color: #000000 !important;
    }
</style>
""", unsafe_allow_html=True)

st.image("banner.jpg", use_container_width=True)
st.title("⚽ System Wymiany Kart Panini FIFA 365 Adrenalyn XL 2026")

# --------------- Google Sheets backend ---------------
conn = st.connection("gsheets", type=GSheetsConnection)

COLUMNS = ["user", "klasa", "telefon", "potrzebne", "powtorki", "pin_hash"]


def load_data() -> pd.DataFrame:
    """Wczytaj dane z Google Sheets. Zwraca DataFrame z kolumnami COLUMNS."""
    try:
        df = conn.read(worksheet="Dane", ttl=0)
        if df is None or df.empty:
            return pd.DataFrame(columns=COLUMNS)
        # Odfiltruj puste wiersze
        df = df.dropna(subset=["user"])
        return df[COLUMNS]
    except Exception:
        return pd.DataFrame(columns=COLUMNS)


def save_data(df: pd.DataFrame) -> None:
    """Zapisz DataFrame do arkusza 'Dane'."""
    conn.update(worksheet="Dane", data=df)

CLUB_CHOICES = {f"{code} — {name} (18 kart)": code for code, name in CLUBS.items()}
SPECIAL_CHOICES = {
    f"{code} — {name} ({count} kart)": (code, count)
    for code, (name, count) in SPECIAL_SETS.items()
}


def picker(key_prefix: str) -> tuple[list[str], set[str]]:
    """Widget wyboru kart. Zwraca (wybrane karty, zbiór edytowanych prefixów klubów/setów)."""
    chosen: list[str] = []
    edited_prefixes: set[str] = set()

    club_labels = st.multiselect(
        "Wybierz kluby",
        options=list(CLUB_CHOICES.keys()),
        key=f"{key_prefix}_clubs",
        placeholder="Wybierz...",
    )
    for club_label_text in club_labels:
        code = CLUB_CHOICES[club_label_text]
        edited_prefixes.add(code)
        opts = [f"{code}{i}" for i in range(1, 19)]
        picked = st.multiselect(
            f"{code} — numery (1–18)",
            options=opts,
            key=f"{key_prefix}_{code}",
            placeholder="Wybierz numery...",
        )
        chosen.extend(picked)

    with st.expander("Zestawy specjalne (Gold, FWC, Jewel, Fans)"):
        for label_text, (code, count) in SPECIAL_CHOICES.items():
            opts = [f"{code}{i}" for i in range(1, count + 1)]
            picked = st.multiselect(
                label_text,
                options=opts,
                key=f"{key_prefix}_{code}",
                placeholder="Wybierz numery...",
            )
            if picked:
                edited_prefixes.add(code)
            chosen.extend(picked)

    return chosen, edited_prefixes


def merge_cards(saved: list[str], new: list[str], edited_prefixes: set[str]) -> list[str]:
    """Połącz stare karty z nowymi — nadpisz tylko edytowane kluby/sety."""
    if not edited_prefixes:
        return saved
    # Zachowaj stare karty z niedotkniętych prefixów
    kept = [c for c in saved if not any(c.startswith(p) for p in edited_prefixes)]
    # Dodaj nowe z edytowanych prefixów
    return sorted(set(kept + new))


KLASY = [f"{r}{l}" for r in range(1, 9) for l in "abc"]


def parse_cards(s: str) -> list[str]:
    """Zamień ciąg 'AJA1,AJA2' na listę; pusty/NaN → pusta lista."""
    if not isinstance(s, str) or not s.strip():
        return []
    return [c.strip() for c in s.split(",") if c.strip()]


# ---- Wczytaj istniejących użytkowników ----
existing = load_data()
if not existing.empty:
    existing_ids = sorted(existing["user"].tolist())
else:
    existing_ids = []
user_options = ["— Nowy użytkownik —"] + existing_ids

# Odtwórz sesję z query_params po refreshu
_sessions = _get_session_store()
_qp = st.query_params
_session_token = _qp.get("s", "")
_remembered_user = _sessions.get(_session_token, "") if _session_token else ""

_header_col, _logout_col = st.columns([4, 1])
with _header_col:
    st.header("1. Wprowadź swoje dane")
with _logout_col:
    if _remembered_user:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔓 Wyloguj", key="logout_btn"):
            _sessions.pop(_session_token, None)
            st.query_params.clear()
            # Wyczyść dane użytkownika z session state
            st.session_state["user_name"] = ""
            st.session_state["user_phone"] = ""
            st.session_state["_loaded_user"] = ""
            st.session_state["user_select"] = "— Nowy użytkownik —"
            # Wyczyść pickery
            for key in list(st.session_state.keys()):
                if key.startswith("need_") or key.startswith("have_"):
                    del st.session_state[key]
            st.rerun()

# Jeśli zapamiętany user istnieje — ustaw go jako domyślny w selectbox
default_idx = 0
if _remembered_user and _remembered_user in user_options:
    default_idx = user_options.index(_remembered_user)

wybor = st.selectbox("Wybierz siebie z listy lub dodaj się jako nowy:", options=user_options, index=default_idx, key="user_select")

# Wczytaj dane jeśli wybrano istniejącego użytkownika
loaded_user = {}
is_existing = wybor != "— Nowy użytkownik —"

# Wyczyść pola formularza jeśli user zmienił wybór
_prev_loaded = st.session_state.get("_loaded_user", "")
if _prev_loaded and _prev_loaded != wybor:
    # Wyczyść dane poprzedniego usera
    st.session_state["user_name"] = ""
    st.session_state["user_phone"] = ""
    st.session_state["_loaded_user"] = ""
    for key in list(st.session_state.keys()):
        if key.startswith("need_") or key.startswith("have_"):
            del st.session_state[key]

# Wyczyść sesję jeśli user zmienił wybór
if _remembered_user and _remembered_user != wybor:
    _sessions.pop(_session_token, None)
    st.query_params.clear()
    _remembered_user = ""
    _session_token = ""

if is_existing:
    row = existing[existing["user"] == wybor].iloc[0]
    _name = str(row["user"])
    _klasa = str(row.get("klasa", "1a"))
    _telefon = str(row.get("telefon", ""))
    loaded_user = {
        "user": _name,
        "imie": _name.rsplit(" (", 1)[0] if " (" in _name else _name,
        "klasa": _klasa,
        "telefon": _telefon if _telefon != "nan" else "",
        "pin_hash": str(row.get("pin_hash", "")),
    }

# Dla istniejących: najpierw PIN, potem reszta
# Dla nowych: wszystko od razu
if is_existing:
    saved_hash = loaded_user.get("pin_hash", "")

    # Sprawdź czy mamy ważną sesję z query_params (po refreshu)
    auto_login = (
        _remembered_user == wybor
        and bool(_session_token)
    )

    if auto_login:
        pin_ok = True
        loaded_user["potrzebne"] = parse_cards(row.get("potrzebne", ""))
        loaded_user["powtorki"] = parse_cards(row.get("powtorki", ""))
    else:
        pin = st.text_input("PIN (6 cyfr)", max_chars=6, type="password", key="user_pin")

        pin_ok = False
        if pin and len(pin) == 6 and pin.isdigit():
            if saved_hash and saved_hash != "nan" and saved_hash == hash_pin(pin):
                pin_ok = True
                loaded_user["potrzebne"] = parse_cards(row.get("potrzebne", ""))
                loaded_user["powtorki"] = parse_cards(row.get("powtorki", ""))
                # Zapamiętaj sesję w URL (losowy token, nie hash)
                _new_token = str(uuid.uuid4())
                _sessions[_new_token] = wybor
                st.query_params["s"] = _new_token
                st.rerun()
            else:
                st.warning("🔒 Błędny PIN.")
                st.stop()
        else:
            st.info("🔑 Podaj swój 6-cyfrowy PIN, żeby wczytać i edytować swoje karty.")
            st.stop()

    # PIN OK — pokaż dane do edycji
    # Wymuś wartości w session state (nadpisuje puste z pierwszego renderu)
    if "user_name" not in st.session_state or st.session_state.get("_loaded_user") != wybor:
        st.session_state["user_name"] = loaded_user.get("imie", "")
        st.session_state["user_phone"] = loaded_user.get("telefon", "")
        st.session_state["_loaded_user"] = wybor

        # Załaduj zapisane karty do pickerów
        for prefix, cards in [("need", loaded_user.get("potrzebne", [])), ("have", loaded_user.get("powtorki", []))]:
            # Pogrupuj karty po prefiksie klubu/setu
            by_prefix = defaultdict(list)
            all_codes = set(CLUBS.keys()) | set(SPECIAL_SETS.keys())
            for card in cards:
                for code in sorted(all_codes, key=len, reverse=True):
                    if card.startswith(code):
                        by_prefix[code].append(card)
                        break

            # Ustaw kluby w multiselect
            club_labels = []
            for code in by_prefix:
                if code in CLUBS:
                    label = f"{code} — {CLUBS[code]} (18 kart)"
                    club_labels.append(label)
            if club_labels:
                st.session_state[f"{prefix}_clubs"] = club_labels

            # Ustaw numery kart per klub/set
            for code, code_cards in by_prefix.items():
                st.session_state[f"{prefix}_{code}"] = sorted(code_cards)

    col_name, col_class, col_phone = st.columns([3, 1, 2])
    with col_name:
        imie = st.text_input("Twoje Imię", key="user_name")
    with col_class:
        default_klasa = loaded_user.get("klasa", "1a")
        klasa_idx = KLASY.index(default_klasa) if default_klasa in KLASY else 0
        klasa = st.selectbox("Klasa", options=KLASY, index=klasa_idx, key="user_class")
    with col_phone:
        telefon = st.text_input("Nr telefonu / WhatsApp", key="user_phone")
else:
    pin_ok = False
    col_name, col_class, col_phone, col_pin = st.columns([3, 1, 2, 1])
    with col_name:
        imie = st.text_input("Twoje Imię", key="user_name")
    with col_class:
        klasa = st.selectbox("Klasa", options=KLASY, key="user_class")
    with col_phone:
        telefon = st.text_input("Nr telefonu / WhatsApp", key="user_phone")
    with col_pin:
        pin = st.text_input("PIN (6 cyfr)", max_chars=6, type="password", key="user_pin")

# Unikalny identyfikator: "Imię (klasa)"
user = f"{imie} ({klasa})" if imie else ""

# Dla nowych: pokaż sekcje kart dopiero po wpisaniu danych
if not is_existing and not imie:
    st.info("👆 Wpisz swoje imię, klasę, telefon i PIN, aby dodać karty.")
    st.divider()
    # Pokaż tabelę graczy nawet bez logowania
    dane = load_data()
    st.header("👥 Gracze w bazie")
    if not dane.empty:
        podsumowanie = pd.DataFrame([
            {
                "Gracz": str(row["user"]).rsplit(" (", 1)[0] if " (" in str(row["user"]) else row["user"],
                "Klasa": row.get("klasa", "—"),
                "WhatsApp": row.get("telefon", "—"),
                "Szuka (#)": len(parse_cards(row["potrzebne"])),
                "Ma na oddanie (#)": len(parse_cards(row["powtorki"])),
            }
            for _, row in dane.iterrows()
        ])
        st.dataframe(podsumowanie, use_container_width=True, hide_index=True)
    else:
        st.info("Nikt jeszcze nie dodał swoich kart.")
    st.stop()

# ---- Wyświetl zapisane karty + picker do edycji ----
col1, col2 = st.columns(2)
with col1:
    st.subheader("🔎 Brakujące karty (Czego szukasz?)")
    saved_potrzebne = loaded_user.get("potrzebne", [])
    if saved_potrzebne:
        st.caption(f"Zapisane ({len(saved_potrzebne)}): {', '.join(sorted(saved_potrzebne))}")
    st.caption("Dodaj/zmień karty poniżej:")
    nowe_potrzebne, edited_need = picker("need")
    potrzebne = merge_cards(saved_potrzebne, nowe_potrzebne, edited_need)

with col2:
    st.subheader("🔁 Powtórki (Co masz na oddanie?)")
    saved_powtorki = loaded_user.get("powtorki", [])
    if saved_powtorki:
        st.caption(f"Zapisane ({len(saved_powtorki)}): {', '.join(sorted(saved_powtorki))}")
    st.caption("Dodaj/zmień karty poniżej:")
    nowe_powtorki, edited_have = picker("have")
    powtorki = merge_cards(saved_powtorki, nowe_powtorki, edited_have)

# Pokaż przycisk tylko jeśli zmieniono karty
karty_zmienione = bool(edited_need) or bool(edited_have)
if karty_zmienione:
    _, col_btn, _ = st.columns([1, 2, 1])
    with col_btn:
        save_clicked = st.button("Zapisz moje karty ✨", type="primary", use_container_width=True)
else:
    save_clicked = False

if save_clicked:
    if not imie:
        st.error("Podaj swoje imię!")
    elif not pin or len(pin) != 6 or not pin.isdigit():
        st.error("PIN musi mieć dokładnie 6 cyfr!")
    else:
        df = load_data()
        existing_row = df[df["user"] == user]

        # Nowy użytkownik z takim samym Imię (klasa) już istnieje
        if not existing_row.empty and wybor == "— Nowy użytkownik —":
            # Zasugeruj wolne imię
            n = 2
            while not df[df["user"] == f"{imie}{n} ({klasa})"].empty:
                n += 1
            sugestia = f"{imie}{n}"
            st.error(
                f"⚠️ Użytkownik **{user}** już istnieje! "
                f"Jeśli to Ty — wybierz siebie z listy powyżej i podaj PIN. "
                f"Jeśli to ktoś inny — użyj np. **{sugestia}** jako imię."
            )
            st.stop()

        if not existing_row.empty:
            # Użytkownik istnieje — sprawdź PIN
            saved_hash = str(existing_row.iloc[0].get("pin_hash", ""))
            if saved_hash and saved_hash != "nan" and saved_hash != hash_pin(pin):
                st.error("❌ Błędny PIN! Nie możesz edytować danych innego użytkownika.")
                st.stop()
        # PIN OK lub nowy użytkownik
        df = df[df["user"] != user]
        new_row = pd.DataFrame([{
            "user": user,
            "klasa": klasa,
            "telefon": telefon,
            "potrzebne": ",".join(sorted(set(potrzebne))),
            "powtorki": ",".join(sorted(set(powtorki))),
            "pin_hash": hash_pin(pin),
        }])
        df = pd.concat([df, new_row], ignore_index=True)
        save_data(df)

        def _kart(n: int) -> str:
            if n == 1:
                return "1 kartę"
            elif 2 <= n <= 4:
                return f"{n} karty"
            return f"{n} kart"

        st.success(f"Zapisano! Szukasz: {_kart(len(potrzebne))}, oddasz: {_kart(len(powtorki))}.")

st.divider()

# Załaduj aktualne dane z arkusza (odśwież po ewentualnym zapisie)
dane = load_data()


st.header("👥 Gracze w bazie")
if not dane.empty:
    podsumowanie = pd.DataFrame([
        {
            "Gracz": str(row["user"]).rsplit(" (", 1)[0] if " (" in str(row["user"]) else row["user"],
            "Klasa": row.get("klasa", "—"),
            "WhatsApp": row.get("telefon", "—"),
            "Szuka (#)": len(parse_cards(row["potrzebne"])),
            "Ma na oddanie (#)": len(parse_cards(row["powtorki"])),
        }
        for _, row in dane.iterrows()
    ])
    st.dataframe(podsumowanie, use_container_width=True, hide_index=True)
else:
    st.info("Nikt jeszcze nie dodał swoich kart.")

st.header("🤝 Propozycje idealnych wymian")
if user:
    my_row = dane[dane["user"] == user] if not dane.empty else pd.DataFrame()
    if my_row.empty and is_existing and wybor:
        my_row = dane[dane["user"] == wybor] if not dane.empty else pd.DataFrame()
    if not my_row.empty and len(dane) > 1:
        me = my_row.iloc[0]
        my_powtorki = set(parse_cards(me["powtorki"]))
        my_potrzebne = set(parse_cards(me["potrzebne"]))
        dopasowania = []
        for _, other in dane.iterrows():
            if other["user"] == me["user"]:
                continue
            other_powtorki = set(parse_cards(other["powtorki"]))
            other_potrzebne = set(parse_cards(other["potrzebne"]))

            dla_other = sorted(my_powtorki & other_potrzebne)
            dla_mnie = sorted(other_powtorki & my_potrzebne)
            if dla_other or dla_mnie:
                dopasowania.append({
                    "gracz": other["user"],
                    "whatsapp": other.get("telefon", "—"),
                    "dla_mnie": dla_mnie,
                    "dla_other": dla_other,
                })

        if dopasowania:
            # Sortuj: najpierw obustronne, potem po łącznej liczbie kart
            dopasowania.sort(key=lambda d: (
                bool(d["dla_mnie"]) and bool(d["dla_other"]),  # obustronne na górze
                len(d["dla_mnie"]) + len(d["dla_other"]),
            ), reverse=True)

            for d in dopasowania:
                obustronna = bool(d["dla_mnie"]) and bool(d["dla_other"])
                typ = "🔄 Wymiana obustronna" if obustronna else ("📥 Możesz dostać" if d["dla_mnie"] else "📤 Możesz oddać")
                wa = d['whatsapp']
                wa_str = f" | 📱 {wa}" if wa and wa != "—" else ""
                with st.expander(
                    f"{typ} z **{d['gracz']}**{wa_str} — "
                    f"dostaniesz {len(d['dla_mnie'])} / oddasz {len(d['dla_other'])} kart",
                    expanded=obustronna,
                ):
                    col_get, col_give = st.columns(2)
                    with col_get:
                        if d["dla_mnie"]:
                            st.success(f"📥 **Dostaniesz ({len(d['dla_mnie'])} kart):**")
                            st.write(", ".join(f"`{c}`" for c in d["dla_mnie"]))
                        else:
                            st.info("📥 Nic do odebrania")
                    with col_give:
                        if d["dla_other"]:
                            st.warning(f"📤 **Oddasz ({len(d['dla_other'])} kart):**")
                            st.write(", ".join(f"`{c}`" for c in d["dla_other"]))
                        else:
                            st.info("📤 Nic do oddania")
        else:
            st.info("Brak pasujących wymian w tym momencie.")
    elif my_row.empty:
        st.info("Zapisz swoje karty, aby zobaczyć propozycje wymian.")
    else:
        st.info("Jesteś jedynym graczem w bazie. Czekam na więcej osób!")
else:
    st.info("Wprowadź swoje dane, aby zobaczyć propozycje wymian.")

with st.expander("ℹ️ Legenda kodów"):
    st.write("**Kluby (18 kart każdy, kod1–kod18):**")
    st.write(" • ".join(f"`{c}` {n}" for c, n in CLUBS.items()))
    st.write("**Zestawy specjalne:**")
    for code, (name, count) in SPECIAL_SETS.items():
        st.write(f"- `{code}1`–`{code}{count}` — {name}")

with st.expander("📖 Jak korzystać z aplikacji?"):
    st.markdown("""
**1. Rejestracja (nowy użytkownik)**
- Wybierz **„— Nowy użytkownik —"** z listy na górze.
- Wpisz swoje **imię**, wybierz **klasę**, podaj **numer telefonu/WhatsApp** i ustaw **6-cyfrowy PIN**.
- PIN będzie potrzebny przy każdym logowaniu — zapamiętaj go!

**2. Logowanie (istniejący użytkownik)**
- Wybierz swoje imię z listy na górze.
- Wpisz swój **6-cyfrowy PIN**, żeby odblokować edycję kart.

**3. Dodawanie kart**
- W sekcji **🔎 Brakujące karty** — dodaj karty, których szukasz.
- W sekcji **🔁 Powtórki** — dodaj karty, które masz na wymianę.
- Najpierw wybierz klub (np. BAR — FC Barcelona), a potem konkretne numery kart.
- Zestawy specjalne (Gold, FWC, Jewel, Fans) znajdziesz w osobnym rozwijalnym panelu.
- Kliknij **„Zapisz moje karty ✨"**, żeby zapisać zmiany.

**4. Propozycje wymian**
- Po zapisaniu kart, na dole strony pojawią się **propozycje wymian** z innymi graczami.
- 🔄 **Wymiana obustronna** — obie strony mają coś do wymiany (najlepsze!).
- 📥 **Możesz dostać** — ktoś ma kartę, której szukasz.
- 📤 **Możesz oddać** — masz kartę, której ktoś szuka.
- Skontaktuj się przez **WhatsApp**, żeby umówić wymianę!

**5. Kody kart**
- Każda karta ma kod: np. `BAR5` = FC Barcelona, karta nr 5.
- Kody znajdziesz w sekcji **ℹ️ Legenda kodów** powyżej.
""")
