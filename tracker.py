"""
================================================================================
INTESTAZIONE:
Quant Portfolio Tracker & Comparator - Cloud & Mobile Web App (GitHub DB Edition)
Applicazione web in Streamlit ottimizzata per smartphone (Pixel 10 Pro) e desktop,
con persistenza cloud automatica tramite commit diretto su repository GitHub.

Caratteristiche principali:
1. Database su GitHub REST API: ogni modifica ai portafogli o alle transazioni
   esegue un commit automatico di 'portfolios_data.json' sul repository GitHub
   privato, eliminando il problema del disco effimero di Streamlit Cloud.
2. Responsive Mobile UI: Bento Grid CSS 2x3 per le metriche su smartphone,
   schede asset touch-friendly e layout adattivo per schermi verticali.
3. Sicurezza Cloud: blocco di accesso tramite PIN configurabile in st.secrets.
4. Motore Fiscale Italiano completo:
   - 12,5% per ETF Governativi White-List / Monetari;
   - 26,0% per ETF standard (Redditi di Capitale);
   - 26,0% per ETC/ETN/Azioni (Redditi Diversi) con compensazione automatica
     dello Zainetto Minusvalenze e accredito netto sul conto Cash.
5. Ribilanciamento a bande, compravendite estemporanee manuali, Dashboard
   Quantitativa a 12 metriche e Confronto Multi-Portafoglio (Head-to-Head).
================================================================================
"""

import os
import json
import copy
import base64
import datetime
import requests
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

# ==============================================================================
# 1. CONFIGURAZIONE PAGINA & CSS MOBILE-FIRST (PIXEL 10 PRO OPTIMIZED)
# ==============================================================================
st.set_page_config(
    page_title="Portfolio Cloud Tracker",
    page_icon="📱",
    layout="wide",
    initial_sidebar_state="collapsed"
)

MOBILE_AND_CLOUD_CSS = """
<style>
    .block-container {
        padding-top: 1.2rem !important;
        padding-bottom: 2.5rem !important;
        padding-left: 0.8rem !important;
        padding-right: 0.8rem !important;
    }
    
    /* Bento Grid Responsiva: 2 colonne su Pixel/Mobile, 3 su Tablet, 6 su Desktop */
    .bento-grid {
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 10px;
        margin-bottom: 18px;
    }
    @media (min-width: 768px) {
        .bento-grid {
            grid-template-columns: repeat(3, 1fr);
        }
    }
    @media (min-width: 1200px) {
        .bento-grid {
            grid-template-columns: repeat(6, 1fr);
        }
    }
    .bento-card {
        background: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 12px 14px;
        box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
    }
    .bento-label {
        font-size: 0.75rem;
        font-weight: 600;
        color: #64748B;
        text-transform: uppercase;
        letter-spacing: 0.03em;
        margin-bottom: 4px;
    }
    .bento-value {
        font-size: 1.22rem;
        font-weight: 800;
        color: #0F172A;
        line-height: 1.2;
    }
    .bento-sub {
        font-size: 0.78rem;
        font-weight: 600;
        margin-top: 4px;
    }
    .pos-delta { color: #16A34A; }
    .neg-delta { color: #DC2626; }
    .neu-delta { color: #475569; }

    /* Asset Card per vista mobile */
    .asset-card {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 12px 14px;
        margin-bottom: 10px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.03);
    }
    .badge-ok {
        background: #DCFCE7; color: #166534; padding: 3px 8px;
        border-radius: 6px; font-weight: 700; font-size: 0.75rem;
    }
    .badge-warn {
        background: #FEF3C7; color: #92400E; padding: 3px 8px;
        border-radius: 6px; font-weight: 700; font-size: 0.75rem;
    }
    .badge-alert {
        background: #FEE2E2; color: #991B1B; padding: 3px 8px;
        border-radius: 6px; font-weight: 700; font-size: 0.75rem;
    }

    /* Tabs scorrevoli orizzontalmente su smartphone */
    .stTabs [data-baseweb="tab-list"] {
        gap: 6px;
        overflow-x: auto;
        white-space: nowrap;
        flex-wrap: nowrap !important;
        padding-bottom: 4px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 42px;
        background-color: #F1F5F9;
        border-radius: 8px;
        font-weight: 600;
        padding: 6px 12px;
        font-size: 0.88rem;
    }
    .stTabs [aria-selected="true"] {
        background-color: #0F172A !important;
        color: #FFFFFF !important;
    }
</style>
"""
st.markdown(MOBILE_AND_CLOUD_CSS, unsafe_allow_html=True)

DATA_FILENAME = "portfolios_data.json"

