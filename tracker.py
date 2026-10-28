"""
================================================================================
INTESTAZIONE:
Quant Portfolio Tracker, Band Rebalancer & Multi-Portfolio Comparator (v3.0)
Applicazione web in Streamlit ottimizzata per Pixel 10 Pro e Desktop.

Caratteristiche tecniche:
- Persistenza Cloud Sicura: Auto-commit su GitHub REST API con crittografia
  simmetrica AES-256 (Fernet) e fallback automatico su file JSON locale.
- Motore Fiscale Italiano: Gestione aliquote 12,5% (Gov White-List) e 26%
  (ETF OICR vs ETC/Azioni), Zainetto Minusvalenze con compensazione automatica
  dei Redditi Diversi e accredito netto sul conto Liquidità (Cash).
- Operatività Completa: Monitoraggio bande di oscillazione con Corridor Chart,
  esecuzione ordini a banda, compravendite estemporanee manuali e Smart PAC
  con applicazione diretta al portafoglio.
- Dashboard Quantitativa & Confronto: 12 metriche istituzionali (CAGR, Volatilità,
  Downside Dev, Sharpe, Sortino, Calmar, Max DD, Ulcer Index, VaR/CVaR 95%,
  Beta, Alpha), Heatmap mensile CSS nativa, Matrice di Correlazione e
  comparazione Head-to-Head multi-portafoglio (Base 100, Drawdown, Rischio/Rend).
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
from cryptography.fernet import Fernet

DATA_FILENAME = "portfolios_data.json"

# ==============================================================================
# 1. CONFIGURAZIONE PAGINA & CSS MOBILE-FIRST (PIXEL 10 PRO)
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
        padding-top: 1.1rem !important;
        padding-bottom: 2.5rem !important;
        padding-left: 0.8rem !important;
        padding-right: 0.8rem !important;
    }
    
    /* Bento Grid Responsiva: 2 col su Smartphone, 3 su Tablet, 6 su Desktop */
    .bento-grid {
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 10px;
        margin-bottom: 16px;
    }
    @media (min-width: 768px) { .bento-grid { grid-template-columns: repeat(3, 1fr); } }
    @media (min-width: 1200px) { .bento-grid { grid-template-columns: repeat(6, 1fr); } }
    
    .bento-card {
        background: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 12px 14px;
        box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
    }
    .bento-label {
        font-size: 0.74rem;
        font-weight: 600;
        color: #64748B;
        text-transform: uppercase;
        letter-spacing: 0.03em;
        margin-bottom: 4px;
    }
    .bento-value {
        font-size: 1.20rem;
        font-weight: 800;
        color: #0F172A;
        line-height: 1.2;
    }
    .bento-sub {
        font-size: 0.77rem;
        font-weight: 600;
        margin-top: 4px;
    }
    
    .pos-delta { color: #16A34A; }
    .neg-delta { color: #DC2626; }
    .neu-delta { color: #475569; }

    /* Asset Card Mobile */
    .asset-card {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 12px 14px;
        margin-bottom: 10px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.03);
    }
    .badge-ok { background: #DCFCE7; color: #166534; padding: 3px 8px; border-radius: 6px; font-weight: 700; font-size: 0.74rem; }
    .badge-warn { background: #FEF3C7; color: #92400E; padding: 3px 8px; border-radius: 6px; font-weight: 700; font-size: 0.74rem; }
    .badge-alert { background: #FEE2E2; color: #991B1B; padding: 3px 8px; border-radius: 6px; font-weight: 700; font-size: 0.74rem; }

    /* Tabs Orizzontali Scorrevoli su Touchscreen */
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
        font-size: 0.87rem;
    }
    .stTabs [aria-selected="true"] {
        background-color: #0F172A !important;
        color: #FFFFFF !important;
    }
</style>
"""
st.markdown(MOBILE_AND_CLOUD_CSS, unsafe_allow_html=True)

# ==============================================================================
# 2. FUNZIONI DI UTILITÀ E SICUREZZA (PIN & DATE PARSING)
# ==============================================================================
def safe_parse_date(date_val, default_str: str = "2024-01-02") -> tuple[str, datetime.date]:
    """Valida e converte qualsiasi data in stringa YYYY-MM-DD e oggetto datetime.date."""
    if isinstance(date_val, datetime.date):
        return date_val.strftime("%Y-%m-%d"), date_val
    try:
        s = str(date_val).strip()[:10]
        dt = datetime.datetime.strptime(s, "%Y-%m-%d").date()
        return s, dt
    except Exception:
        dt = datetime.datetime.strptime(default_str, "%Y-%m-%d").date()
        return default_str, dt

def style_heatmap_cell(val):
    """Colorazione CSS nativa per tabelle di rendimento (elimina la dipendenza da matplotlib)."""
    if pd.isna(val) or not isinstance(val, (int, float, np.number)):
        return "color: #94A3B8;"
    if val > 0:
        alpha = min(0.80, max(0.12, float(val) / 10.0))
        text_col = "#FFFFFF" if alpha > 0.50 else "#064E3B"
        return f"background-color: rgba(22, 163, 74, {alpha:.2f}); color: {text_col}; font-weight: 600;"
    elif val < 0:
        alpha = min(0.80, max(0.12, abs(float(val)) / 10.0))
        text_col = "#FFFFFF" if alpha > 0.50 else "#7F1D1D"
        return f"background-color: rgba(220, 38, 38, {alpha:.2f}); color: {text_col}; font-weight: 600;"
    return ""

def check_pin_authentication() -> bool:
    """Verifica il PIN di accesso se configurato in st.secrets['app_pin']."""
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
# 3. PERSISTENZA SU GITHUB REST API & CRITTOGRAFIA AES-256 (FERNET)
# ==============================================================================
def get_cipher():
    """Restituisce l'oggetto Fernet se encryption_key è valida nei Secrets."""
    try:
        key = str(st.secrets.get("encryption_key", "")).strip() if "encryption_key" in st.secrets else ""
        return Fernet(key.encode("utf-8")) if key else None
    except Exception:
        return None

def get_github_config():
    """Recupera token, repo e branch GitHub da st.secrets."""
    try:
        token = str(st.secrets.get("github_token", "")).strip() if "github_token" in st.secrets else ""
        repo = str(st.secrets.get("github_repo", "")).strip() if "github_repo" in st.secrets else ""
        branch = str(st.secrets.get("github_branch", "main")).strip() if "github_branch" in st.secrets else "main"
        return {"token": token, "repo": repo, "branch": branch} if (token and repo) else None
    except Exception:
        return None

def get_default_portfolios() -> dict:
    return {
        "P1 - Core & Satellites": {
            "data_inizio": "2024-01-02",
            "capitale_iniziale_versato": 50000.0,
            "cash": 3500.0,
            "tasse_totali_pagate": 0.0,
            "zainetto_minusvalenze": 0.0,
            "posizioni": [
                {"ticker": "SWDA.MI", "nome": "MSCI World Core", "target": 50.0, "tolleranza": 5.0, "quote": 120, "pmc": 86.20},
                {"ticker": "SXRM.DE", "nome": "Treasury 7-10y (Gov)", "target": 30.0, "tolleranza": 4.0, "quote": 300, "pmc": 26.50},
                {"ticker": "4GLD.DE", "nome": "Physical Gold ETC", "target": 10.0, "tolleranza": 2.5, "quote": 60, "pmc": 70.00},
                {"ticker": "VVSM.DE", "nome": "Semiconductors", "target": 10.0, "tolleranza": 2.5, "quote": 40, "pmc": 115.00}
            ],
            "transazioni": []
        }
    }

def decode_storage_payload(raw_text: str) -> dict:
    """Decodifica un testo JSON sia se cifrato con Fernet sia se in chiaro."""
    cipher = get_cipher()
    text_clean = raw_text.strip()
    if cipher:
        try:
            decrypted = cipher.decrypt(text_clean.encode("utf-8")).decode("utf-8")
            return json.loads(decrypted)
        except Exception:
            pass
    return json.loads(text_clean)

