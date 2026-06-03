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

st.image("banner.jpg", width="stretch")
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
        # Telefon bywa wczytywany jako float (np. 733404212.0) — wymuś string bez .0
        if "telefon" in df.columns:
            df["telefon"] = df["telefon"].apply(
                lambda v: str(int(v)) if isinstance(v, float) and not pd.isna(v) else str(v) if pd.notna(v) else ""
            )
        return df[COLUMNS]
    except Exception:
        return pd.DataFrame(columns=COLUMNS)


def save_data(df: pd.DataFrame) -> None:
    """Zapisz DataFrame do arkusza 'Dane'."""
    conn.update(worksheet="Dane", data=df)


def _render_legenda():
    with st.expander("ℹ️ Legenda kodów"):
        st.write("**Kluby (18 kart każdy, kod1–kod18):**")
        st.write(" • ".join(f"`{c}` {n}" for c, n in CLUBS.items()))
        st.write("**Zestawy specjalne:**")
        for code, (name, count) in SPECIAL_SETS.items():
            st.write(f"- `{code}1`–`{code}{count}` — {name}")


def _render_jak_korzystac():
    with st.expander("📖 Jak korzystać z aplikacji?"):
        st.markdown("""
**1. Rejestracja (nowy użytkownik)**
- Wybierz **„— Nowy użytkownik —”** z listy na górze.
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
- Kliknij **„Zapisz moje karty/profil ✨”**, żeby zapisać zmiany.

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

CLUB_CHOICES = {f"{code} — {name} (18 kart)": code for code, name in CLUBS.items()}
SPECIAL_CHOICES = {
    f"{code} — {name} ({count} kart)": (code, count)
    for code, (name, count) in SPECIAL_SETS.items()
}


def picker(key_prefix: str) -> tuple[list[str], set[str]]:
    """Widget wyboru kart. Zwraca (wybrane karty, zbiór edytowanych prefixów klubów/setów).

    Każdy klub i zestaw specjalny renderowany jest jako osobny expander z multiselect numerów.
    Brak globalnego selektora klubów (powodował problem z popoverem 'No results').
    """
    chosen: list[str] = []
    edited_prefixes: set[str] = set()

    with st.expander("⚽ Kluby", expanded=True):
        for code, name in CLUBS.items():
            opts = [f"{code}{i}" for i in range(1, 19)]
            picked = st.multiselect(
                f"{code} — {name} (1–18)",
                options=opts,
                key=f"{key_prefix}_{code}",
                placeholder="Wybierz numery...",
            )
            if picked:
                edited_prefixes.add(code)
                chosen.extend(picked)

    with st.expander("✨ Zestawy specjalne (Gold, FWC, Jewel, Fans)"):
        for code, (name, count) in SPECIAL_SETS.items():
            opts = [f"{code}{i}" for i in range(1, count + 1)]
            picked = st.multiselect(
                f"{code} — {name} ({count} kart)",
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

# Odtwórz sesję z query_params po refreshu (wcześniej, żeby dodać usera do opcji jeśli sheet jest stale)
_sessions = _get_session_store()
_qp = st.query_params
_session_token = _qp.get("s", "")
_remembered_user = _sessions.get(_session_token, "") if _session_token else ""

# Jeśli zapamiętany user (z sesji) nie jest jeszcze w świeżo odczytanym arkuszu
# (np. tuż po zapisie — gsheets bywa eventually-consistent), wymuś jego obecność w liście.
if _remembered_user and _remembered_user not in existing_ids:
    existing_ids.append(_remembered_user)
    existing_ids.sort()
user_options = ["— Nowy użytkownik —"] + existing_ids

_header_col, _logout_col = st.columns([8, 1])
with _header_col:
    st.header("1. Wprowadź swoje dane")
with _logout_col:
    if _remembered_user:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔓 Wyloguj", key="logout_btn", width="stretch"):
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

# Po zapisie: ustaw selectbox na nowego usera (przed renderowaniem widgeta)
_pending_user = st.session_state.pop("_pending_user_select", None)
if _pending_user and _pending_user in user_options:
    st.session_state["user_select"] = _pending_user
    default_idx = user_options.index(_pending_user)
elif _remembered_user and _remembered_user in user_options:
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
    row_match = existing[existing["user"] == wybor]
    if row_match.empty:
        # Wiersz jeszcze niewidoczny w arkuszu (stale read po zapisie) — użyj danych z session_state / flash.
        # Fallback: spróbuj odtworzyć z poprzednio załadowanych danych.
        row = None
        _name = wybor
        _klasa_default = st.session_state.get("user_class", "1a")
        _klasa = _klasa_default if _klasa_default in KLASY else "1a"
        _telefon = st.session_state.get("user_phone", "")
        loaded_user = {
            "user": _name,
            "imie": _name.rsplit(" (", 1)[0] if " (" in _name else _name,
            "klasa": _klasa,
            "telefon": _telefon,
            "pin_hash": st.session_state.get("_pin_hash_cached", ""),
        }
    else:
        row = row_match.iloc[0]
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
        st.session_state["_pin_hash_cached"] = loaded_user["pin_hash"]
        # Nadpisz danymi z cache jeśli są świeższe (gsheets bywa eventually-consistent)
        if "_telefon_cached" in st.session_state:
            loaded_user["telefon"] = st.session_state.pop("_telefon_cached")
        if "_imie_cached" in st.session_state:
            loaded_user["imie"] = st.session_state.pop("_imie_cached")
        if "_klasa_cached" in st.session_state:
            loaded_user["klasa"] = st.session_state.pop("_klasa_cached")

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
        if row is not None:
            loaded_user["potrzebne"] = parse_cards(row.get("potrzebne", ""))
            loaded_user["powtorki"] = parse_cards(row.get("powtorki", ""))
            st.session_state["_potrzebne_cached"] = loaded_user["potrzebne"]
            st.session_state["_powtorki_cached"] = loaded_user["powtorki"]
        else:
            # Stale read — użyj ostatnio załadowanych danych z session_state.
            loaded_user["potrzebne"] = st.session_state.get("_potrzebne_cached", [])
            loaded_user["powtorki"] = st.session_state.get("_powtorki_cached", [])
    else:
        pin = st.text_input("PIN (6 cyfr)", max_chars=6, type="password", key="user_pin")

        pin_ok = False
        if pin and len(pin) == 6 and pin.isdigit():
            if saved_hash and saved_hash != "nan" and saved_hash == hash_pin(pin):
                pin_ok = True
                loaded_user["potrzebne"] = parse_cards(row.get("potrzebne", "")) if row is not None else []
                loaded_user["powtorki"] = parse_cards(row.get("powtorki", "")) if row is not None else []
                st.session_state["_potrzebne_cached"] = loaded_user["potrzebne"]
                st.session_state["_powtorki_cached"] = loaded_user["powtorki"]
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

            # Ustaw numery kart per klub/set (sortuj numerycznie po sufiksie)
            for code, code_cards in by_prefix.items():
                st.session_state[f"{prefix}_{code}"] = sorted(
                    code_cards, key=lambda c: int(c[len(code):]) if c[len(code):].isdigit() else 0
                )

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
        st.dataframe(podsumowanie, width="stretch", hide_index=True)
    else:
        st.info("Nikt jeszcze nie dodał swoich kart.")
    _render_legenda()
    _render_jak_korzystac()
    st.stop()

# ---- Wyświetl zapisane karty + picker do edycji ----
col1, col2 = st.columns(2)
with col1:
    st.subheader("🔎  Brakujące karty (Czego szukasz)")
    saved_potrzebne = loaded_user.get("potrzebne", [])
    nowe_potrzebne, edited_need = picker("need")
    potrzebne = merge_cards(saved_potrzebne, nowe_potrzebne, edited_need)

with col2:
    st.subheader("🔁  Powtórki (Co masz do oddania)")
    saved_powtorki = loaded_user.get("powtorki", [])
    nowe_powtorki, edited_have = picker("have")
    powtorki = merge_cards(saved_powtorki, nowe_powtorki, edited_have)

# Pokaż przycisk jeśli zmieniono karty lub dane profilu (np. telefon)
karty_zmienione = bool(edited_need) or bool(edited_have)
if is_existing:
    profil_zmieniony = (
        imie != loaded_user.get("imie", "")
        or klasa != loaded_user.get("klasa", "1a")
        or (telefon or "") != (loaded_user.get("telefon", "") or "")
    )
else:
    # Dla nowego użytkownika sam formularz danych jest częścią zapisu.
    profil_zmieniony = True

mozna_zapisac = karty_zmienione or profil_zmieniony
if mozna_zapisac:
    _, col_btn, _ = st.columns([1, 2, 1])
    with col_btn:
        save_clicked = st.button("Zapisz moje karty/profil ✨", type="primary", width="stretch")
        # Pokaż komunikat sukcesu tuż pod przyciskiem (po rerun)
        _flash = st.session_state.pop("_flash_success", None)
        if _flash:
            st.success(_flash)
            st.toast(_flash, icon="✨")
else:
    save_clicked = False
    # Obsłuż flash również gdy przycisk jest ukryty (edge case)
    _flash = st.session_state.pop("_flash_success", None)
    if _flash:
        st.toast(_flash, icon="✨")

if save_clicked:
    # Dla istniejących użytkowników PIN jest już zweryfikowany (pin_ok=True),
    # więc używamy hashu zapisanego na koncie. Dla nowych — bierzemy z formularza.
    if is_existing and pin_ok:
        pin_hash_to_save = loaded_user.get("pin_hash", "") or hash_pin(st.session_state.get("user_pin", ""))
        pin_valid = True
    else:
        pin_valid = bool(pin) and len(pin) == 6 and pin.isdigit()
        pin_hash_to_save = hash_pin(pin) if pin_valid else ""

    if not imie:
        st.error("Podaj swoje imię!")
    elif not pin_valid:
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

        if not existing_row.empty and not is_existing:
            # Edycja przez nowy formularz — sprawdź PIN
            saved_hash = str(existing_row.iloc[0].get("pin_hash", ""))
            if saved_hash and saved_hash != "nan" and saved_hash != pin_hash_to_save:
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
            "pin_hash": pin_hash_to_save,
        }])
        # Jeśli zmieniono imię/klasę istniejącego użytkownika — usuń stary wpis pod poprzednią nazwą
        if is_existing and wybor and wybor != user:
            df = df[df["user"] != wybor]

        df = pd.concat([df, new_row], ignore_index=True)
        save_data(df)

        # Wymuś inwalidację cache gsheets, żeby następny load_data() zobaczył świeże dane.
        try:
            conn.reset()
        except Exception:
            pass

        # Zapamiętaj świeżo zapisane dane w session_state — fallback gdyby kolejny read
        # był jeszcze stale (gsheets bywa eventually-consistent).
        st.session_state["_potrzebne_cached"] = sorted(set(potrzebne))
        st.session_state["_powtorki_cached"] = sorted(set(powtorki))
        st.session_state["_pin_hash_cached"] = pin_hash_to_save
        st.session_state["_telefon_cached"] = telefon
        st.session_state["_imie_cached"] = imie
        st.session_state["_klasa_cached"] = klasa
        # Token zapisany w URL musi wskazywać aktualny `user`, a selectbox musi go pokazywać.
        if is_existing:
            if _session_token:
                _sessions[_session_token] = user
            else:
                _new_token = str(uuid.uuid4())
                _sessions[_new_token] = user
                st.query_params["s"] = _new_token
        else:
            # Nowy użytkownik — załóż sesję, żeby od razu był zalogowany
            _new_token = str(uuid.uuid4())
            _sessions[_new_token] = user
            st.query_params["s"] = _new_token

        st.session_state["_pending_user_select"] = user
        st.session_state["_loaded_user"] = user

        st.session_state["_flash_success"] = "Zapisano!"
        st.rerun()

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
    st.dataframe(podsumowanie, width="stretch", hide_index=True)
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

_render_legenda()
_render_jak_korzystac()