# ==============================================================================
# 2. AUTENTICAZIONE PIN PER ACCESSO SICURO DA MOBILE / WEB
# ==============================================================================
def check_pin_authentication() -> bool:
    """Protegge la web app con un PIN se configurato in st.secrets['app_pin']."""
    expected_pin = None
    try:
        if "app_pin" in st.secrets:
            expected_pin = str(st.secrets["app_pin"]).strip()
    except Exception:
        pass

    if not expected_pin or st.session_state.get("authenticated", False):
        return True

    st.markdown("<h2 style='text-align:center; margin-top:2rem;'>🔒 Portfolio Cloud Lock</h2>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 1.5, 1])
    with c2:
        pin_in = st.text_input("Inserisci il PIN di sicurezza:", type="password")
        if st.button("Sblocca Applicazione", type="primary", use_container_width=True):
            if pin_in == expected_pin:
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("PIN errato.")
    return False

if not check_pin_authentication():
    st.stop()

# ==============================================================================
# 3. PERSISTENZA SU GITHUB REST API (AUTO-COMMIT) + FALLBACK LOCALE
# ==============================================================================
def get_github_config():
    """Legge i parametri GitHub da st.secrets se presenti."""
    try:
        token = st.secrets.get("github_token", "").strip()
        repo = st.secrets.get("github_repo", "").strip()
        branch = st.secrets.get("github_branch", "main").strip()
        if token and repo:
            return {"token": token, "repo": repo, "branch": branch}
    except Exception:
        pass
    return None

def get_default_portfolios() -> dict:
    """Restituisce i portafogli di base al primo avvio."""
    return {
        "P1 - Multi-Factor Core": {
            "data_inizio": "2024-01-02",
            "capitale_iniziale_versato": 50000.0,
            "cash": 3500.0,
            "tasse_totali_pagate": 0.0,
            "zainetto_minusvalenze": 0.0,
            "posizioni": [
                {"ticker": "WMOT.DE", "nome": "US Wide Moat Focus", "target": 20.0, "tolleranza": 4.0, "quote": 75, "pmc": 130.50},
                {"ticker": "SWDA.MI", "nome": "MSCI World Core", "target": 15.0, "tolleranza": 3.0, "quote": 60, "pmc": 86.20},
                {"ticker": "SXRM.DE", "nome": "Treasury 7-10 Year (Gov)", "target": 15.0, "tolleranza": 3.0, "quote": 280, "pmc": 26.50},
                {"ticker": "VVSM.DE", "nome": "VanEck Semiconductor", "target": 10.0, "tolleranza": 2.5, "quote": 45, "pmc": 115.00},
                {"ticker": "XDEQ.DE", "nome": "MSCI USA Quality", "target": 10.0, "tolleranza": 2.5, "quote": 40, "pmc": 128.00},
                {"ticker": "IS3S.DE", "nome": "MSCI USA Value", "target": 10.0, "tolleranza": 2.5, "quote": 120, "pmc": 41.50},
                {"ticker": "QDVH.DE", "nome": "Financials Sector", "target": 5.0, "tolleranza": 1.5, "quote": 35, "pmc": 72.00},
                {"ticker": "QDVF.DE", "nome": "Energy Sector", "target": 5.0, "tolleranza": 1.5, "quote": 90, "pmc": 28.50},
                {"ticker": "4GLD.DE", "nome": "Physical Gold ETC", "target": 5.0, "tolleranza": 1.5, "quote": 30, "pmc": 70.00},
                {"ticker": "DBXOAN.DE", "nome": "EUR Overnight Swap", "target": 5.0, "tolleranza": 1.5, "quote": 15, "pmc": 140.00}
            ],
            "transazioni": []
        },
        "P2 - Defensive Trend (All-Weather)": {
            "data_inizio": "2024-01-02",
            "capitale_iniziale_versato": 50000.0,
            "cash": 2200.0,
            "tasse_totali_pagate": 0.0,
            "zainetto_minusvalenze": 0.0,
            "posizioni": [
                {"ticker": "SWDA.MI", "nome": "MSCI World Core", "target": 45.0, "tolleranza": 5.0, "quote": 180, "pmc": 85.00},
                {"ticker": "QDVG.DE", "nome": "Health Care Select", "target": 15.0, "tolleranza": 3.5, "quote": 190, "pmc": 40.20},
                {"ticker": "SXRM.DE", "nome": "Treasury 7-10 Year (Gov)", "target": 10.0, "tolleranza": 2.5, "quote": 200, "pmc": 27.10},
                {"ticker": "DTLA.MI", "nome": "Treasury 20+ Year (Gov)", "target": 10.0, "tolleranza": 2.5, "quote": 240, "pmc": 21.00},
                {"ticker": "4GLD.DE", "nome": "Physical Gold ETC", "target": 10.0, "tolleranza": 2.5, "quote": 55, "pmc": 68.50},
                {"ticker": "DBMF",    "nome": "Managed Futures CTA", "target": 10.0, "tolleranza": 2.5, "quote": 125, "pmc": 29.50}
            ],
            "transazioni": []
        }
    }

def load_data_from_storage() -> dict:
    """
    Carica il database JSON direttamente dal repository GitHub tramite API
    (evitando cache obsolete). Se non configurato, legge dal file locale.
    """
    gh = get_github_config()
    if gh:
        url = f"https://api.github.com/repos/{gh['repo']}/contents/{DATA_FILENAME}?ref={gh['branch']}"
        headers = {
            "Authorization": f"Bearer {gh['token']}",
            "Accept": "application/vnd.github.v3+json",
            "Cache-Control": "no-cache"
        }
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                payload = resp.json()
                raw_json = base64.b64decode(payload["content"]).decode("utf-8")
                data = json.loads(raw_json)
                st.session_state["storage_mode"] = f"GitHub Cloud ({gh['repo']})"
                st.session_state["github_file_sha"] = payload.get("sha")
                return data
            elif resp.status_code == 404:
                # Il file non esiste ancora nel repo: lo inizializziamo al primo salvataggio
                st.session_state["storage_mode"] = f"GitHub Cloud ({gh['repo']} - Nuovo)"
                default_d = get_default_portfolios()
                save_data_to_storage(default_d, commit_msg="Inizializzazione portfolios_data.json")
                return default_d
        except Exception as e:
            st.warning(f"Lettura GitHub API non riuscita ({e}), uso copia locale.")

    st.session_state["storage_mode"] = "File Locale (JSON)"
    if os.path.exists(DATA_FILENAME):
        try:
            with open(DATA_FILENAME, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    return get_default_portfolios()

def save_data_to_storage(data: dict, commit_msg: str = "Aggiornamento portafoglio da Web App"):
    """
    Salva il file JSON in locale e, se GitHub è configurato nei Secrets,
    esegue un commit automatico sul repository remoto tramite API REST.
    """
    json_str = json.dumps(data, indent=4, ensure_ascii=False)

    # 1. Salvataggio su filesystem locale del container / PC
    try:
        with open(DATA_FILENAME, "w", encoding="utf-8") as f:
            f.write(json_str)
    except Exception:
        pass

    # 2. Commit automatico su GitHub tramite REST API
    gh = get_github_config()
    if gh:
        url = f"https://api.github.com/repos/{gh['repo']}/contents/{DATA_FILENAME}"
        headers = {
            "Authorization": f"Bearer {gh['token']}",
            "Accept": "application/vnd.github.v3+json"
        }
        try:
            # Recupera sempre lo SHA aggiornato del file su GitHub per evitare conflitti (409)
            sha = None
            get_resp = requests.get(f"{url}?ref={gh['branch']}", headers=headers, timeout=10)
            if get_resp.status_code == 200:
                sha = get_resp.json().get("sha")

            encoded_content = base64.b64encode(json_str.encode("utf-8")).decode("utf-8")
            put_payload = {
                "message": f"{commit_msg} [{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]",
                "content": encoded_content,
                "branch": gh["branch"]
            }
            if sha:
                put_payload["sha"] = sha

            put_resp = requests.put(url, headers=headers, json=put_payload, timeout=12)
            if put_resp.status_code in (200, 201):
                new_sha = put_resp.json().get("content", {}).get("sha")
                if new_sha:
                    st.session_state["github_file_sha"] = new_sha
                st.session_state["storage_mode"] = f"GitHub Cloud ({gh['repo']})"
                return True, "✅ Salvato con commit automatico su GitHub!"
            else:
                return False, f"⚠️ Errore commit GitHub ({put_resp.status_code}): {put_resp.text}"
        except Exception as e:
            return False, f"⚠️ Errore di rete verso GitHub: {e}"

    return True, "💾 Salvato sul file locale (GitHub non configurato nei Secrets)."

# ==============================================================================
# 4. MOTORE FISCALE ITALIANO (12.5%, 26%, ETC & ZAINETTO MINUSVALENZE)
# ==============================================================================
GOV_KEYWORDS = [
    "treasury", "sxrm", "dtla", "tlt", "ief", "bil", "btp", "bund",
    "gov", "titoli di stato", "bonos", "oat", "cct", "bot", "dbxoan", "xeon"
]
ETC_KEYWORDS = [
    "4gld", "gld", "sgld", "igln", "phau", "gold", "oro", "etc", "etn",
    "wisdomtree physical", "invesco physical", "xetra-gold", "silver", "commodity"
]

def classifica_strumento_fiscale(ticker: str, nome: str = "") -> dict:
    testo = f"{ticker} {nome}".lower()
    for kw in ETC_KEYWORDS:
        if kw in testo:
            return {"codice": "ETC_26", "aliquota": 0.26, "compensa_minus": True, "label": "26% (ETC/Redd. Diversi)"}
    for kw in GOV_KEYWORDS:
        if kw in testo:
            return {"codice": "GOV_125", "aliquota": 0.125, "compensa_minus": False, "label": "12.5% (Gov White-List)"}
    return {"codice": "ETF_26", "aliquota": 0.26, "compensa_minus": False, "label": "26% (ETF/Redd. Capitale)"}

def calcola_vendita_fiscale(ticker: str, nome: str, quote: float, prezzo: float, pmc: float, zainetto_attuale: float = 0.0) -> dict:
    controvalore_lordo = quote * prezzo
    costo_fiscale = quote * pmc
    risultato_lordo = controvalore_lordo - costo_fiscale
    profilo = classifica_strumento_fiscale(ticker, nome)
    aliquota = profilo["aliquota"]

    minus_usata = 0.0
    minus_generata = 0.0
    imposta_dovuta = 0.0
    risparmio_fiscale = 0.0

    if risultato_lordo > 0:
        imponibile = risultato_lordo
        if profilo["compensa_minus"] and zainetto_attuale > 0:
            minus_usata = min(zainetto_attuale, imponibile)
            imponibile -= minus_usata
            risparmio_fiscale = minus_usata * aliquota
        imposta_dovuta = imponibile * aliquota
    elif risultato_lordo < 0:
        minus_generata = abs(risultato_lordo)

    incasso_netto = controvalore_lordo - imposta_dovuta
    nuovo_zainetto = max(0.0, zainetto_attuale - minus_usata + minus_generata)

    return {
        "controvalore_lordo": controvalore_lordo,
        "plusvalenza": risultato_lordo,
        "aliquota": aliquota,
        "label_fiscale": profilo["label"],
        "compensa_minus": profilo["compensa_minus"],
        "minus_usata": minus_usata,
        "minus_generata": minus_generata,
        "risparmio_fiscale": risparmio_fiscale,
        "imposta_dovuta": imposta_dovuta,
        "incasso_netto": incasso_netto,
        "nuovo_zainetto": nuovo_zainetto
    }

# ==============================================================================
# 5. MOTORE QUANTITATIVO DELLE METRICHE DI PERFORMANCE E RISCHIO
# ==============================================================================
def compute_quant_metrics(equity_series: pd.Series, rf_annual: float = 0.025, bench_series: pd.Series = None) -> dict:
    if equity_series is None or len(equity_series.dropna()) < 5:
        return {}

    s = equity_series.dropna()
    rets = s.pct_change().dropna()
    if rets.empty:
        return {}

    total_days = max(1, (s.index[-1] - s.index[0]).days)
    years = total_days / 365.25

    tot_ret_pct = ((s.iloc[-1] / s.iloc[0]) - 1.0) * 100.0
    cagr_pct = (((s.iloc[-1] / s.iloc[0]) ** (1.0 / years)) - 1.0) * 100.0 if years > 0.05 else tot_ret_pct

    vol_pct = float(rets.std() * np.sqrt(252) * 100.0)
    rf_daily = (1.0 + rf_annual) ** (1.0 / 252.0) - 1.0
    excess_rets = rets - rf_daily

    downside_rets = excess_rets[excess_rets < 0]
    downside_dev_pct = float(np.sqrt(np.mean(downside_rets ** 2)) * np.sqrt(252) * 100.0) if len(downside_rets) > 0 else 0.001

    sharpe = (cagr_pct - (rf_annual * 100.0)) / vol_pct if vol_pct > 0 else 0.0
    sortino = (cagr_pct - (rf_annual * 100.0)) / downside_dev_pct if downside_dev_pct > 0 else 0.0

    cummax = s.cummax()
    dd_pct = ((s - cummax) / cummax) * 100.0
    max_dd_pct = float(dd_pct.min())
    ulcer_index = float(np.sqrt(np.mean(dd_pct ** 2)))
    calmar = cagr_pct / abs(max_dd_pct) if max_dd_pct < 0 else 0.0

    var_95 = float(np.percentile(rets, 5) * 100.0)
    cvar_95 = float(rets[rets <= np.percentile(rets, 5)].mean() * 100.0) if len(rets[rets <= np.percentile(rets, 5)]) > 0 else var_95

    win_rate = float((rets > 0).mean() * 100.0)
    best_day = float(rets.max() * 100.0)
    worst_day = float(rets.min() * 100.0)

    beta, alpha_pct = np.nan, np.nan
    if bench_series is not None and len(bench_series.dropna()) >= 5:
        b_rets = bench_series.dropna().pct_change().dropna()
        aligned = pd.concat([rets, b_rets], axis=1, join="inner").dropna()
        if len(aligned) > 10:
            cov_matrix = np.cov(aligned.iloc[:, 0], aligned.iloc[:, 1])
            var_b = cov_matrix[1, 1]
            if var_b > 0:
                beta = float(cov_matrix[0, 1] / var_b)
                b_days = max(1, (aligned.index[-1] - aligned.index[0]).days)
                b_years = b_days / 365.25
                b_cagr = ((((1 + aligned.iloc[:, 1]).prod()) ** (1.0 / b_years)) - 1.0) * 100.0 if b_years > 0.05 else 0.0
                alpha_pct = float(cagr_pct - (rf_annual * 100.0 + beta * (b_cagr - rf_annual * 100.0)))

    return {
        "Totale %": tot_ret_pct,
        "CAGR %": cagr_pct,
        "Volatilità %": vol_pct,
        "Downside Dev %": downside_dev_pct,
        "Sharpe": sharpe,
        "Sortino": sortino,
        "Calmar": calmar,
        "Max Drawdown %": max_dd_pct,
        "Ulcer Index": ulcer_index,
        "VaR 95% (1g)": var_95,
        "CVaR 95% (1g)": cvar_95,
        "Win Rate %": win_rate,
        "Miglior Giorno %": best_day,
        "Peggior Giorno %": worst_day,
        "Beta": beta,
        "Alpha %": alpha_pct,
        "dd_series": dd_pct
    }

def compute_monthly_returns_table(equity_series: pd.Series) -> pd.DataFrame:
    if equity_series is None or equity_series.empty:
        return pd.DataFrame()
    s = equity_series.resample("ME").last()
    m_rets = s.pct_change().dropna() * 100.0
    if m_rets.empty:
        return pd.DataFrame()

    df_m = pd.DataFrame({"Anno": m_rets.index.year, "Mese": m_rets.index.month, "Ret": m_rets.values})
    pivot = df_m.pivot(index="Anno", columns="Mese", values="Ret")
    mesi_nomi = {1: "Gen", 2: "Feb", 3: "Mar", 4: "Apr", 5: "Mag", 6: "Giu",
                 7: "Lug", 8: "Ago", 9: "Set", 10: "Ott", 11: "Nov", 12: "Dic"}
    pivot = pivot.rename(columns=mesi_nomi)

    annual_rets = {}
    for yr, grp in df_m.groupby("Anno"):
        annual_rets[yr] = (np.prod(1.0 + grp["Ret"].values / 100.0) - 1.0) * 100.0
    pivot["Totale Anno"] = pd.Series(annual_rets)
    return pivot.sort_index(ascending=False)

# ==============================================================================
# 6. DOWNLOAD DATI YAHOO FINANCE (MULTI-INDEX SAFE)
# ==============================================================================
def extract_close_dataframe(raw_df: pd.DataFrame, tickers: list) -> pd.DataFrame:
    if raw_df is None or raw_df.empty:
        return pd.DataFrame()
    if isinstance(raw_df.columns, pd.MultiIndex):
        if "Close" in raw_df.columns.get_level_values(0):
            df_close = raw_df["Close"]
        elif "Close" in raw_df.columns.get_level_values(1):
            df_close = raw_df.xs("Close", axis=1, level=1)
        else:
            df_close = raw_df.iloc[:, :len(tickers)]
    else:
        if "Close" in raw_df.columns:
            df_close = raw_df[["Close"]].rename(columns={"Close": tickers[0]})
        else:
            df_close = raw_df

    if isinstance(df_close, pd.Series):
        df_close = df_close.to_frame(name=tickers[0])
    return df_close

@st.cache_data(ttl=300, show_spinner=False)
def fetch_realtime_prices(tickers: list) -> dict:
    prices = {}
    clean_tickers = [t for t in tickers if t]
    if not clean_tickers:
        return prices
    try:
        raw = yf.download(clean_tickers, period="7d", interval="1d", progress=False, auto_adjust=True)
        df_close = extract_close_dataframe(raw, clean_tickers)
        for t in clean_tickers:
            if t in df_close.columns:
                s = df_close[t].dropna()
                if len(s) >= 2:
                    prices[t] = {"price": float(s.iloc[-1]), "prev_close": float(s.iloc[-2])}
                elif len(s) == 1:
                    p = float(s.iloc[-1])
                    prices[t] = {"price": p, "prev_close": p}
                else:
                    prices[t] = {"price": 0.0, "prev_close": 0.0}
            else:
                prices[t] = {"price": 0.0, "prev_close": 0.0}
    except Exception:
        for t in clean_tickers:
            prices[t] = {"price": 0.0, "prev_close": 0.0}
    return prices

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_historical_matrix(tickers: list, start_date: str) -> pd.DataFrame:
    clean_tickers = list(set([t for t in tickers if t]))
    if not clean_tickers:
        return pd.DataFrame()
    try:
        raw = yf.download(clean_tickers, start=start_date, progress=False, auto_adjust=True)
        df_close = extract_close_dataframe(raw, clean_tickers)
        return df_close.ffill().bfill().dropna(how="all")
    except Exception:
        return pd.DataFrame()

# ==============================================================================
# 7. INIZIALIZZAZIONE STATO & BARRA SUPERIORE MOBILE-FRIENDLY
# ==============================================================================
if "all_portfolios" not in st.session_state:
    st.session_state["all_portfolios"] = load_data_from_storage()

all_p = st.session_state["all_portfolios"]
p_names = list(all_p.keys())

for k in p_names:
    if isinstance(all_p[k], list):
        all_p[k] = {
            "data_inizio": "2024-01-02", "capitale_iniziale_versato": 50000.0,
            "cash": 1000.0, "tasse_totali_pagate": 0.0, "zainetto_minusvalenze": 0.0,
            "posizioni": all_p[k], "transazioni": []
        }
    else:
        all_p[k].setdefault("zainetto_minusvalenze", 0.0)
        all_p[k].setdefault("tasse_totali_pagate", 0.0)
        all_p[k].setdefault("cash", 0.0)
        all_p[k].setdefault("transazioni", [])

top_c1, top_c2 = st.columns([3, 1])
with top_c1:
    selected_p = st.selectbox("📂 Portafoglio Attivo:", p_names, index=0 if p_names else None)
with top_c2:
    st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
    if st.button("🔄 Sync Live", use_container_width=True):
        st.cache_data.clear()
        st.session_state["all_portfolios"] = load_data_from_storage()
        st.rerun()

port_cash = float(all_p[selected_p].get("cash", 0.0))

with st.sidebar:
    st.title("🎛️ Impostazioni & Cassa")
    storage_type = st.session_state.get("storage_mode", "Locale")
    if "GitHub Cloud" in storage_type:
        st.success(f"☁️ {storage_type}")
    else:
        st.warning(f"💾 {storage_type}")

    rf_rate_pct = st.number_input("Tasso Risk-Free Annuo (%):", min_value=0.0, max_value=10.0, value=2.50, step=0.25)
    rf_rate = rf_rate_pct / 100.0

    st.divider()
    st.subheader("💵 Gestione Liquidità")
    cash_mov = st.number_input("Importo (€):", min_value=10.0, max_value=1000000.0, value=1000.0, step=100.0)
    c_in, c_out = st.columns(2)
    with c_in:
        if st.button("Deposita", use_container_width=True):
            all_p[selected_p]["cash"] = port_cash + cash_mov
            all_p[selected_p]["capitale_iniziale_versato"] = float(all_p[selected_p].get("capitale_iniziale_versato", 0.0)) + cash_mov
            all_p[selected_p]["transazioni"].append({
                "data": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                "tipo": "DEPOSITO_CASH", "ticker": "CASH", "quote": 0, "prezzo": 1.0,
                "lordo": cash_mov, "plusvalenza": 0.0, "tassa_pagata": 0.0, "netto_incassato": cash_mov
            })
            save_data_to_storage(all_p, commit_msg=f"Deposito Cash su {selected_p}")
            st.rerun()
    with c_out:
        if st.button("Preleva", use_container_width=True):
            if cash_mov <= port_cash:
                all_p[selected_p]["cash"] = port_cash - cash_mov
                all_p[selected_p]["capitale_iniziale_versato"] = max(0.0, float(all_p[selected_p].get("capitale_iniziale_versato", 0.0)) - cash_mov)
                all_p[selected_p]["transazioni"].append({
                    "data": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "tipo": "PRELIEVO_CASH", "ticker": "CASH", "quote": 0, "prezzo": 1.0,
                    "lordo": cash_mov, "plusvalenza": 0.0, "tassa_pagata": 0.0, "netto_incassato": -cash_mov
                })
                save_data_to_storage(all_p, commit_msg=f"Prelievo Cash da {selected_p}")
                st.rerun()
            else:
                st.error("Cash insufficiente.")

    st.divider()
    with st.expander("➕ Crea / Duplica Portafoglio"):
        new_p_name = st.text_input("Nome Nuovo Portafoglio:")
        clone_from = st.selectbox("Copia da:", ["Vuoto Base"] + p_names)
        new_cap = st.number_input("Capitale Versato (€):", value=50000.0, step=1000.0)
        if st.button("Crea Portafoglio", use_container_width=True):
            if new_p_name and new_p_name not in all_p:
                cloned_pos = copy.deepcopy(all_p[clone_from]["posizioni"]) if clone_from != "Vuoto Base" else [
                    {"ticker": "SWDA.MI", "nome": "MSCI World", "target": 60.0, "tolleranza": 5.0, "quote": 100, "pmc": 85.00},
                    {"ticker": "SXRM.DE", "nome": "Treasury 7-10yr (Gov)", "target": 40.0, "tolleranza": 5.0, "quote": 200, "pmc": 27.00}
                ]
                all_p[new_p_name] = {
                    "data_inizio": datetime.date.today().strftime("%Y-%m-%d"),
                    "capitale_iniziale_versato": new_cap, "cash": 1000.0,
                    "tasse_totali_pagate": 0.0, "zainetto_minusvalenze": 0.0,
                    "posizioni": cloned_pos, "transazioni": []
                }
                save_data_to_storage(all_p, commit_msg=f"Creazione portafoglio {new_p_name}")
                st.rerun()

    with st.expander("✏️ Rinomina / Elimina"):
        ren_val = st.text_input("Nuovo nome:", value=selected_p)
        cr1, cr2 = st.columns(2)
        with cr1:
            if st.button("Rinomina", use_container_width=True):
                if ren_val and ren_val != selected_p and ren_val not in all_p:
                    all_p[ren_val] = all_p.pop(selected_p)
                    save_data_to_storage(all_p, commit_msg=f"Rinomina portafoglio in {ren_val}")
                    st.rerun()
        with cr2:
            if st.button("Elimina 🗑️", use_container_width=True):
                if len(all_p) > 1:
                    all_p.pop(selected_p)
                    save_data_to_storage(all_p, commit_msg=f"Eliminazione portafoglio {selected_p}")
                    st.rerun()
                else:
                    st.error("Impossibile eliminare l'ultimo portafoglio.")

# ==============================================================================
# 8. CALCOLO POSIZIONI & METRICHE PORTAFOGLIO ATTIVO
# ==============================================================================
curr_data = all_p[selected_p]
posizioni = curr_data.get("posizioni", [])
tickers = [p["ticker"] for p in posizioni if p.get("ticker")]

with st.spinner("Sincronizzazione quotazioni da Yahoo Finance..."):
    prezzi_info = fetch_realtime_prices(tickers)

righe_tabella = []
valore_totale_strumenti = 0.0
valore_totale_ieri = 0.0
daily_pnl_totale_eur = 0.0
plusvalenze_latenti_totali = 0.0
imposta_latente_stimata = 0.0
zainetto_minus = float(curr_data.get("zainetto_minusvalenze", 0.0))

for p in posizioni:
    tk = p["ticker"]
    nome = p.get("nome", tk)
    target = float(p.get("target", 0.0))
    toll = float(p.get("tolleranza", 2.0))
    quote = float(p.get("quote", 0))
    pmc = float(p.get("pmc", 0.0))

    q_info = prezzi_info.get(tk, {"price": 0.0, "prev_close": 0.0})
    prezzo = q_info["price"]
    prev_close = q_info["prev_close"] if q_info["prev_close"] > 0 else prezzo

    controvalore = quote * prezzo
    controvalore_ieri = quote * prev_close
    valore_totale_strumenti += controvalore
    valore_totale_ieri += controvalore_ieri

    daily_gain_eur = controvalore - controvalore_ieri
    daily_gain_pct = ((prezzo / prev_close) - 1.0) * 100.0 if prev_close > 0 else 0.0
    daily_pnl_totale_eur += daily_gain_eur

    costo_tot = quote * pmc
    gain_latente = controvalore - costo_tot
    plusvalenze_latenti_totali += gain_latente
    gain_latente_pct = ((prezzo / pmc) - 1.0) * 100.0 if pmc > 0 else 0.0

    prof_fisc = classifica_strumento_fiscale(tk, nome)
    if gain_latente > 0:
        imposta_latente_stimata += gain_latente * prof_fisc["aliquota"]

    righe_tabella.append({
        "Ticker": tk, "Nome": nome, "Quote": quote, "PMC €": pmc, "Prezzo €": prezzo,
        "Var. Oggi %": daily_gain_pct, "Var. Oggi €": daily_gain_eur,
        "Controvalore €": controvalore, "P&L Latente €": gain_latente, "P&L %": gain_latente_pct,
        "Regime Fiscale": prof_fisc["label"], "Target %": target, "Tolleranza %": toll
    })

df_pos = pd.DataFrame(righe_tabella)
valore_portafoglio_totale = valore_totale_strumenti + port_cash
valore_portafoglio_ieri = valore_totale_ieri + port_cash
daily_pnl_totale_pct = (daily_pnl_totale_eur / valore_portafoglio_ieri * 100.0) if valore_portafoglio_ieri > 0 else 0.0

if not df_pos.empty and valore_portafoglio_totale > 0:
    df_pos["Peso Attuale %"] = (df_pos["Controvalore €"] / valore_portafoglio_totale) * 100.0
    df_pos["Scostamento %"] = df_pos["Peso Attuale %"] - df_pos["Target %"]
    df_pos["Utilizzo Banda %"] = (df_pos["Scostamento %"].abs() / df_pos["Tolleranza %"]) * 100.0
    df_pos["Fuori Banda"] = df_pos["Scostamento %"].abs() > df_pos["Tolleranza %"]
    df_pos["Stato"] = df_pos.apply(
        lambda r: "🚨 RIBILANCIARE" if r["Fuori Banda"] else ("⚠️ VICINO SOGLIA" if r["Utilizzo Banda %"] >= 80 else "✅ IN TARGET"),
        axis=1
    )
    df_pos["Target Valore €"] = valore_portafoglio_totale * (df_pos["Target %"] / 100.0)
    df_pos["Azione €"] = df_pos["Target Valore €"] - df_pos["Controvalore €"]
    df_pos["Azione Quote"] = df_pos.apply(
        lambda r: int(round(r["Azione €"] / r["Prezzo €"])) if r["Prezzo €"] > 0 else 0, axis=1
    )
else:
    for col in ["Peso Attuale %", "Scostamento %", "Utilizzo Banda %", "Azione €", "Azione Quote"]:
        df_pos[col] = 0.0
    df_pos["Fuori Banda"] = False
    df_pos["Stato"] = "IN ATTESA"

# ==============================================================================
# 9. BENTO GRID RESPONSIVA (PIXEL 10 PRO E DESKTOP)
# ==============================================================================
cap_versato = float(curr_data.get("capitale_iniziale_versato", valore_portafoglio_totale))
data_inizio_str = curr_data.get("data_inizio", "2024-01-02")
data_inizio_dt = datetime.datetime.strptime(data_inizio_str, "%Y-%m-%d").date()
giorni_inv = max(1, (datetime.date.today() - data_inizio_dt).days)
anni_inv = giorni_inv / 365.25

pnl_netto_eur = valore_portafoglio_totale - cap_versato
pnl_netto_pct = (pnl_netto_eur / cap_versato * 100.0) if cap_versato > 0 else 0.0
cagr_effettivo = (((valore_portafoglio_totale / cap_versato) ** (1.0 / anni_inv)) - 1.0) * 100.0 if (cap_versato > 0 and anni_inv > 0.05 and valore_portafoglio_totale > 0) else pnl_netto_pct
tasse_pagate = float(curr_data.get("tasse_totali_pagate", 0.0))
cash_weight_pct = (port_cash / valore_portafoglio_totale * 100.0) if valore_portafoglio_totale > 0 else 0.0

cls_oggi = "pos-delta" if daily_pnl_totale_eur >= 0 else "neg-delta"
cls_storico = "pos-delta" if pnl_netto_eur >= 0 else "neg-delta"
cls_latente = "pos-delta" if plusvalenze_latenti_totali >= 0 else "neg-delta"

bento_html = f"""
<div class="bento-grid">
    <div class="bento-card">
        <div class="bento-label">Patrimonio Totale</div>
        <div class="bento-value">€ {valore_portafoglio_totale:,.2f}</div>
        <div class="bento-sub neu-delta">Cash: € {port_cash:,.0f} ({cash_weight_pct:.1f}%)</div>
    </div>
    <div class="bento-card">
        <div class="bento-label">Performance Oggi</div>
        <div class="bento-value {cls_oggi}">€ {daily_pnl_totale_eur:+,.2f}</div>
        <div class="bento-sub {cls_oggi}">{daily_pnl_totale_pct:+.2f}% intraday</div>
    </div>
    <div class="bento-card">
        <div class="bento-label">P&L Storico Reale</div>
        <div class="bento-value {cls_storico}">€ {pnl_netto_eur:+,.2f}</div>
        <div class="bento-sub {cls_storico}">{pnl_netto_pct:+.2f}% su versato</div>
    </div>
    <div class="bento-card">
        <div class="bento-label">CAGR Effettivo</div>
        <div class="bento-value">{cagr_effettivo:.2f}%</div>
        <div class="bento-sub neu-delta">Attivo da {anni_inv:.1f} anni</div>
    </div>
    <div class="bento-card">
        <div class="bento-label">P&L Latente Lordo</div>
        <div class="bento-value {cls_latente}">€ {plusvalenze_latenti_totali:+,.2f}</div>
        <div class="bento-sub neu-delta">Netto: € {valore_portafoglio_totale - imposta_latente_stimata:,.0f}</div>
    </div>
    <div class="bento-card">
        <div class="bento-label">Fisco & Zainetto</div>
        <div class="bento-value">€ {tasse_pagate:,.2f}</div>
        <div class="bento-sub neu-delta">Minus: € {zainetto_minus:,.0f}</div>
    </div>
</div>
"""
st.markdown(bento_html, unsafe_allow_html=True)

# ==============================================================================
# 10. NAVIGAZIONE PRINCIPALE (7 TAB SCORREVOLI SU TOUCHSCREEN)
# ==============================================================================
tab_reb, tab_quant, tab_comp, tab_pac, tab_tax, tab_setup, tab_cloud = st.tabs([
    "⚖️ Bande & Ordini",
    "📊 Quant Dashboard",
    "⚔️ Confronto",
    "💰 Smart PAC",
    "🧾 Fisco",
    "⚙️ Setup",
    "☁️ Database GitHub"
])

# ------------------------------------------------------------------------------
# TAB 1: RIBILANCIAMENTO A BANDE (VISTA CARD MOBILE + TABELLA DESKTOP)
# ------------------------------------------------------------------------------
with tab_reb:
    vista_scelta = st.radio(
        "Formato visualizzazione:",
        ["📱 Vista Card (Ottimizzata per Pixel)", "🖥️ Tabella Completa"],
        horizontal=True
    )

    if "Vista Card" in vista_scelta:
        for _, r in df_pos.iterrows():
            badge_cls = "badge-alert" if r["Fuori Banda"] else ("badge-warn" if "VICINO" in r["Stato"] else "badge-ok")
            d_cls = "pos-delta" if r["Var. Oggi %"] >= 0 else "neg-delta"
            pnl_cls = "pos-delta" if r["P&L %"] >= 0 else "neg-delta"
            azione_str = f"Compra {r['Azione Quote']:+,.0f} quote (€ {abs(r['Azione €']):,.0f})" if r["Azione Quote"] > 0 else (
                f"Vendi {abs(r['Azione Quote']):,.0f} quote (€ {abs(r['Azione €']):,.0f})" if r["Azione Quote"] < 0 else "Nessuna azione"
            )
            st.markdown(f"""
            <div class="asset-card">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                    <div><b>{r['Ticker']}</b> <span style="color:#64748B; font-size:0.85rem;">• {r['Nome']}</span></div>
                    <span class="{badge_cls}">{r['Stato']}</span>
                </div>
                <div style="display:grid; grid-template-columns: repeat(3, 1fr); gap:6px; font-size:0.84rem;">
                    <div>Prezzo: <b>€ {r['Prezzo €']:.2f}</b> <span class="{d_cls}">({r['Var. Oggi %']:+.2f}%)</span></div>
                    <div>Valore: <b>€ {r['Controvalore €']:,.0f}</b> ({r['Quote']:.0f} q)</div>
                    <div>P&L: <b class="{pnl_cls}">{r['P&L %']:+.1f}%</b> (PMC €{r['PMC €']:.2f})</div>
                    <div>Peso: <b>{r['Peso Attuale %']:.1f}%</b> / {r['Target %']:.1f}%</div>
                    <div>Scost.: <b>{r['Scostamento %']:+.2f}%</b> (±{r['Tolleranza %']:.1f}%)</div>
                    <div>Azione: <b>{azione_str}</b></div>
                </div>
            </div>
            """, unsafe_allow_html=True)
    else:
        display_df = df_pos[[
            "Ticker", "Nome", "Prezzo €", "Var. Oggi %", "Quote", "PMC €",
            "Controvalore €", "P&L %", "Peso Attuale %", "Target %",
            "Tolleranza %", "Scostamento %", "Stato", "Azione Quote", "Azione €", "Regime Fiscale"
        ]].copy()
        styled_pos = display_df.style.format({
            "Prezzo €": "€ {:.2f}", "Var. Oggi %": "{:+.2f}%", "Quote": "{:,.0f}",
            "PMC €": "€ {:.2f}", "Controvalore €": "€ {:,.2f}", "P&L %": "{:+.2f}%",
            "Peso Attuale %": "{:.2f}%", "Target %": "{:.2f}%", "Tolleranza %": "±{:.2f}%",
            "Scostamento %": "{:+.2f}%", "Azione Quote": "{:+,.0f}", "Azione €": "€ {:+,.2f}"
        }).map(
            lambda v: "background-color: #FEE2E2; color: #991B1B; font-weight: bold;" if "RIBILANCIARE" in str(v)
            else ("background-color: #FEF3C7; color: #92400E; font-weight: bold;" if "VICINO" in str(v)
                  else "background-color: #DCFCE7; color: #166534; font-weight: bold;"),
            subset=["Stato"]
        )
        st.dataframe(styled_pos, use_container_width=True, height=360)

    # GRAFICI CORRIDOR BAND + TORTA ALLOCAZIONE
    col_band_chart, col_pie_chart = st.columns([1.6, 1.2])
    with col_band_chart:
        st.markdown("##### 🎯 Corridor Chart: Scostamento % vs Bande")
        if not df_pos.empty:
            fig_band = go.Figure()
            fig_band.add_trace(go.Bar(
                y=df_pos["Ticker"], x=df_pos["Tolleranza %"], orientation='h',
                marker=dict(color='rgba(148, 163, 184, 0.25)', line=dict(color='#64748B', width=1))
            ))
            fig_band.add_trace(go.Bar(
                y=df_pos["Ticker"], x=-df_pos["Tolleranza %"], orientation='h',
                marker=dict(color='rgba(148, 163, 184, 0.25)', line=dict(color='#64748B', width=1))
            ))
            colors_scost = ["#DC2626" if fb else "#16A34A" for fb in df_pos["Fuori Banda"]]
            fig_band.add_trace(go.Scatter(
                y=df_pos["Ticker"], x=df_pos["Scostamento %"], mode='markers+text',
                text=[f"{v:+.1f}%" for v in df_pos["Scostamento %"]], textposition="middle right",
                marker=dict(color=colors_scost, size=11, symbol="diamond")
            ))
            fig_band.update_layout(
                barmode='overlay', template="plotly_white", height=310,
                margin=dict(t=10, b=10, l=10, r=35), showlegend=False
            )
            fig_band.add_vline(x=0, line_width=1.5, line_dash="dash", line_color="#0F172A")
            st.plotly_chart(fig_band, use_container_width=True)

    with col_pie_chart:
        st.markdown("##### 🍩 Allocazione Effettiva")
        pie_labels = list(df_pos["Ticker"]) + ["CASH"]
        pie_values = list(df_pos["Controvalore €"]) + [port_cash]
        fig_pie = go.Figure(data=[go.Pie(
            labels=pie_labels, values=pie_values, hole=0.55,
            textinfo="label+percent", marker=dict(colors=px.colors.qualitative.Prism)
        )])
        fig_pie.update_layout(height=310, margin=dict(t=10, b=10, l=10, r=10), showlegend=False)
        st.plotly_chart(fig_pie, use_container_width=True)

    # ORDINI A BANDA AUTOMATICI
    st.divider()
    st.subheader("⚡ Esecuzione Rapida Ribilanciamenti a Banda")
    out_of_band = df_pos[df_pos["Fuori Banda"]].to_dict("records")
    if out_of_band:
        for item in out_of_band:
            tk = item["Ticker"]
            nome = item["Nome"]
            q_act = item["Azione Quote"]
            pr = item["Prezzo €"]
            pmc_i = item["PMC €"]
            c_ord1, c_ord2 = st.columns([3, 1])
            if q_act < 0:
                q_s = abs(q_act)
                sim_b = calcola_vendita_fiscale(tk, nome, q_s, pr, pmc_i, zainetto_minus)
                c_ord1.markdown(
                    f"🔴 **VENDI `{tk}`**: **{q_s}** quote a **€ {pr:.2f}** • "
                    f"Tassa: € {sim_b['imposta_dovuta']:,.2f} ➡️ **Netto su Cash: € {sim_b['incasso_netto']:,.2f}**"
                )
                if c_ord2.button(f"Vendi {tk}", key=f"b_sell_{tk}", use_container_width=True):
                    for p in posizioni:
                        if p["ticker"] == tk:
                            p["quote"] = max(0, p["quote"] - q_s)
                    all_p[selected_p]["cash"] = port_cash + sim_b["incasso_netto"]
                    all_p[selected_p]["tasse_totali_pagate"] = tasse_pagate + sim_b["imposta_dovuta"]
                    all_p[selected_p]["zainetto_minusvalenze"] = sim_b["nuovo_zainetto"]
                    all_p[selected_p]["transazioni"].append({
                        "data": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "tipo": "VENDITA_BANDA", "ticker": tk, "quote": q_s, "prezzo": pr,
                        "pmc": pmc_i, "lordo": sim_b["controvalore_lordo"], "plusvalenza": sim_b["plusvalenza"],
                        "minus_compensata": sim_b["minus_usata"], "tassa_pagata": sim_b["imposta_dovuta"],
                        "netto_incassato": sim_b["incasso_netto"]
                    })
                    save_data_to_storage(all_p, commit_msg=f"Vendita a banda {tk}")
                    st.rerun()
            elif q_act > 0:
                costo_b = q_act * pr
                c_ord1.markdown(
                    f"🟢 **COMPRA `{tk}`**: **{q_act}** quote a **€ {pr:.2f}** • "
                    f"Spesa: **€ {costo_b:,.2f}** (Cash disp.: € {port_cash:,.2f})"
                )
                if c_ord2.button(f"Compra {tk}", key=f"b_buy_{tk}", use_container_width=True):
                    if costo_b > port_cash:
                        st.error("Cash insufficiente. Esegui prima una vendita o deposita liquidità.")
                    else:
                        for p in posizioni:
                            if p["ticker"] == tk:
                                nq = p["quote"] + q_act
                                p["pmc"] = round(((p["quote"] * p["pmc"]) + costo_b) / nq, 4)
                                p["quote"] = nq
                        all_p[selected_p]["cash"] = port_cash - costo_b
                        all_p[selected_p]["transazioni"].append({
                            "data": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "tipo": "ACQUISTO_BANDA", "ticker": tk, "quote": q_act, "prezzo": pr,
                            "pmc": pr, "lordo": costo_b, "plusvalenza": 0.0,
                            "minus_compensata": 0.0, "tassa_pagata": 0.0, "netto_incassato": -costo_b
                        })
                        save_data_to_storage(all_p, commit_msg=f"Acquisto a banda {tk}")
                        st.rerun()
    else:
        st.success("🎯 Tutti gli strumenti sono all'interno delle bande di tolleranza.")

    # OPERAZIONI ESTEMPORANEE MANUALI
    with st.expander("🛠️ Operazione Estemporanea Manuale (Compra / Vendi Quote)"):
        c_op1, c_op2, c_op3, c_op4 = st.columns([1.4, 1.2, 1.0, 1.0])
        with c_op1:
            etf_sel = st.selectbox("Strumento:", tickers, key="man_etf")
        asset_obj = next((item for item in posizioni if item["ticker"] == etf_sel), None)
        p_mkt = prezzi_info.get(etf_sel, {}).get("price", 0.0)
        q_att = asset_obj["quote"] if asset_obj else 0
        pmc_att = asset_obj["pmc"] if asset_obj else 0.0
        nome_att = asset_obj.get("nome", etf_sel) if asset_obj else etf_sel

        with c_op2:
            tipo_op = st.radio("Azione:", ["Vendi (-> Cash)", "Compra (Usa Cash)"], horizontal=True)
        with c_op3:
            q_man = st.number_input(
                "Quote:", min_value=1,
                max_value=int(q_att) if ("Vendi" in tipo_op and q_att > 0) else 100000,
                value=min(10, int(q_att)) if ("Vendi" in tipo_op and q_att > 0) else 10, step=1
            )
        with c_op4:
            p_man = st.number_input("Prezzo (€):", min_value=0.01, value=float(p_mkt) if p_mkt > 0 else 100.0, step=0.01, format="%.2f")

        if "Vendi" in tipo_op:
            sim = calcola_vendita_fiscale(etf_sel, nome_att, q_man, p_man, pmc_att, zainetto_minus)
            st.info(
                f"Lordo: **€ {sim['controvalore_lordo']:,.2f}** | P&L: **€ {sim['plusvalenza']:+,.2f}** | "
                f"Minus usata: **€ {sim['minus_usata']:,.2f}** | Imposta: **€ {sim['imposta_dovuta']:,.2f}** ➡️ "
                f"**Incasso Netto su Cash: € {sim['incasso_netto']:,.2f}**"
            )
            if st.button("🔴 Conferma Vendita Manuale", type="primary", use_container_width=True):
                if q_man <= q_att:
                    asset_obj["quote"] = q_att - q_man
                    all_p[selected_p]["cash"] = port_cash + sim["incasso_netto"]
                    all_p[selected_p]["tasse_totali_pagate"] = tasse_pagate + sim["imposta_dovuta"]
                    all_p[selected_p]["zainetto_minusvalenze"] = sim["nuovo_zainetto"]
                    all_p[selected_p]["transazioni"].append({
                        "data": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "tipo": "VENDITA_MANUALE", "ticker": etf_sel, "quote": q_man, "prezzo": p_man,
                        "pmc": pmc_att, "lordo": sim["controvalore_lordo"], "plusvalenza": sim["plusvalenza"],
                        "minus_compensata": sim["minus_usata"], "tassa_pagata": sim["imposta_dovuta"],
                        "netto_incassato": sim["incasso_netto"]
                    })
                    save_data_to_storage(all_p, commit_msg=f"Vendita manuale {q_man}x {etf_sel}")
                    st.rerun()
        else:
            costo_tot = q_man * p_man
            new_q = q_att + q_man
            new_pmc = ((q_att * pmc_att) + costo_tot) / new_q if new_q > 0 else p_man
            st.info(f"Spesa: **€ {costo_tot:,.2f}** | Cash residuo: **€ {port_cash - costo_tot:,.2f}** | Nuovo PMC: **€ {new_pmc:.2f}**")
            if st.button("🟢 Conferma Acquisto Manuale", type="primary", use_container_width=True):
                if costo_tot <= port_cash:
                    asset_obj["quote"] = new_q
                    asset_obj["pmc"] = round(new_pmc, 4)
                    all_p[selected_p]["cash"] = port_cash - costo_tot
                    all_p[selected_p]["transazioni"].append({
                        "data": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "tipo": "ACQUISTO_MANUALE", "ticker": etf_sel, "quote": q_man, "prezzo": p_man,
                        "pmc": round(new_pmc, 4), "lordo": costo_tot, "plusvalenza": 0.0,
                        "minus_compensata": 0.0, "tassa_pagata": 0.0, "netto_incassato": -costo_tot
                    })
                    save_data_to_storage(all_p, commit_msg=f"Acquisto manuale {q_man}x {etf_sel}")
                    st.rerun()
                else:
                    st.error("Cash insufficiente.")

# ------------------------------------------------------------------------------
# TAB 2: DASHBOARD QUANTITATIVA (12 METRICHE + HEATMAP + CORRELAZIONE)
# ------------------------------------------------------------------------------
with tab_quant:
    cq1, cq2, cq3 = st.columns([1.5, 1.0, 1.0])
    with cq1:
        modalita_analisi = st.radio("Serie:", ["Patrimonio Reale", "Backtest Pesi Target"], horizontal=True)
    with cq2:
        anni_backtest = st.selectbox("Anni Backtest:", [1, 3, 5, 10], index=2)
    with cq3:
        bench_tk = st.selectbox("Benchmark:", ["SWDA.MI", "SPY", "QQQ", "URTH"], index=0)

    start_q = data_inizio_str if "Reale" in modalita_analisi else (
        datetime.date.today() - datetime.timedelta(days=int(anni_backtest * 365.25))
    ).strftime("%Y-%m-%d")

    df_hist = fetch_historical_matrix(tickers + [bench_tk], start_date=start_q)
    if not df_hist.empty:
        valid_tks = [t for t in tickers if t in df_hist.columns]
        if valid_tks:
            if "Reale" in modalita_analisi:
                port_series = pd.Series(port_cash, index=df_hist.index)
                for p in posizioni:
                    if p["ticker"] in df_hist.columns:
                        port_series += df_hist[p["ticker"]] * float(p["quote"])
            else:
                rets_asset = df_hist[valid_tks].pct_change().fillna(0.0)
                tot_w = sum(float(p["target"]) for p in posizioni if p["ticker"] in valid_tks)
                w_vec = np.array([float(p["target"]) / tot_w for p in posizioni if p["ticker"] in valid_tks]) if tot_w > 0 else np.ones(len(valid_tks)) / len(valid_tks)
                port_series = (1.0 + rets_asset.dot(w_vec)).cumprod() * 100.0

            bench_s = None
            if bench_tk in df_hist.columns:
                bench_s = (1.0 + df_hist[bench_tk].pct_change().fillna(0.0)).cumprod() * float(port_series.iloc[0])

            qm = compute_quant_metrics(port_series, rf_annual=rf_rate, bench_series=bench_s)
            if qm:
                quant_bento = f"""
                <div class="bento-grid">
                    <div class="bento-card"><div class="bento-label">CAGR Annuo</div><div class="bento-value">{qm['CAGR %']:.2f}%</div><div class="bento-sub neu-delta">Tot: {qm['Totale %']:+.1f}%</div></div>
                    <div class="bento-card"><div class="bento-label">Volatilità</div><div class="bento-value">{qm['Volatilità %']:.2f}%</div><div class="bento-sub neu-delta">Down: {qm['Downside Dev %']:.2f}%</div></div>
                    <div class="bento-card"><div class="bento-label">Sharpe / Sortino</div><div class="bento-value">{qm['Sharpe']:.2f} / {qm['Sortino']:.2f}</div><div class="bento-sub neu-delta">Rf: {rf_rate_pct:.1f}%</div></div>
                    <div class="bento-card"><div class="bento-label">Max Drawdown</div><div class="bento-value neg-delta">{qm['Max Drawdown %']:.2f}%</div><div class="bento-sub neu-delta">Ulcer: {qm['Ulcer Index']:.2f}</div></div>
                    <div class="bento-card"><div class="bento-label">Calmar / WinRate</div><div class="bento-value">{qm['Calmar']:.2f}</div><div class="bento-sub neu-delta">Win: {qm['Win Rate %']:.1f}%</div></div>
                    <div class="bento-card"><div class="bento-label">VaR / CVaR 95%</div><div class="bento-value neg-delta">{qm['VaR 95% (1g)']:.2f}%</div><div class="bento-sub neg-delta">CVaR: {qm['CVaR 95% (1g)']:.2f}%</div></div>
                </div>
                """
                st.markdown(quant_bento, unsafe_allow_html=True)

                fig_eq = go.Figure()
                fig_eq.add_trace(go.Scatter(x=port_series.index, y=port_series, mode="lines", name=selected_p, line=dict(color="#2563EB", width=2.5)))
                if bench_s is not None:
                    fig_eq.add_trace(go.Scatter(x=bench_s.index, y=bench_s, mode="lines", name=bench_tk, line=dict(color="#94A3B8", width=1.6, dash="dot")))
                fig_eq.update_layout(title="Equity Curve", template="plotly_white", hovermode="x unified", height=330, margin=dict(t=35, b=10, l=10, r=10))
                st.plotly_chart(fig_eq, use_container_width=True)

                fig_dd = go.Figure()
                fig_dd.add_trace(go.Scatter(x=qm["dd_series"].index, y=qm["dd_series"], mode="lines", fill="tozeroy", name="Drawdown %", line=dict(color="#DC2626", width=1.5), fillcolor="rgba(220,38,38,0.15)"))
                fig_dd.update_layout(title="Underwater Drawdown (%)", template="plotly_white", height=230, margin=dict(t=35, b=10, l=10, r=10))
                st.plotly_chart(fig_dd, use_container_width=True)

                st.markdown("##### 📅 Rendimenti Mensili e Annuali (%)")
                df_monthly = compute_monthly_returns_table(port_series)
                if not df_monthly.empty:
                    st.dataframe(df_monthly.style.format("{:+.2f}%", na_rep="-").background_gradient(cmap="RdYlGn", vmin=-8, vmax=8), use_container_width=True)

                if len(valid_tks) > 1:
                    st.markdown("##### 🔗 Matrice di Correlazione tra gli ETF")
                    corr_mat = df_hist[valid_tks].pct_change().dropna().corr()
                    fig_corr = px.imshow(corr_mat, text_auto=".2f", color_continuous_scale="RdBu_r", zmin=-1, zmax=1, aspect="auto")
                    fig_corr.update_layout(height=320, margin=dict(t=10, b=10, l=10, r=10), coloraxis_showscale=False)
                    st.plotly_chart(fig_corr, use_container_width=True)

# ------------------------------------------------------------------------------
# TAB 3: CONFRONTO MULTI-PORTAFOGLIO (HEAD-TO-HEAD)
# ------------------------------------------------------------------------------
with tab_comp:
    st.subheader("⚔️ Confronto Diretto Multi-Portafoglio")
    cc1, cc2, cc3 = st.columns([1.6, 1.2, 1.0])
    with cc1:
        selected_compare = st.multiselect("Portafogli:", p_names, default=p_names)
    with cc2:
        comp_mode = st.radio("Metodo:", ["Pesi Target (Base 100)", "Quote Reali (Base 100)"], horizontal=True)
    with cc3:
        comp_yrs = st.selectbox("Orizzonte:", [1, 3, 5, 10], index=1)

    if selected_compare:
        comp_start = (datetime.date.today() - datetime.timedelta(days=int(comp_yrs * 365.25))).strftime("%Y-%m-%d")
        all_comp_tickers = {item["ticker"] for pn in selected_compare for item in all_p[pn].get("posizioni", []) if item.get("ticker")}
        df_comp_prices = fetch_historical_matrix(list(all_comp_tickers), start_date=comp_start)

        if not df_comp_prices.empty:
            rets_all = df_comp_prices.pct_change().fillna(0.0)
            curves_dict = {}
            metrics_comparison = []

            for pn in selected_compare:
                p_obj = all_p[pn]
                pos_list = [x for x in p_obj.get("posizioni", []) if x.get("ticker") in df_comp_prices.columns]
                if not pos_list:
                    continue
                if "Target" in comp_mode:
                    tot_t = sum(float(x["target"]) for x in pos_list)
                    weights = {x["ticker"]: (float(x["target"]) / tot_t if tot_t > 0 else 1.0 / len(pos_list)) for x in pos_list}
                    p_ret = sum(rets_all[tk] * w for tk, w in weights.items())
                    eq_c = (1.0 + p_ret).cumprod() * 100.0
                else:
                    val_s = pd.Series(float(p_obj.get("cash", 0.0)), index=df_comp_prices.index)
                    for x in pos_list:
                        val_s += df_comp_prices[x["ticker"]] * float(x["quote"])
                    eq_c = (val_s / val_s.iloc[0]) * 100.0 if val_s.iloc[0] > 0 else val_s

                curves_dict[pn] = eq_c
                m_res = compute_quant_metrics(eq_c, rf_annual=rf_rate)
                if m_res:
                    metrics_comparison.append({
                        "Portafoglio": pn, "CAGR %": m_res["CAGR %"], "Totale %": m_res["Totale %"],
                        "Volatilità %": m_res["Volatilità %"], "Max DD %": m_res["Max Drawdown %"],
                        "Sharpe": m_res["Sharpe"], "Sortino": m_res["Sortino"],
                        "Calmar": m_res["Calmar"], "Ulcer Index": m_res["Ulcer Index"]
                    })

            if metrics_comparison:
                df_comp_t = pd.DataFrame(metrics_comparison).set_index("Portafoglio")
                st.dataframe(
                    df_comp_t.style.format({
                        "CAGR %": "{:+.2f}%", "Totale %": "{:+.2f}%", "Volatilità %": "{:.2f}%",
                        "Max DD %": "{:.2f}%", "Sharpe": "{:.2f}", "Sortino": "{:.2f}",
                        "Calmar": "{:.2f}", "Ulcer Index": "{:.2f}"
                    }).highlight_max(subset=["CAGR %", "Sharpe", "Sortino", "Calmar"], color="#DCFCE7")
                      .highlight_min(subset=["Volatilità %", "Ulcer Index"], color="#DCFCE7"),
                    use_container_width=True
                )

                fig_m_eq = go.Figure()
                for name_c, s_c in curves_dict.items():
                    fig_m_eq.add_trace(go.Scatter(x=s_c.index, y=s_c, mode="lines", name=name_c, line=dict(width=2.5)))
                fig_m_eq.update_layout(title="Equity Curve Comparata (Base 100)", template="plotly_white", hovermode="x unified", height=350, margin=dict(t=35, b=10))
                st.plotly_chart(fig_m_eq, use_container_width=True)

# ------------------------------------------------------------------------------
# TAB 4: SIMULATORE SMART PAC
# ------------------------------------------------------------------------------
with tab_pac:
    st.subheader("💡 Simulatore Smart PAC (Zero Vendite)")
    cash_pac = st.number_input("Nuova liquidità PAC da investire (€):", min_value=50.0, max_value=1000000.0, value=1500.0, step=100.0)
    nuovo_tot_pac = valore_portafoglio_totale + cash_pac
    gaps = [max(0.0, nuovo_tot_pac * (r["Target %"] / 100.0) - r["Controvalore €"]) for _, r in df_pos.iterrows()]
    somma_gap = sum(gaps)

    pac_rows = []
    for idx, (_, r) in enumerate(df_pos.iterrows()):
        budget_etf = cash_pac * (gaps[idx] / somma_gap) if somma_gap > 0 else cash_pac * (r["Target %"] / 100.0)
        q_buy = int(budget_etf // r["Prezzo €"]) if r["Prezzo €"] > 0 else 0
        spesa_eff = q_buy * r["Prezzo €"]
        pac_rows.append({
            "Ticker": r["Ticker"], "Prezzo €": r["Prezzo €"], "Quote da Comprare": q_buy,
            "Spesa €": spesa_eff, "Nuovo Peso %": ((r["Controvalore €"] + spesa_eff) / nuovo_tot_pac) * 100.0, "Target %": r["Target %"]
        })
    df_pac = pd.DataFrame(pac_rows)
    st.dataframe(df_pac.style.format({"Prezzo €": "€ {:.2f}", "Quote da Comprare": "{:,.0f}", "Spesa €": "€ {:,.2f}", "Nuovo Peso %": "{:.2f}%", "Target %": "{:.2f}%"}), use_container_width=True)

# ------------------------------------------------------------------------------
# TAB 5: REGISTRO TRANSAZIONI & ZAINETTO FISCALE
# ------------------------------------------------------------------------------
with tab_tax:
    st.subheader("🧾 Zainetto Fiscale & Transazioni")
    nuovo_z_man = st.number_input("Zainetto Minusvalenze Accumulate (€):", min_value=0.0, value=zainetto_minus, step=50.0)
    if st.button("Salva Zainetto Minusvalenze"):
        all_p[selected_p]["zainetto_minusvalenze"] = nuovo_z_man
        save_data_to_storage(all_p, commit_msg="Aggiornamento manuale zainetto fiscale")
        st.rerun()

    tx_list = curr_data.get("transazioni", [])
    if tx_list:
        st.dataframe(pd.DataFrame(tx_list), use_container_width=True)
    else:
        st.info("Nessuna transazione registrata.")

# ------------------------------------------------------------------------------
# TAB 6: SETUP & STRUMENTI
# ------------------------------------------------------------------------------
with tab_setup:
    st.subheader(f"⚙️ Configurazione: {selected_p}")
    cs1, cs2 = st.columns(2)
    with cs1:
        new_start_dt = st.date_input("Data Inizio:", data_inizio_dt)
    with cs2:
        new_cap_in = st.number_input("Capitale Versato (€):", value=cap_versato, step=500.0)

    edited_df = st.data_editor(
        pd.DataFrame(posizioni), num_rows="dynamic", use_container_width=True,
        column_config={
            "ticker": st.column_config.TextColumn("Ticker Yahoo", required=True),
            "nome": st.column_config.TextColumn("Nome"),
            "target": st.column_config.NumberColumn("Target %", min_value=0.0, max_value=100.0, step=0.5, required=True),
            "tolleranza": st.column_config.NumberColumn("Banda (±%)", min_value=0.1, max_value=25.0, step=0.5, required=True),
            "quote": st.column_config.NumberColumn("Quote", min_value=0, step=1, required=True),
            "pmc": st.column_config.NumberColumn("PMC (€)", min_value=0.0, step=0.01, format="€ %.2f", required=True),
        }
    )
    if st.button("💾 Salva e Fai Commit su GitHub", type="primary", use_container_width=True):
        cleaned = []
        for _, r in edited_df.iterrows():
            if pd.notna(r.get("ticker")) and str(r.get("ticker")).strip() != "":
                cleaned.append({
                    "ticker": str(r["ticker"]).strip().upper(),
                    "nome": str(r.get("nome") or r["ticker"]).strip(),
                    "target": float(r.get("target") or 0.0),
                    "tolleranza": float(r.get("tolleranza") or 2.5),
                    "quote": float(r.get("quote") or 0),
                    "pmc": float(r.get("pmc") or 0.0)
                })
        all_p[selected_p]["data_inizio"] = str(new_start_dt)
        all_p[selected_p]["capitale_iniziale_versato"] = float(new_cap_in)
        all_p[selected_p]["posizioni"] = cleaned
        ok, msg = save_data_to_storage(all_p, commit_msg=f"Setup aggiornato per {selected_p}")
        st.cache_data.clear()
        if ok:
            st.success(msg)
        else:
            st.error(msg)
        st.rerun()

# ------------------------------------------------------------------------------
# TAB 7: DATABASE GITHUB & BACKUP LOCALE
# ------------------------------------------------------------------------------
with tab_cloud:
    st.subheader("☁️ Stato Sincronizzazione GitHub & Esportazione Locale")
    st.write(f"Modalità di persistenza attiva: **{st.session_state.get('storage_mode')}**")
    
    if st.button("🚀 Forza Commit Immediato su GitHub", use_container_width=True):
        ok, msg = save_data_to_storage(all_p, commit_msg="Sync manuale forzato dall'utente")
        if ok:
            st.success(msg)
        else:
            st.error(msg)

    st.divider()
    b1, b2 = st.columns(2)
    with b1:
        st.download_button(
            "⬇️ Scarica Copia JSON sul Telefono/PC",
            data=json.dumps(all_p, indent=4, ensure_ascii=False),
            file_name=f"portfolios_backup_{datetime.date.today()}.json",
            mime="application/json", use_container_width=True
        )
    with b2:
        up_file = st.file_uploader("⬆️ Ripristina da file JSON:", type=["json"])
        if up_file is not None and st.button("Conferma Ripristino e Commit", use_container_width=True):
            all_p.update(json.load(up_file))
            save_data_to_storage(all_p, commit_msg="Ripristino da backup JSON esterno")
            st.success("Backup ripristinato e inviato a GitHub!")
            st.rerun()