def normalize_portfolios_dict(raw_dict: dict) -> dict:
    """Normalizza e mette in sicurezza la struttura di tutti i portafogli caricati."""
    if not isinstance(raw_dict, dict) or not raw_dict:
        return get_default_portfolios()
    normalized = {}
    for k, val in raw_dict.items():
        if isinstance(val, list):
            normalized[str(k)] = {
                "data_inizio": "2024-01-02",
                "capitale_iniziale_versato": 50000.0,
                "cash": 1000.0,
                "tasse_totali_pagate": 0.0,
                "zainetto_minusvalenze": 0.0,
                "posizioni": val,
                "transazioni": []
            }
        elif isinstance(val, dict):
            d_str, _ = safe_parse_date(val.get("data_inizio", "2024-01-02"))
            pos_clean = []
            for item in val.get("posizioni", []):
                if isinstance(item, dict) and item.get("ticker"):
                    pos_clean.append({
                        "ticker": str(item["ticker"]).strip().upper(),
                        "nome": str(item.get("nome") or item["ticker"]).strip(),
                        "target": float(item.get("target") or 0.0),
                        "tolleranza": max(0.1, float(item.get("tolleranza") or 2.5)),
                        "quote": max(0.0, float(item.get("quote") or 0.0)),
                        "pmc": max(0.0, float(item.get("pmc") or 0.0))
                    })
            normalized[str(k)] = {
                "data_inizio": d_str,
                "capitale_iniziale_versato": max(0.0, float(val.get("capitale_iniziale_versato", 50000.0))),
                "cash": max(0.0, float(val.get("cash", 0.0))),
                "tasse_totali_pagate": max(0.0, float(val.get("tasse_totali_pagate", 0.0))),
                "zainetto_minusvalenze": max(0.0, float(val.get("zainetto_minusvalenze", 0.0))),
                "posizioni": pos_clean,
                "transazioni": list(val.get("transazioni", []))
            }
    return normalized if normalized else get_default_portfolios()

def load_data_from_storage() -> dict:
    gh = get_github_config()
    cipher = get_cipher()

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
                raw_file_str = base64.b64decode(payload["content"]).decode("utf-8")
                data = normalize_portfolios_dict(decode_storage_payload(raw_file_str))
                st.session_state["storage_mode"] = "GitHub Cloud (AES-256)" if cipher else f"GitHub Cloud ({gh['repo']})"
                st.session_state["github_file_sha"] = payload.get("sha")
                return data
            elif resp.status_code == 404:
                st.session_state["storage_mode"] = "GitHub Cloud (Inizializzato)"
                default_d = get_default_portfolios()
                save_data_to_storage(default_d, commit_msg="Inizializzazione database portafogli")
                return default_d
        except Exception as e:
            st.warning(f"Connessione GitHub non disponibile ({e}). Uso copia locale.")

    st.session_state["storage_mode"] = "File Locale (JSON)"
    if os.path.exists(DATA_FILENAME):
        try:
            with open(DATA_FILENAME, "r", encoding="utf-8") as f:
                return normalize_portfolios_dict(decode_storage_payload(f.read()))
        except Exception:
            pass

    return get_default_portfolios()

def save_data_to_storage(data: dict, commit_msg: str = "Aggiornamento portafoglio"):
    norm_data = normalize_portfolios_dict(data)
    st.session_state["all_portfolios"] = norm_data
    json_str = json.dumps(norm_data, indent=4, ensure_ascii=False)
    cipher = get_cipher()
    content_to_save = cipher.encrypt(json_str.encode("utf-8")).decode("utf-8") if cipher else json_str

    try:
        with open(DATA_FILENAME, "w", encoding="utf-8") as f:
            f.write(content_to_save)
    except Exception:
        pass

    gh = get_github_config()
    if gh:
        url = f"https://api.github.com/repos/{gh['repo']}/contents/{DATA_FILENAME}"
        headers = {
            "Authorization": f"Bearer {gh['token']}",
            "Accept": "application/vnd.github.v3+json"
        }
        try:
            sha = None
            get_resp = requests.get(f"{url}?ref={gh['branch']}", headers=headers, timeout=10)
            if get_resp.status_code == 200:
                sha = get_resp.json().get("sha")

            encoded = base64.b64encode(content_to_save.encode("utf-8")).decode("utf-8")
            put_payload = {
                "message": f"{commit_msg} [{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]",
                "content": encoded,
                "branch": gh["branch"]
            }
            if sha:
                put_payload["sha"] = sha

            put_resp = requests.put(url, headers=headers, json=put_payload, timeout=12)
            if put_resp.status_code in (200, 201):
                st.session_state["github_file_sha"] = put_resp.json().get("content", {}).get("sha")
                st.session_state["storage_mode"] = "GitHub Cloud (AES-256)" if cipher else f"GitHub Cloud ({gh['repo']})"
                return True, "✅ Dati cifrati e sincronizzati su GitHub!"
            else:
                return False, f"⚠️ Errore commit GitHub ({put_resp.status_code}): {put_resp.text}"
        except Exception as e:
            return False, f"⚠️ Errore di rete verso GitHub: {e}"

    return True, "💾 Salvato in memoria locale."

# ==============================================================================
# 4. MOTORE FISCALE ITALIANO (12.5% GOV, 26% ETF, 26% ETC + ZAINETTO)
# ==============================================================================
GOV_KEYWORDS = [
    "treasury", "sxrm", "dtla", "tlt", "ief", "bil", "btp", "bund",
    "gov", "titoli di stato", "bonos", "oat", "cct", "bot", "dbxoan", "xeon", "ib01"
]
ETC_KEYWORDS = [
    "4gld", "gld", "sgld", "igln", "phau", "gold", "oro", "etc", "etn",
    "physical", "commodity", "wbit", "btce", "silver", "xetra-gold"
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
    controvalore_lordo = float(quote) * float(prezzo)
    costo_fiscale = float(quote) * float(pmc)
    risultato_lordo = controvalore_lordo - costo_fiscale
    profilo = classifica_strumento_fiscale(ticker, nome)
    aliquota = profilo["aliquota"]

    minus_usata, minus_generata, imposta_dovuta, risparmio_fiscale = 0.0, 0.0, 0.0, 0.0

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
# 5. MOTORE QUANTITATIVO (METRICHE E ANALISI SERIE STORICHE)
# ==============================================================================
def compute_quant_metrics(equity_series: pd.Series, rf_annual: float = 0.025, bench_series: pd.Series = None) -> dict:
    if equity_series is None:
        return {}
    s = equity_series.replace([np.inf, -np.inf], np.nan).dropna()
    if len(s) < 5 or s.iloc[0] <= 0:
        return {}

    rets = s.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    if rets.empty:
        return {}

    days = max(1, (s.index[-1] - s.index[0]).days)
    years = days / 365.25
    tot_ret_pct = ((s.iloc[-1] / s.iloc[0]) - 1.0) * 100.0
    cagr_pct = (((s.iloc[-1] / s.iloc[0]) ** (1.0 / years)) - 1.0) * 100.0 if years > 0.08 else tot_ret_pct

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
    calmar = cagr_pct / abs(max_dd_pct) if max_dd_pct < -0.01 else 0.0

    p5 = np.percentile(rets, 5)
    var_95 = float(p5 * 100.0)
    tail_losses = rets[rets <= p5]
    cvar_95 = float(tail_losses.mean() * 100.0) if len(tail_losses) > 0 else var_95

    beta, alpha_pct = np.nan, np.nan
    if bench_series is not None:
        b_clean = bench_series.replace([np.inf, -np.inf], np.nan).dropna()
        if len(b_clean) >= 5:
            b_rets = b_clean.pct_change().dropna()
            aligned = pd.concat([rets, b_rets], axis=1, join="inner").dropna()
            if len(aligned) > 10:
                cov_mat = np.cov(aligned.iloc[:, 0], aligned.iloc[:, 1])
                var_b = cov_mat[1, 1]
                if var_b > 0:
                    beta = float(cov_mat[0, 1] / var_b)
                    b_years = max(1, (aligned.index[-1] - aligned.index[0]).days) / 365.25
                    b_cagr = ((((1.0 + aligned.iloc[:, 1]).prod()) ** (1.0 / b_years)) - 1.0) * 100.0 if b_years > 0.08 else 0.0
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
        "Win Rate %": float((rets > 0).mean() * 100.0),
        "Miglior Giorno %": float(rets.max() * 100.0),
        "Peggior Giorno %": float(rets.min() * 100.0),
        "Beta": beta,
        "Alpha %": alpha_pct,
        "dd_series": dd_pct
    }

def compute_monthly_returns_table(equity_series: pd.Series) -> pd.DataFrame:
    if equity_series is None or equity_series.empty:
        return pd.DataFrame()
    s = equity_series.resample("ME").last().dropna()
    m_rets = s.pct_change().dropna() * 100.0
    if m_rets.empty:
        return pd.DataFrame()

    df_m = pd.DataFrame({"Anno": m_rets.index.year, "Mese": m_rets.index.month, "Ret": m_rets.values})
    pivot = df_m.pivot(index="Anno", columns="Mese", values="Ret").rename(columns={
        1: "Gen", 2: "Feb", 3: "Mar", 4: "Apr", 5: "Mag", 6: "Giu",
        7: "Lug", 8: "Ago", 9: "Set", 10: "Ott", 11: "Nov", 12: "Dic"
    })
    pivot["Totale Anno"] = pd.Series({
        yr: (np.prod(1.0 + grp["Ret"].values / 100.0) - 1.0) * 100.0
        for yr, grp in df_m.groupby("Anno")
    })
    return pivot.sort_index(ascending=False)

# ==============================================================================
# 6. DOWNLOAD DATI YAHOO FINANCE (TIMEZONE & MULTI-INDEX SAFE)
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
        df_close = raw_df[["Close"]].rename(columns={"Close": tickers[0]}) if "Close" in raw_df.columns else raw_df

    if isinstance(df_close, pd.Series):
        df_close = df_close.to_frame(name=tickers[0])

    # Normalizzazione Timezone e raggruppamento per data solare (evita disallineamenti EU/USA)
    df_close = df_close.copy()
    df_close.index = pd.to_datetime(df_close.index).tz_localize(None).normalize()
    df_close = df_close.groupby(df_close.index).last()
    return df_close

@st.cache_data(ttl=300, show_spinner=False)
def fetch_realtime_prices(tickers: list) -> dict:
    prices = {}
    clean_tickers = list(dict.fromkeys([str(t).strip().upper() for t in tickers if t]))
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
                    prices[t] = {"price": float(s.iloc[-1]), "prev_close": float(s.iloc[-1])}
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
    clean_tickers = list(dict.fromkeys([str(t).strip().upper() for t in tickers if t]))
    if not clean_tickers:
        return pd.DataFrame()
    try:
        raw = yf.download(clean_tickers, start=start_date, progress=False, auto_adjust=True)
        df_close = extract_close_dataframe(raw, clean_tickers)
        return df_close.ffill().bfill().dropna(how="all")
    except Exception:
        return pd.DataFrame()

# ==============================================================================
# 7. INIZIALIZZAZIONE STATO E BARRA SUPERIORE DI CONTROLLO
# ==============================================================================
if "all_portfolios" not in st.session_state:
    st.session_state["all_portfolios"] = load_data_from_storage()

all_p = normalize_portfolios_dict(st.session_state["all_portfolios"])
st.session_state["all_portfolios"] = all_p
p_names = list(all_p.keys())

top_c1, top_c2 = st.columns([3, 1])
with top_c1:
    selected_p = st.selectbox("📂 Portafoglio Attivo:", p_names, index=0)
with top_c2:
    st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
    if st.button("🔄 Sync Live", use_container_width=True):
        st.cache_data.clear()
        st.session_state["all_portfolios"] = load_data_from_storage()
        st.rerun()

curr_data = all_p[selected_p]
port_cash = float(curr_data.get("cash", 0.0))

with st.sidebar:
    st.title("🎛️ Settings & Cassa")
    mode_lbl = st.session_state.get("storage_mode", "Locale")
    if "Cloud" in mode_lbl:
        st.success(f"☁️ {mode_lbl}")
    else:
        st.warning(f"💾 {mode_lbl}")

    rf_rate_pct = st.number_input("Tasso Risk-Free Annuo (%):", min_value=0.0, max_value=10.0, value=2.50, step=0.25)
    rf_rate = rf_rate_pct / 100.0

    st.divider()
    st.subheader("💵 Gestione Liquidità")
    cash_mov = st.number_input("Importo (€):", min_value=10.0, max_value=1000000.0, value=1000.0, step=100.0)
    c_in, c_out = st.columns(2)
    with c_in:
        if st.button("Deposita", use_container_width=True):
            all_p[selected_p]["cash"] = port_cash + cash_mov
            all_p[selected_p]["capitale_iniziale_versato"] = float(curr_data.get("capitale_iniziale_versato", 0.0)) + cash_mov
            all_p[selected_p]["transazioni"].append({
                "data": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                "tipo": "DEPOSITO_CASH", "ticker": "CASH", "quote": 0, "prezzo": 1.0,
                "lordo": cash_mov, "plusvalenza": 0.0, "tassa_pagata": 0.0, "netto_incassato": cash_mov
            })
            save_data_to_storage(all_p, f"Deposito Cash su {selected_p}")
            st.rerun()
    with c_out:
        if st.button("Preleva", use_container_width=True):
            if cash_mov <= port_cash:
                all_p[selected_p]["cash"] = port_cash - cash_mov
                all_p[selected_p]["capitale_iniziale_versato"] = max(0.0, float(curr_data.get("capitale_iniziale_versato", 0.0)) - cash_mov)
                all_p[selected_p]["transazioni"].append({
                    "data": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "tipo": "PRELIEVO_CASH", "ticker": "CASH", "quote": 0, "prezzo": 1.0,
                    "lordo": cash_mov, "plusvalenza": 0.0, "tassa_pagata": 0.0, "netto_incassato": -cash_mov
                })
                save_data_to_storage(all_p, f"Prelievo Cash da {selected_p}")
                st.rerun()
            else:
                st.error("Cash disponibile insufficiente.")

    st.divider()
    with st.expander("➕ Nuovo / Duplica Portafoglio"):
        new_p_name = st.text_input("Nome Nuovo Portafoglio:").strip()
        clone_from = st.selectbox("Copia struttura da:", ["Vuoto Base"] + p_names)
        new_cap = st.number_input("Capitale Versato (€):", value=50000.0, step=1000.0)
        if st.button("Crea Portafoglio", use_container_width=True):
            if new_p_name and new_p_name not in all_p:
                cloned_pos = copy.deepcopy(all_p[clone_from]["posizioni"]) if clone_from != "Vuoto Base" else [
                    {"ticker": "SWDA.MI", "nome": "MSCI World", "target": 60.0, "tolleranza": 5.0, "quote": 100, "pmc": 85.00},
                    {"ticker": "SXRM.DE", "nome": "Treasury 7-10yr", "target": 40.0, "tolleranza": 5.0, "quote": 200, "pmc": 27.00}
                ]
                all_p[new_p_name] = {
                    "data_inizio": datetime.date.today().strftime("%Y-%m-%d"),
                    "capitale_iniziale_versato": new_cap, "cash": 1000.0,
                    "tasse_totali_pagate": 0.0, "zainetto_minusvalenze": 0.0,
                    "posizioni": cloned_pos, "transazioni": []
                }
                save_data_to_storage(all_p, f"Creato portafoglio {new_p_name}")
                st.rerun()
            else:
                st.warning("Inserisci un nome valido e non duplicato.")

    with st.expander("✏️ Rinomina / Elimina"):
        ren_val = st.text_input("Rinomina in:", value=selected_p).strip()
        cr1, cr2 = st.columns(2)
        with cr1:
            if st.button("Rinomina", use_container_width=True):
                if ren_val and ren_val != selected_p and ren_val not in all_p:
                    all_p[ren_val] = all_p.pop(selected_p)
                    save_data_to_storage(all_p, f"Rinominato {selected_p} in {ren_val}")
                    st.rerun()
        with cr2:
            if st.button("Elimina 🗑️", use_container_width=True):
                if len(all_p) > 1:
                    all_p.pop(selected_p)
                    save_data_to_storage(all_p, f"Eliminato {selected_p}")
                    st.rerun()
                else:
                    st.error("Deve rimanere almeno un portafoglio.")

# ==============================================================================
# 8. ELABORAZIONE POSIZIONI & BENTO GRID SUPERIORE
# ==============================================================================
posizioni = curr_data.get("posizioni", [])
tickers = [p["ticker"] for p in posizioni if p.get("ticker")]

with st.spinner("Aggiornamento quotazioni in tempo reale..."):
    prezzi_info = fetch_realtime_prices(tickers)

righe_tabella = []
valore_totale_strumenti, valore_totale_ieri, daily_pnl_totale_eur = 0.0, 0.0, 0.0
plusvalenze_latenti_totali, imposta_latente_stimata = 0.0, 0.0
zainetto_minus = float(curr_data.get("zainetto_minusvalenze", 0.0))

for p in posizioni:
    tk = p["ticker"]
    nome = p.get("nome", tk)
    target = float(p.get("target", 0.0))
    toll = max(0.1, float(p.get("tolleranza", 2.0)))
    quote = float(p.get("quote", 0.0))
    pmc = float(p.get("pmc", 0.0))

    q_info = prezzi_info.get(tk, {"price": 0.0, "prev_close": 0.0})
    prezzo = q_info["price"] if q_info["price"] > 0 else pmc
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
    for col in ["Ticker", "Nome", "Regime Fiscale", "Stato"]:
        df_pos[col] = ""
    for col in ["Quote", "PMC €", "Prezzo €", "Var. Oggi %", "Var. Oggi €", "Controvalore €",
                "P&L Latente €", "P&L %", "Target %", "Tolleranza %", "Peso Attuale %",
                "Scostamento %", "Utilizzo Banda %", "Azione €", "Azione Quote"]:
        df_pos[col] = 0.0
    df_pos["Fuori Banda"] = False

# Calcolo KPI Globali e Date Sicure
cap_versato = float(curr_data.get("capitale_iniziale_versato", valore_portafoglio_totale))
data_inizio_str, data_inizio_dt = safe_parse_date(curr_data.get("data_inizio", "2024-01-02"))
giorni_inv = max(1, (datetime.date.today() - data_inizio_dt).days)
anni_inv = giorni_inv / 365.25

pnl_netto_eur = valore_portafoglio_totale - cap_versato
pnl_netto_pct = (pnl_netto_eur / cap_versato * 100.0) if cap_versato > 0 else 0.0
cagr_effettivo = (((valore_portafoglio_totale / cap_versato) ** (1.0 / anni_inv)) - 1.0) * 100.0 if (cap_versato > 0 and anni_inv > 0.08 and valore_portafoglio_totale > 0) else pnl_netto_pct
tasse_pagate = float(curr_data.get("tasse_totali_pagate", 0.0))
cash_pct = (port_cash / valore_portafoglio_totale * 100.0) if valore_portafoglio_totale > 0 else 0.0

c_oggi = "pos-delta" if daily_pnl_totale_eur >= 0 else "neg-delta"
c_storico = "pos-delta" if pnl_netto_eur >= 0 else "neg-delta"
c_lat = "pos-delta" if plusvalenze_latenti_totali >= 0 else "neg-delta"

st.markdown(f"""
<div class="bento-grid">
    <div class="bento-card"><div class="bento-label">Patrimonio Totale</div><div class="bento-value">€ {valore_portafoglio_totale:,.2f}</div><div class="bento-sub neu-delta">Cash: € {port_cash:,.0f} ({cash_pct:.1f}%)</div></div>
    <div class="bento-card"><div class="bento-label">Performance Oggi</div><div class="bento-value {c_oggi}">€ {daily_pnl_totale_eur:+,.2f}</div><div class="bento-sub {c_oggi}">{daily_pnl_totale_pct:+.2f}% intraday</div></div>
    <div class="bento-card"><div class="bento-label">P&L Storico Reale</div><div class="bento-value {c_storico}">€ {pnl_netto_eur:+,.2f}</div><div class="bento-sub {c_storico}">{pnl_netto_pct:+.2f}% su versato</div></div>
    <div class="bento-card"><div class="bento-label">CAGR Effettivo</div><div class="bento-value">{cagr_effettivo:.2f}%</div><div class="bento-sub neu-delta">Da {data_inizio_str} ({anni_inv:.1f}a)</div></div>
    <div class="bento-card"><div class="bento-label">P&L Latente Lordo</div><div class="bento-value {c_lat}">€ {plusvalenze_latenti_totali:+,.2f}</div><div class="bento-sub neu-delta">Netto Fisco: € {valore_portafoglio_totale - imposta_latente_stimata:,.0f}</div></div>
    <div class="bento-card"><div class="bento-label">Fisco & Zainetto</div><div class="bento-value">€ {tasse_pagate:,.2f}</div><div class="bento-sub neu-delta">Minus: € {zainetto_minus:,.0f}</div></div>
</div>
""", unsafe_allow_html=True)

# ==============================================================================
# 9. TABS PRINCIPALI DELL'APPLICAZIONE
# ==============================================================================
t_reb, t_quant, t_comp, t_pac, t_tax, t_setup, t_cloud = st.tabs([
    "⚖️ Operatività", "📊 Quant", "⚔️ Confronto", "💰 Smart PAC", "🧾 Fisco", "⚙️ Setup", "☁️ Backup"
])

# ------------------------------------------------------------------------------
# TAB 1: RIBILANCIAMENTO A BANDE & OPERATIVITÀ MANUALE
# ------------------------------------------------------------------------------
with t_reb:
    if df_pos.empty or not tickers:
        st.info("Nessuno strumento presente in questo portafoglio. Vai nella scheda '⚙️ Setup' per aggiungere i tuoi ETF.")
    else:
        v_opt = st.radio("Formato visualizzazione:", ["📱 Mobile Cards", "🖥️ Tabella Completa"], horizontal=True)
        if "Mobile" in v_opt:
            for _, r in df_pos.iterrows():
                bdg = "badge-alert" if r["Fuori Banda"] else ("badge-warn" if "VICINO" in r["Stato"] else "badge-ok")
                c_d = "pos-delta" if r["Var. Oggi %"] >= 0 else "neg-delta"
                c_p = "pos-delta" if r["P&L %"] >= 0 else "neg-delta"
                az = f"Compra {r['Azione Quote']:+,.0f} q (€ {abs(r['Azione €']):,.0f})" if r["Azione Quote"] > 0 else (
                    f"Vendi {abs(r['Azione Quote']):,.0f} q (€ {abs(r['Azione €']):,.0f})" if r["Azione Quote"] < 0 else "Allineato"
                )
                st.markdown(f"""
                <div class="asset-card">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
                        <div><b>{r['Ticker']}</b> <span style="color:#64748B;font-size:0.85rem;">• {r['Nome']}</span></div>
                        <span class="{bdg}">{r['Stato']}</span>
                    </div>
                    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:6px;font-size:0.84rem;">
                        <div>Prezzo: <b>€ {r['Prezzo €']:.2f}</b> <span class="{c_d}">({r['Var. Oggi %']:+.2f}%)</span></div>
                        <div>Valore: <b>€ {r['Controvalore €']:,.0f}</b> ({r['Quote']:.0f} q)</div>
                        <div>P&L: <b class="{c_p}">{r['P&L %']:+.1f}%</b> (PMC €{r['PMC €']:.2f})</div>
                        <div>Peso: <b>{r['Peso Attuale %']:.1f}%</b> / {r['Target %']:.1f}%</div>
                        <div>Scost.: <b>{r['Scostamento %']:+.2f}%</b> (±{r['Tolleranza %']:.1f}%)</div>
                        <div>Ordine: <b>{az}</b></div>
                    </div>
                </div>""", unsafe_allow_html=True)
        else:
            styled_pos = df_pos[[
                "Ticker", "Nome", "Prezzo €", "Var. Oggi %", "Quote", "PMC €",
                "Controvalore €", "P&L %", "Peso Attuale %", "Target %",
                "Tolleranza %", "Scostamento %", "Stato", "Azione Quote", "Azione €", "Regime Fiscale"
            ]].style.format({
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

        cb_c, cp_c = st.columns([1.6, 1.2])
        with cb_c:
            st.markdown("##### 🎯 Corridor Chart: Scostamento % rispetto alle Bande")
            fig_b = go.Figure()
            fig_b.add_trace(go.Bar(y=df_pos["Ticker"], x=df_pos["Tolleranza %"], orientation='h', marker=dict(color='rgba(148,163,184,0.25)', line=dict(color='#64748B', width=1))))
            fig_b.add_trace(go.Bar(y=df_pos["Ticker"], x=-df_pos["Tolleranza %"], orientation='h', marker=dict(color='rgba(148,163,184,0.25)', line=dict(color='#64748B', width=1))))
            c_s = ["#DC2626" if fb else "#16A34A" for fb in df_pos["Fuori Banda"]]
            fig_b.add_trace(go.Scatter(
                y=df_pos["Ticker"], x=df_pos["Scostamento %"], mode='markers+text',
                text=[f"{v:+.1f}%" for v in df_pos["Scostamento %"]], textposition="middle right",
                marker=dict(color=c_s, size=11, symbol="diamond")
            ))
            fig_b.update_layout(barmode='overlay', template="plotly_white", height=310, margin=dict(t=10, b=10, l=10, r=35), showlegend=False)
            fig_b.add_vline(x=0, line_width=1.5, line_dash="dash", line_color="#0F172A")
            st.plotly_chart(fig_b, use_container_width=True)

        with cp_c:
            st.markdown("##### 🍩 Allocazione Effettiva")
            fig_p = go.Figure(data=[go.Pie(
                labels=list(df_pos["Ticker"]) + ["CASH"],
                values=list(df_pos["Controvalore €"]) + [port_cash],
                hole=0.55, textinfo="label+percent", marker=dict(colors=px.colors.qualitative.Prism)
            )])
            fig_p.update_layout(height=310, margin=dict(t=10, b=10, l=10, r=10), showlegend=False)
            st.plotly_chart(fig_p, use_container_width=True)

        st.divider()
        st.subheader("⚡ Ordini di Ribilanciamento a Banda")
        oob = df_pos[df_pos["Fuori Banda"]].to_dict("records")
        if oob:
            for item in oob:
                tk, nome, q_act, pr, pmc_i = item["Ticker"], item["Nome"], item["Azione Quote"], item["Prezzo €"], item["PMC €"]
                c1, c2 = st.columns([3, 1])
                if q_act < 0:
                    qs = abs(q_act)
                    sim = calcola_vendita_fiscale(tk, nome, qs, pr, pmc_i, zainetto_minus)
                    c1.markdown(f"🔴 **VENDI `{tk}`**: **{qs}** quote a **€ {pr:.2f}** • Tassa: € {sim['imposta_dovuta']:,.2f} ➡️ **Netto su Cash: € {sim['incasso_netto']:,.2f}**")
                    if c2.button(f"Vendi {tk}", key=f"bs_{tk}", use_container_width=True):
                        for p in posizioni:
                            if p["ticker"] == tk:
                                p["quote"] = max(0.0, float(p["quote"]) - qs)
                        all_p[selected_p]["cash"] = port_cash + sim["incasso_netto"]
                        all_p[selected_p]["tasse_totali_pagate"] = tasse_pagate + sim["imposta_dovuta"]
                        all_p[selected_p]["zainetto_minusvalenze"] = sim["nuovo_zainetto"]
                        all_p[selected_p]["transazioni"].append({
                            "data": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "tipo": "VENDITA_BANDA", "ticker": tk, "quote": qs, "prezzo": pr, "pmc": pmc_i,
                            "lordo": sim["controvalore_lordo"], "plusvalenza": sim["plusvalenza"],
                            "minus_compensata": sim["minus_usata"], "tassa_pagata": sim["imposta_dovuta"],
                            "netto_incassato": sim["incasso_netto"]
                        })
                        save_data_to_storage(all_p, f"Vendita a banda {tk}")
                        st.rerun()
                elif q_act > 0:
                    costo_b = q_act * pr
                    c1.markdown(f"🟢 **COMPRA `{tk}`**: **{q_act}** quote a **€ {pr:.2f}** • Spesa: **€ {costo_b:,.2f}** (Cash: € {port_cash:,.2f})")
                    if c2.button(f"Compra {tk}", key=f"bb_{tk}", use_container_width=True):
                        if costo_b > port_cash:
                            st.error("Cash insufficiente. Esegui prima una vendita o deposita liquidità.")
                        else:
                            for p in posizioni:
                                if p["ticker"] == tk:
                                    nq = float(p["quote"]) + q_act
                                    p["pmc"] = round(((float(p["quote"]) * float(p["pmc"])) + costo_b) / nq, 4)
                                    p["quote"] = nq
                            all_p[selected_p]["cash"] = port_cash - costo_b
                            all_p[selected_p]["transazioni"].append({
                                "data": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                                "tipo": "ACQUISTO_BANDA", "ticker": tk, "quote": q_act, "prezzo": pr, "pmc": pr,
                                "lordo": costo_b, "plusvalenza": 0.0, "minus_compensata": 0.0,
                                "tassa_pagata": 0.0, "netto_incassato": -costo_b
                            })
                            save_data_to_storage(all_p, f"Acquisto a banda {tk}")
                            st.rerun()
        else:
            st.success("🎯 Tutti gli strumenti sono all'interno delle bande di tolleranza.")

        with st.expander("🛠️ Compravendita Estemporanea Manuale"):
            c1, c2, c3, c4 = st.columns([1.4, 1.2, 1.0, 1.0])
            with c1:
                etf_sel = st.selectbox("Strumento:", tickers, key="m_etf")
            a_obj = next((i for i in posizioni if i["ticker"] == etf_sel), None)
            p_mkt = prezzi_info.get(etf_sel, {}).get("price", 0.0)
            q_a = float(a_obj["quote"]) if a_obj else 0.0
            pmc_a = float(a_obj["pmc"]) if a_obj else 0.0
            nm_a = a_obj.get("nome", etf_sel) if a_obj else etf_sel

            with c2:
                t_op = st.radio("Azione:", ["Vendi (-> Cash)", "Compra (Usa Cash)"], horizontal=True)
            with c3:
                max_q = max(1, int(q_a)) if "Vendi" in t_op else 100000
                def_q = min(10, max(1, int(q_a))) if "Vendi" in t_op else 10
                q_m = st.number_input("Quote:", min_value=1, max_value=max_q, value=def_q, step=1)
            with c4:
                p_m = st.number_input("Prezzo (€):", min_value=0.01, value=float(p_mkt) if p_mkt > 0 else max(0.01, pmc_a), step=0.01, format="%.2f")

            if "Vendi" in t_op:
                sim = calcola_vendita_fiscale(etf_sel, nm_a, q_m, p_m, pmc_a, zainetto_minus)
                st.info(
                    f"Lordo: **€ {sim['controvalore_lordo']:,.2f}** | P&L: **€ {sim['plusvalenza']:+,.2f}** | "
                    f"Minus compensata: **€ {sim['minus_usata']:,.2f}** | Imposta: **€ {sim['imposta_dovuta']:,.2f}** ➡️ "
                    f"**Incasso Netto su Cash: € {sim['incasso_netto']:,.2f}**"
                )
                if st.button("🔴 Conferma Vendita Manuale", type="primary", use_container_width=True):
                    if q_m > q_a:
                        st.error("Non possiedi abbastanza quote per questa vendita.")
                    else:
                        a_obj["quote"] = q_a - q_m
                        all_p[selected_p]["cash"] = port_cash + sim["incasso_netto"]
                        all_p[selected_p]["tasse_totali_pagate"] = tasse_pagate + sim["imposta_dovuta"]
                        all_p[selected_p]["zainetto_minusvalenze"] = sim["nuovo_zainetto"]
                        all_p[selected_p]["transazioni"].append({
                            "data": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "tipo": "VENDITA_MANUALE", "ticker": etf_sel, "quote": q_m, "prezzo": p_m,
                            "pmc": pmc_a, "lordo": sim["controvalore_lordo"], "plusvalenza": sim["plusvalenza"],
                            "minus_compensata": sim["minus_usata"], "tassa_pagata": sim["imposta_dovuta"],
                            "netto_incassato": sim["incasso_netto"]
                        })
                        save_data_to_storage(all_p, f"Vendita manuale {etf_sel}")
                        st.rerun()
            else:
                cst = q_m * p_m
                new_q = q_a + q_m
                new_pmc = ((q_a * pmc_a) + cst) / new_q if new_q > 0 else p_m
                st.info(f"Spesa: **€ {cst:,.2f}** | Cash residuo: **€ {port_cash - cst:,.2f}** | Nuovo PMC: **€ {new_pmc:.2f}**")
                if st.button("🟢 Conferma Acquisto Manuale", type="primary", use_container_width=True):
                    if cst > port_cash:
                        st.error("Liquidità in Cash insufficiente.")
                    else:
                        a_obj["quote"] = new_q
                        a_obj["pmc"] = round(new_pmc, 4)
                        all_p[selected_p]["cash"] = port_cash - cst
                        all_p[selected_p]["transazioni"].append({
                            "data": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "tipo": "ACQUISTO_MANUALE", "ticker": etf_sel, "quote": q_m, "prezzo": p_m,
                            "pmc": round(new_pmc, 4), "lordo": cst, "plusvalenza": 0.0,
                            "minus_compensata": 0.0, "tassa_pagata": 0.0, "netto_incassato": -cst
                        })
                        save_data_to_storage(all_p, f"Acquisto manuale {etf_sel}")
                        st.rerun()

# ------------------------------------------------------------------------------
# TAB 2: DASHBOARD QUANTITATIVA (SENZA DIPENDENZA MATPLOTLIB)
# ------------------------------------------------------------------------------
with t_quant:
    cq1, cq2, cq3 = st.columns([1.5, 1.0, 1.0])
    with cq1:
        mod_a = st.radio("Serie Storica:", ["Patrimonio Reale", "Backtest Pesi Target"], horizontal=True)
    with cq2:
        anni_b = st.selectbox("Anni Backtest:", [1, 3, 5, 10], index=2)
    with cq3:
        b_tk = st.selectbox("Benchmark:", ["SWDA.MI", "SPY", "QQQ", "URTH", "SXR8.DE"], index=0)

    sq = data_inizio_str if "Reale" in mod_a else (datetime.date.today() - datetime.timedelta(days=int(anni_b * 365.25))).strftime("%Y-%m-%d")
    dh = fetch_historical_matrix(tickers + [b_tk], start_date=sq)

    if not dh.empty and tickers:
        vt = [t for t in tickers if t in dh.columns]
        if vt:
            if "Reale" in mod_a:
                ps = pd.Series(port_cash, index=dh.index, dtype=float)
                for p in posizioni:
                    if p["ticker"] in dh.columns:
                        ps += dh[p["ticker"]] * float(p["quote"])
            else:
                ra = dh[vt].pct_change().fillna(0.0)
                tw = sum(float(p["target"]) for p in posizioni if p["ticker"] in vt)
                wv = np.array([float(p["target"]) / tw for p in posizioni if p["ticker"] in vt]) if tw > 0 else np.ones(len(vt)) / len(vt)
                ps = (1.0 + ra.dot(wv)).cumprod() * 100.0

            bs = (1.0 + dh[b_tk].pct_change().fillna(0.0)).cumprod() * float(ps.iloc[0]) if (b_tk in dh.columns and len(ps) > 0) else None
            qm = compute_quant_metrics(ps, rf_annual=rf_rate, bench_series=bs)

            if qm:
                beta_str = f"{qm['Beta']:.2f}" if not np.isnan(qm["Beta"]) else "N/D"
                alpha_str = f"{qm['Alpha %']:+.2f}%" if not np.isnan(qm["Alpha %"]) else "N/D"
                st.markdown(f"""
                <div class="bento-grid">
                    <div class="bento-card"><div class="bento-label">CAGR Annuo</div><div class="bento-value">{qm['CAGR %']:.2f}%</div><div class="bento-sub neu-delta">Tot: {qm['Totale %']:+.1f}%</div></div>
                    <div class="bento-card"><div class="bento-label">Volatilità</div><div class="bento-value">{qm['Volatilità %']:.2f}%</div><div class="bento-sub neu-delta">Down: {qm['Downside Dev %']:.2f}%</div></div>
                    <div class="bento-card"><div class="bento-label">Sharpe / Sortino</div><div class="bento-value">{qm['Sharpe']:.2f} / {qm['Sortino']:.2f}</div><div class="bento-sub neu-delta">Rf: {rf_rate_pct:.1f}%</div></div>
                    <div class="bento-card"><div class="bento-label">Max Drawdown</div><div class="bento-value neg-delta">{qm['Max Drawdown %']:.2f}%</div><div class="bento-sub neu-delta">Ulcer: {qm['Ulcer Index']:.2f}</div></div>
                    <div class="bento-card"><div class="bento-label">Calmar / Beta</div><div class="bento-value">{qm['Calmar']:.2f}</div><div class="bento-sub neu-delta">Beta: {beta_str} | α: {alpha_str}</div></div>
                    <div class="bento-card"><div class="bento-label">VaR / CVaR 95%</div><div class="bento-value neg-delta">{qm['VaR 95% (1g)']:.2f}%</div><div class="bento-sub neg-delta">CVaR: {qm['CVaR 95% (1g)']:.2f}%</div></div>
                </div>""", unsafe_allow_html=True)

                fe = go.Figure()
                fe.add_trace(go.Scatter(x=ps.index, y=ps, mode="lines", name=selected_p, line=dict(color="#2563EB", width=2.5)))
                if bs is not None:
                    fe.add_trace(go.Scatter(x=bs.index, y=bs, mode="lines", name=f"Benchmark ({b_tk})", line=dict(color="#94A3B8", width=1.6, dash="dot")))
                fe.update_layout(title="Equity Curve Storica", template="plotly_white", hovermode="x unified", height=340, margin=dict(t=35, b=10, l=10, r=10))
                st.plotly_chart(fe, use_container_width=True)

                fd = go.Figure()
                fd.add_trace(go.Scatter(x=qm["dd_series"].index, y=qm["dd_series"], mode="lines", fill="tozeroy", name="Drawdown %", line=dict(color="#DC2626", width=1.5), fillcolor="rgba(220,38,38,0.15)"))
                fd.update_layout(title="Underwater Drawdown (%)", template="plotly_white", height=230, margin=dict(t=35, b=10, l=10, r=10))
                st.plotly_chart(fd, use_container_width=True)

                st.markdown("##### 📅 Heatmap dei Rendimenti Mensili e Annuali (%)")
                df_m = compute_monthly_returns_table(ps)
                if not df_m.empty:
                    st.dataframe(
                        df_m.style.format("{:+.2f}%", na_rep="-").map(style_heatmap_cell),
                        use_container_width=True
                    )

                if len(vt) > 1:
                    st.markdown("##### 🔗 Matrice di Correlazione tra gli ETF")
                    fig_c = px.imshow(dh[vt].pct_change().dropna().corr(), text_auto=".2f", color_continuous_scale="RdBu_r", zmin=-1, zmax=1, aspect="auto")
                    fig_c.update_layout(height=320, margin=dict(t=10, b=10, l=10, r=10), coloraxis_showscale=False)
                    st.plotly_chart(fig_c, use_container_width=True)

# ------------------------------------------------------------------------------
# TAB 3: CONFRONTO MULTI-PORTAFOGLIO (HEAD-TO-HEAD COMPLETO)
# ------------------------------------------------------------------------------
with t_comp:
    st.subheader("⚔️ Confronto Multi-Portafoglio (Head-to-Head)")
    cc1, cc2, cc3, cc4 = st.columns([1.6, 1.2, 1.0, 1.0])
    with cc1:
        sel_c = st.multiselect("Portafogli:", p_names, default=p_names)
    with cc2:
        mod_c = st.radio("Metodo:", ["Pesi Target", "Quote Reali"], horizontal=True)
    with cc3:
        yrs_c = st.selectbox("Orizzonte (Anni):", [1, 3, 5, 10], index=1)
    with cc4:
        comp_bench = st.selectbox("Benchmark:", ["Nessuno", "SWDA.MI", "SPY", "QQQ"], index=1)

    if sel_c:
        sc = (datetime.date.today() - datetime.timedelta(days=int(yrs_c * 365.25))).strftime("%Y-%m-%d")
        act = {i["ticker"] for pn in sel_c for i in all_p[pn].get("posizioni", []) if i.get("ticker")}
        if comp_bench != "Nessuno":
            act.add(comp_bench)
        dhc = fetch_historical_matrix(list(act), start_date=sc)

        if not dhc.empty:
            ra_c = dhc.pct_change().fillna(0.0)
            cdict, mcomp = {}, []

            for pn in sel_c:
                plist = [x for x in all_p[pn].get("posizioni", []) if x.get("ticker") in dhc.columns]
                if not plist:
                    continue
                if "Target" in mod_c:
                    tt = sum(float(x["target"]) for x in plist)
                    ws = {x["ticker"]: (float(x["target"]) / tt if tt > 0 else 1.0 / len(plist)) for x in plist}
                    pr = sum(ra_c[tk] * w for tk, w in ws.items())
                    ec = (1.0 + pr).cumprod() * 100.0
                else:
                    vs = pd.Series(float(all_p[pn].get("cash", 0.0)), index=dhc.index, dtype=float)
                    for x in plist:
                        vs += dhc[x["ticker"]] * float(x["quote"])
                    ec = (vs / vs.iloc[0]) * 100.0 if vs.iloc[0] > 0 else vs

                cdict[pn] = ec
                mres = compute_quant_metrics(ec, rf_annual=rf_rate)
                if mres:
                    mcomp.append({
                        "Portafoglio": pn, "CAGR %": mres["CAGR %"], "Totale %": mres["Totale %"],
                        "Volatilità %": mres["Volatilità %"], "Max DD %": mres["Max Drawdown %"],
                        "Sharpe": mres["Sharpe"], "Sortino": mres["Sortino"],
                        "Calmar": mres["Calmar"], "Ulcer Index": mres["Ulcer Index"]
                    })

            if comp_bench != "Nessuno" and comp_bench in ra_c.columns:
                bc_s = (1.0 + ra_c[comp_bench]).cumprod() * 100.0
                b_name = f"Bench ({comp_bench})"
                cdict[b_name] = bc_s
                bm_res = compute_quant_metrics(bc_s, rf_annual=rf_rate)
                if bm_res:
                    mcomp.append({
                        "Portafoglio": b_name, "CAGR %": bm_res["CAGR %"], "Totale %": bm_res["Totale %"],
                        "Volatilità %": bm_res["Volatilità %"], "Max DD %": bm_res["Max Drawdown %"],
                        "Sharpe": bm_res["Sharpe"], "Sortino": bm_res["Sortino"],
                        "Calmar": bm_res["Calmar"], "Ulcer Index": bm_res["Ulcer Index"]
                    })

            if mcomp:
                df_mc = pd.DataFrame(mcomp).set_index("Portafoglio")
                st.dataframe(
                    df_mc.style.format({
                        "CAGR %": "{:+.2f}%", "Totale %": "{:+.2f}%", "Volatilità %": "{:.2f}%",
                        "Max DD %": "{:.2f}%", "Sharpe": "{:.2f}", "Sortino": "{:.2f}",
                        "Calmar": "{:.2f}", "Ulcer Index": "{:.2f}"
                    }).highlight_max(subset=["CAGR %", "Totale %", "Sharpe", "Sortino", "Calmar"], color="#DCFCE7")
                      .highlight_min(subset=["Volatilità %", "Ulcer Index"], color="#DCFCE7"),
                    use_container_width=True
                )

                fm = go.Figure()
                for nc, s in cdict.items():
                    fm.add_trace(go.Scatter(x=s.index, y=s, mode="lines", name=nc, line=dict(width=2.4, dash="dot" if "Bench" in nc else "solid")))
                fm.update_layout(title="Equity Curve Comparata (Base 100)", template="plotly_white", hovermode="x unified", height=350, margin=dict(t=35, b=10))
                st.plotly_chart(fm, use_container_width=True)

                f_dd_m = go.Figure()
                for nc, s in cdict.items():
                    dd_s = ((s - s.cummax()) / s.cummax()) * 100.0
                    f_dd_m.add_trace(go.Scatter(x=dd_s.index, y=dd_s, mode="lines", name=nc, line=dict(width=1.8, dash="dot" if "Bench" in nc else "solid")))
                f_dd_m.update_layout(title="Confronto Underwater Drawdown (%)", template="plotly_white", hovermode="x unified", height=250, margin=dict(t=35, b=10))
                st.plotly_chart(f_dd_m, use_container_width=True)

# ------------------------------------------------------------------------------
# TAB 4: SMART PAC (CON PULSANTE DI ESECUZIONE DIRETTA)
# ------------------------------------------------------------------------------
with t_pac:
    st.subheader("💡 Smart PAC (Ribilanciamento tramite Nuovi Versamenti)")
    c_pac = st.number_input("Nuova liquidità PAC da investire (€):", min_value=50.0, max_value=1000000.0, value=1500.0, step=100.0)

    if not df_pos.empty and tickers:
        nt_pac = valore_portafoglio_totale + c_pac
        gps = [max(0.0, nt_pac * (r["Target %"] / 100.0) - r["Controvalore €"]) for _, r in df_pos.iterrows()]
        sg = sum(gps)

        p_rows = []
        spesa_tot_pac = 0.0
        for i, (_, r) in enumerate(df_pos.iterrows()):
            b = c_pac * (gps[i] / sg) if sg > 0 else c_pac * (r["Target %"] / 100.0)
            qb = int(b // r["Prezzo €"]) if r["Prezzo €"] > 0 else 0
            se = qb * r["Prezzo €"]
            spesa_tot_pac += se
            p_rows.append({
                "Ticker": r["Ticker"], "Prezzo €": r["Prezzo €"], "Da Comprare": qb,
                "Spesa €": se, "Nuovo Peso %": ((r["Controvalore €"] + se) / nt_pac) * 100.0 if nt_pac > 0 else 0.0,
                "Target %": r["Target %"]
            })

        resto_pac = c_pac - spesa_tot_pac
        st.caption(f"Capitale allocato in quote intere: **€ {spesa_tot_pac:,.2f}** • Resto che confluirà nel Cash: **€ {resto_pac:,.2f}**")
        st.dataframe(
            pd.DataFrame(p_rows).style.format({
                "Prezzo €": "€ {:.2f}", "Da Comprare": "{:,.0f}", "Spesa €": "€ {:,.2f}",
                "Nuovo Peso %": "{:.2f}%", "Target %": "{:.2f}%"
            }),
            use_container_width=True
        )

        if st.button("✅ Esegui e Registra Acquisti PAC in Portafoglio", type="primary", use_container_width=True):
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            for row_pac in p_rows:
                q_add = int(row_pac["Da Comprare"])
                if q_add > 0:
                    tk_p = row_pac["Ticker"]
                    pr_p = float(row_pac["Prezzo €"])
                    spesa_p = q_add * pr_p
                    for p in posizioni:
                        if p["ticker"] == tk_p:
                            old_q = float(p["quote"])
                            old_pmc = float(p["pmc"])
                            new_q = old_q + q_add
                            p["pmc"] = round(((old_q * old_pmc) + spesa_p) / new_q, 4)
                            p["quote"] = new_q
                    all_p[selected_p]["transazioni"].append({
                        "data": now_str, "tipo": "ACQUISTO_PAC", "ticker": tk_p,
                        "quote": q_add, "prezzo": pr_p, "pmc": pr_p, "lordo": spesa_p,
                        "plusvalenza": 0.0, "minus_compensata": 0.0, "tassa_pagata": 0.0, "netto_incassato": -spesa_p
                    })
            all_p[selected_p]["capitale_iniziale_versato"] = cap_versato + c_pac
            all_p[selected_p]["cash"] = port_cash + resto_pac
            save_data_to_storage(all_p, f"Esecuzione Smart PAC su {selected_p}")
            st.rerun()

# ------------------------------------------------------------------------------
# TAB 5: REGISTRO FISCALE & STORICO TRANSAZIONI
# ------------------------------------------------------------------------------
with t_tax:
    st.subheader("🧾 Zainetto Minusvalenze & Registro Transazioni")
    ct1, ct2 = st.columns([2, 1])
    with ct1:
        nz = st.number_input("Zainetto Minusvalenze Accumulate (€):", min_value=0.0, value=zainetto_minus, step=50.0)
    with ct2:
        st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
        if st.button("💾 Aggiorna Zainetto", use_container_width=True):
            all_p[selected_p]["zainetto_minusvalenze"] = nz
            save_data_to_storage(all_p, "Aggiornamento manuale zainetto minusvalenze")
            st.rerun()

    tx_list = curr_data.get("transazioni", [])
    if tx_list:
        st.dataframe(pd.DataFrame(tx_list), use_container_width=True)
        if st.button("🗑️ Elimina Ultima Voce dal Registro Transazioni"):
            all_p[selected_p]["transazioni"].pop()
            save_data_to_storage(all_p, "Rimozione ultima voce registro transazioni")
            st.rerun()
    else:
        st.info("Nessuna transazione registrata.")

# ------------------------------------------------------------------------------
# TAB 6: SETUP & CONFIGURAZIONE STRUMENTI
# ------------------------------------------------------------------------------
with t_setup:
    st.subheader(f"⚙️ Configurazione: {selected_p}")
    cs1, cs2, cs3 = st.columns(3)
    with cs1:
        ns_dt = st.date_input("Data Inizio:", data_inizio_dt)
    with cs2:
        nc_in = st.number_input("Capitale Versato (€):", value=cap_versato, step=500.0)
    with cs3:
        somma_t = sum(float(x.get("target", 0.0)) for x in posizioni)
        st.metric("Somma Pesi Target", f"{somma_t:.1f}%", "OK = 100%" if abs(somma_t - 100.0) < 0.1 else "Verifica Somma != 100%")

    df_for_edit = pd.DataFrame(posizioni) if posizioni else pd.DataFrame(columns=["ticker", "nome", "target", "tolleranza", "quote", "pmc"])
    edf = st.data_editor(
        df_for_edit, num_rows="dynamic", use_container_width=True,
        column_config={
            "ticker": st.column_config.TextColumn("Ticker Yahoo", required=True),
            "nome": st.column_config.TextColumn("Nome"),
            "target": st.column_config.NumberColumn("Target %", min_value=0.0, max_value=100.0, step=0.5, required=True),
            "tolleranza": st.column_config.NumberColumn("Banda (±%)", min_value=0.1, max_value=25.0, step=0.5, required=True),
            "quote": st.column_config.NumberColumn("Quote", min_value=0, step=1, required=True),
            "pmc": st.column_config.NumberColumn("PMC (€)", min_value=0.0, step=0.01, format="€ %.2f", required=True),
        }
    )
    if st.button("💾 Salva Portafoglio su Cloud", type="primary", use_container_width=True):
        cleaned = []
        for _, r in edf.iterrows():
            tk_raw = str(r.get("ticker") or "").strip().upper()
            if pd.notna(r.get("ticker")) and tk_raw and tk_raw != "NAN":
                cleaned.append({
                    "ticker": tk_raw,
                    "nome": str(r.get("nome") or tk_raw).strip(),
                    "target": float(r.get("target") or 0.0),
                    "tolleranza": max(0.1, float(r.get("tolleranza") or 2.5)),
                    "quote": max(0.0, float(r.get("quote") or 0.0)),
                    "pmc": max(0.0, float(r.get("pmc") or 0.0))
                })
        all_p[selected_p]["data_inizio"] = str(ns_dt)
        all_p[selected_p]["capitale_iniziale_versato"] = float(nc_in)
        all_p[selected_p]["posizioni"] = cleaned
        ok, msg = save_data_to_storage(all_p, f"Setup aggiornato per {selected_p}")
        st.cache_data.clear()
        if ok:
            st.success(msg)
        else:
            st.error(msg)
        st.rerun()

# ------------------------------------------------------------------------------
# TAB 7: CLOUD & IMPORTAZIONE / ESPORTAZIONE BACKUP JSON
# ------------------------------------------------------------------------------
with t_cloud:
    st.subheader("☁️ Stato Sincronizzazione GitHub & Gestione JSON")
    st.write(f"Modalità attiva: **{st.session_state.get('storage_mode')}**")

    if st.button("🚀 Forza Commit Immediato su GitHub", use_container_width=True):
        ok, msg = save_data_to_storage(all_p, "Sync manuale forzato")
        if ok:
            st.success(msg)
        else:
            st.error(msg)

    st.divider()
    col_dl, col_ul = st.columns(2)
    with col_dl:
        st.markdown("##### ⬇️ Esporta il tuo Database")
        st.download_button(
            "⬇️ Scarica Copia JSON (In Chiaro)",
            data=json.dumps(all_p, indent=4, ensure_ascii=False),
            file_name=f"portfolios_backup_{datetime.date.today()}.json",
            mime="application/json",
            use_container_width=True
        )
    with col_ul:
        st.markdown("##### ⬆️ Importa Portafoglio Esterno (JSON)")
        sovrascrivi = st.checkbox("Sostituisci interamente i portafogli esistenti", value=True)
        up = st.file_uploader("Seleziona file .json:", type=["json"])
        if up is not None and st.button("✅ Conferma Importazione JSON", type="primary", use_container_width=True):
            try:
                raw_up_str = up.read().decode("utf-8")
                imported_dict = normalize_portfolios_dict(decode_storage_payload(raw_up_str))
                if sovrascrivi:
                    all_p = imported_dict
                else:
                    all_p.update(imported_dict)
                ok, msg = save_data_to_storage(all_p, "Importazione da file JSON esterno")
                st.cache_data.clear()
                st.success(f"Portafogli importati correttamente! {msg}")
                st.rerun()
            except Exception as e:
                st.error(f"Impossibile leggere il file JSON caricato: {e}")
