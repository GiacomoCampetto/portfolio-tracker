"""
================================================================================
INTESTAZIONE:
Quant Portfolio Tracker & Comparator - Cloud & Mobile Web App (AES-256 Edition)
Applicazione web professionale in Streamlit ottimizzata per smartphone e desktop.

Architettura e Sicurezza:
- Persistenza Cloud: Auto-commit su repository GitHub tramite REST API (bypass del disco effimero).
- Sicurezza Dati: Crittografia militare AES-256 (Fernet) del JSON prima del salvataggio.
- Accesso: Blocco con PIN di sicurezza (st.secrets).

Funzionalità Core:
- Motore Fiscale IT: Calcolo imposte (12,5% / 26%), compensazione ETC/Azioni con Zainetto.
- Gestione Cash: P&L realizzato accreditato netto sul conto liquidità.
- Operatività: Bande di tolleranza, Corridor Chart, compravendite manuali, Smart PAC.
- Analisi Quant: 12 metriche di rischio, Heatmap mensile, Correlazione, Confronto Portafogli.
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
        padding-top: 1.2rem !important;
        padding-bottom: 2.5rem !important;
        padding-left: 0.8rem !important;
        padding-right: 0.8rem !important;
    }
    
    /* Bento Grid Responsiva */
    .bento-grid {
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 10px;
        margin-bottom: 18px;
    }
    @media (min-width: 768px) { .bento-grid { grid-template-columns: repeat(3, 1fr); } }
    @media (min-width: 1200px) { .bento-grid { grid-template-columns: repeat(6, 1fr); } }
    .bento-card {
        background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 12px;
        padding: 12px 14px; box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
    }
    .bento-label {
        font-size: 0.75rem; font-weight: 600; color: #64748B;
        text-transform: uppercase; letter-spacing: 0.03em; margin-bottom: 4px;
    }
    .bento-value { font-size: 1.22rem; font-weight: 800; color: #0F172A; line-height: 1.2; }
    .bento-sub { font-size: 0.78rem; font-weight: 600; margin-top: 4px; }
    
    .pos-delta { color: #16A34A; }
    .neg-delta { color: #DC2626; }
    .neu-delta { color: #475569; }

    /* Asset Card Mobile */
    .asset-card {
        background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 12px;
        padding: 12px 14px; margin-bottom: 10px; box-shadow: 0 1px 2px rgba(0,0,0,0.03);
    }
    .badge-ok { background: #DCFCE7; color: #166534; padding: 3px 8px; border-radius: 6px; font-weight: 700; font-size: 0.75rem; }
    .badge-warn { background: #FEF3C7; color: #92400E; padding: 3px 8px; border-radius: 6px; font-weight: 700; font-size: 0.75rem; }
    .badge-alert { background: #FEE2E2; color: #991B1B; padding: 3px 8px; border-radius: 6px; font-weight: 700; font-size: 0.75rem; }

    /* Tabs Scorrevoli */
    .stTabs [data-baseweb="tab-list"] {
        gap: 6px; overflow-x: auto; white-space: nowrap; flex-wrap: nowrap !important; padding-bottom: 4px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 42px; background-color: #F1F5F9; border-radius: 8px;
        font-weight: 600; padding: 6px 12px; font-size: 0.88rem;
    }
    .stTabs [aria-selected="true"] { background-color: #0F172A !important; color: #FFFFFF !important; }
</style>
"""
st.markdown(MOBILE_AND_CLOUD_CSS, unsafe_allow_html=True)

# ==============================================================================
# 2. AUTENTICAZIONE PIN
# ==============================================================================
def check_pin_authentication() -> bool:
    expected_pin = st.secrets.get("app_pin", "").strip() if "app_pin" in st.secrets else None
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
# 3. GITHUB REST API & AES-256 PERSISTENCE
# ==============================================================================
def get_cipher():
    key = st.secrets.get("encryption_key", "").strip() if "encryption_key" in st.secrets else ""
    return Fernet(key.encode("utf-8")) if key else None

def get_github_config():
    token = st.secrets.get("github_token", "").strip() if "github_token" in st.secrets else ""
    repo = st.secrets.get("github_repo", "").strip() if "github_repo" in st.secrets else ""
    branch = st.secrets.get("github_branch", "main").strip() if "github_branch" in st.secrets else "main"
    return {"token": token, "repo": repo, "branch": branch} if token and repo else None

def get_default_portfolios() -> dict:
    return {
        "P1 - Core & Satellites": {
            "data_inizio": "2024-01-02", "capitale_iniziale_versato": 50000.0, "cash": 3500.0,
            "tasse_totali_pagate": 0.0, "zainetto_minusvalenze": 0.0,
            "posizioni": [
                {"ticker": "SWDA.MI", "nome": "MSCI World Core", "target": 50.0, "tolleranza": 5.0, "quote": 120, "pmc": 86.20},
                {"ticker": "SXRM.DE", "nome": "Treasury 7-10y (Gov)", "target": 30.0, "tolleranza": 4.0, "quote": 300, "pmc": 26.50},
                {"ticker": "4GLD.DE", "nome": "Gold ETC (No OICR)", "target": 10.0, "tolleranza": 2.5, "quote": 60, "pmc": 70.00},
                {"ticker": "VVSM.DE", "nome": "Semiconductors", "target": 10.0, "tolleranza": 2.5, "quote": 40, "pmc": 115.00}
            ], "transazioni": []
        }
    }

def load_data_from_storage() -> dict:
    gh = get_github_config()
    cipher = get_cipher()
    
    if gh:
        url = f"https://api.github.com/repos/{gh['repo']}/contents/{DATA_FILENAME}?ref={gh['branch']}"
        headers = {"Authorization": f"Bearer {gh['token']}", "Accept": "application/vnd.github.v3+json", "Cache-Control": "no-cache"}
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                payload = resp.json()
                raw_file_str = base64.b64decode(payload["content"]).decode("utf-8")
                
                if cipher:
                    try:
                        data = json.loads(cipher.decrypt(raw_file_str.encode("utf-8")).decode("utf-8"))
                    except Exception:
                        data = json.loads(raw_file_str) # Fallback se era in chiaro
                else:
                    data = json.loads(raw_file_str)
                    
                st.session_state["storage_mode"] = f"GitHub Cloud (AES-256)" if cipher else f"GitHub Cloud ({gh['repo']})"
                st.session_state["github_file_sha"] = payload.get("sha")
                return data
            elif resp.status_code == 404:
                st.session_state["storage_mode"] = f"GitHub Cloud (Nuovo)"
                default_d = get_default_portfolios()
                save_data_to_storage(default_d, commit_msg="Inizializzazione database cifrato")
                return default_d
        except Exception as e:
            st.warning(f"Errore GitHub API ({e}). Uso locale.")

    st.session_state["storage_mode"] = "File Locale (JSON)"
    if os.path.exists(DATA_FILENAME):
        try:
            with open(DATA_FILENAME, "r", encoding="utf-8") as f:
                content = f.read()
                if cipher:
                    try: content = cipher.decrypt(content.encode("utf-8")).decode("utf-8")
                    except: pass
                return json.loads(content)
        except Exception:
            pass

    return get_default_portfolios()

def save_data_to_storage(data: dict, commit_msg: str = "Aggiornamento portafoglio (Dati Cifrati)"):
    json_str = json.dumps(data, indent=4, ensure_ascii=False)
    cipher = get_cipher()
    content_to_save = cipher.encrypt(json_str.encode("utf-8")).decode("utf-8") if cipher else json_str

    try:
        with open(DATA_FILENAME, "w", encoding="utf-8") as f: f.write(content_to_save)
    except: pass

    gh = get_github_config()
    if gh:
        url = f"https://api.github.com/repos/{gh['repo']}/contents/{DATA_FILENAME}"
        headers = {"Authorization": f"Bearer {gh['token']}", "Accept": "application/vnd.github.v3+json"}
        try:
            sha = None
            get_resp = requests.get(f"{url}?ref={gh['branch']}", headers=headers, timeout=10)
            if get_resp.status_code == 200:
                sha = get_resp.json().get("sha")

            encoded = base64.b64encode(content_to_save.encode("utf-8")).decode("utf-8")
            put_payload = {
                "message": f"{commit_msg} [{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]",
                "content": encoded, "branch": gh["branch"]
            }
            if sha: put_payload["sha"] = sha

            put_resp = requests.put(url, headers=headers, json=put_payload, timeout=12)
            if put_resp.status_code in (200, 201):
                st.session_state["github_file_sha"] = put_resp.json().get("content", {}).get("sha")
                return True, "✅ Dati cifrati e salvati su GitHub!"
            else:
                return False, f"⚠️ Errore commit GitHub ({put_resp.status_code}): {put_resp.text}"
        except Exception as e:
            return False, f"⚠️ Errore di rete verso GitHub: {e}"
    return True, "💾 Dati salvati in locale."

# ==============================================================================
# 4. MOTORE FISCALE ITALIANO
# ==============================================================================
GOV_KEYWORDS = ["treasury", "sxrm", "dtla", "tlt", "ief", "bil", "btp", "bund", "gov", "titoli di stato", "dbxoan", "xeon"]
ETC_KEYWORDS = ["4gld", "gld", "sgld", "igln", "phau", "gold", "oro", "etc", "etn", "physical", "commodity"]

def classifica_strumento_fiscale(ticker: str, nome: str = "") -> dict:
    testo = f"{ticker} {nome}".lower()
    for kw in ETC_KEYWORDS:
        if kw in testo: return {"codice": "ETC_26", "aliquota": 0.26, "compensa_minus": True, "label": "26% (ETC/Redd. Diversi)"}
    for kw in GOV_KEYWORDS:
        if kw in testo: return {"codice": "GOV_125", "aliquota": 0.125, "compensa_minus": False, "label": "12.5% (Gov White-List)"}
    return {"codice": "ETF_26", "aliquota": 0.26, "compensa_minus": False, "label": "26% (ETF/Redd. Capitale)"}

def calcola_vendita_fiscale(ticker: str, nome: str, quote: float, prezzo: float, pmc: float, zainetto_attuale: float = 0.0) -> dict:
    controvalore_lordo = quote * prezzo
    costo_fiscale = quote * pmc
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
        "controvalore_lordo": controvalore_lordo, "plusvalenza": risultato_lordo, "aliquota": aliquota,
        "label_fiscale": profilo["label"], "compensa_minus": profilo["compensa_minus"],
        "minus_usata": minus_usata, "minus_generata": minus_generata, "risparmio_fiscale": risparmio_fiscale,
        "imposta_dovuta": imposta_dovuta, "incasso_netto": incasso_netto, "nuovo_zainetto": nuovo_zainetto
    }

# ==============================================================================
# 5. MOTORE QUANTITATIVO (METRICHE E SERIE STORICHE)
# ==============================================================================
def compute_quant_metrics(equity_series: pd.Series, rf_annual: float = 0.025, bench_series: pd.Series = None) -> dict:
    if equity_series is None or len(equity_series.dropna()) < 5: return {}
    s = equity_series.dropna()
    rets = s.pct_change().dropna()
    if rets.empty: return {}

    years = max(1, (s.index[-1] - s.index[0]).days) / 365.25
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

    beta, alpha_pct = np.nan, np.nan
    if bench_series is not None and len(bench_series.dropna()) >= 5:
        b_rets = bench_series.dropna().pct_change().dropna()
        aligned = pd.concat([rets, b_rets], axis=1, join="inner").dropna()
        if len(aligned) > 10:
            cov_mat = np.cov(aligned.iloc[:, 0], aligned.iloc[:, 1])
            var_b = cov_mat[1, 1]
            if var_b > 0:
                beta = float(cov_mat[0, 1] / var_b)
                b_years = max(1, (aligned.index[-1] - aligned.index[0]).days) / 365.25
                b_cagr = ((((1 + aligned.iloc[:, 1]).prod()) ** (1.0 / b_years)) - 1.0) * 100.0 if b_years > 0.05 else 0.0
                alpha_pct = float(cagr_pct - (rf_annual * 100.0 + beta * (b_cagr - rf_annual * 100.0)))

    return {
        "Totale %": tot_ret_pct, "CAGR %": cagr_pct, "Volatilità %": vol_pct, "Downside Dev %": downside_dev_pct,
        "Sharpe": sharpe, "Sortino": sortino, "Calmar": calmar, "Max Drawdown %": max_dd_pct,
        "Ulcer Index": ulcer_index, "VaR 95% (1g)": var_95, "CVaR 95% (1g)": cvar_95,
        "Win Rate %": float((rets > 0).mean() * 100.0), "Miglior Giorno %": float(rets.max() * 100.0),
        "Peggior Giorno %": float(rets.min() * 100.0), "Beta": beta, "Alpha %": alpha_pct, "dd_series": dd_pct
    }

def compute_monthly_returns_table(equity_series: pd.Series) -> pd.DataFrame:
    if equity_series is None or equity_series.empty: return pd.DataFrame()
    s = equity_series.resample("ME").last()
    m_rets = s.pct_change().dropna() * 100.0
    if m_rets.empty: return pd.DataFrame()

    df_m = pd.DataFrame({"Anno": m_rets.index.year, "Mese": m_rets.index.month, "Ret": m_rets.values})
    pivot = df_m.pivot(index="Anno", columns="Mese", values="Ret").rename(columns={
        1:"Gen", 2:"Feb", 3:"Mar", 4:"Apr", 5:"Mag", 6:"Giu", 7:"Lug", 8:"Ago", 9:"Set", 10:"Ott", 11:"Nov", 12:"Dic"
    })
    pivot["Totale Anno"] = pd.Series({yr: (np.prod(1.0 + grp["Ret"].values / 100.0) - 1.0) * 100.0 for yr, grp in df_m.groupby("Anno")})
    return pivot.sort_index(ascending=False)

# ==============================================================================
# 6. DOWNLOAD DATI MERCATO
# ==============================================================================
def extract_close_dataframe(raw_df: pd.DataFrame, tickers: list) -> pd.DataFrame:
    if raw_df is None or raw_df.empty: return pd.DataFrame()
    if isinstance(raw_df.columns, pd.MultiIndex):
        if "Close" in raw_df.columns.get_level_values(0): df_close = raw_df["Close"]
        elif "Close" in raw_df.columns.get_level_values(1): df_close = raw_df.xs("Close", axis=1, level=1)
        else: df_close = raw_df.iloc[:, :len(tickers)]
    else:
        df_close = raw_df[["Close"]].rename(columns={"Close": tickers[0]}) if "Close" in raw_df.columns else raw_df
    return df_close.to_frame(name=tickers[0]) if isinstance(df_close, pd.Series) else df_close

@st.cache_data(ttl=300, show_spinner=False)
def fetch_realtime_prices(tickers: list) -> dict:
    prices = {}
    clean_tickers = [t for t in tickers if t]
    if not clean_tickers: return prices
    try:
        raw = yf.download(clean_tickers, period="7d", interval="1d", progress=False, auto_adjust=True)
        df_close = extract_close_dataframe(raw, clean_tickers)
        for t in clean_tickers:
            if t in df_close.columns:
                s = df_close[t].dropna()
                prices[t] = {"price": float(s.iloc[-1]), "prev_close": float(s.iloc[-2])} if len(s) >= 2 else (
                    {"price": float(s.iloc[-1]), "prev_close": float(s.iloc[-1])} if len(s) == 1 else {"price": 0.0, "prev_close": 0.0}
                )
            else:
                prices[t] = {"price": 0.0, "prev_close": 0.0}
    except:
        for t in clean_tickers: prices[t] = {"price": 0.0, "prev_close": 0.0}
    return prices

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_historical_matrix(tickers: list, start_date: str) -> pd.DataFrame:
    clean_tickers = list(set([t for t in tickers if t]))
    if not clean_tickers: return pd.DataFrame()
    try:
        raw = yf.download(clean_tickers, start=start_date, progress=False, auto_adjust=True)
        return extract_close_dataframe(raw, clean_tickers).ffill().bfill().dropna(how="all")
    except: return pd.DataFrame()

# ==============================================================================
# 7. INIZIALIZZAZIONE STATO E BARRA CONTROLLI
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
        for f in ["zainetto_minusvalenze", "tasse_totali_pagate", "cash"]: all_p[k].setdefault(f, 0.0)
        all_p[k].setdefault("transazioni", [])

top_c1, top_c2 = st.columns([3, 1])
with top_c1: selected_p = st.selectbox("📂 Portafoglio Attivo:", p_names, index=0 if p_names else None)
with top_c2:
    st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
    if st.button("🔄 Sync Live", use_container_width=True):
        st.cache_data.clear()
        st.session_state["all_portfolios"] = load_data_from_storage()
        st.rerun()

port_cash = float(all_p[selected_p].get("cash", 0.0))

with st.sidebar:
    st.title("🎛️ Settings & Cassa")
    if "Cloud" in st.session_state.get("storage_mode", ""): st.success(f"☁️ {st.session_state.get('storage_mode')}")
    else: st.warning(f"💾 {st.session_state.get('storage_mode')}")

    rf_rate_pct = st.number_input("Tasso Risk-Free Annuo (%):", min_value=0.0, max_value=10.0, value=2.50, step=0.25)
    rf_rate = rf_rate_pct / 100.0

    st.divider()
    st.subheader("💵 Liquidità")
    cash_mov = st.number_input("Importo (€):", min_value=10.0, max_value=1000000.0, value=1000.0, step=100.0)
    c_in, c_out = st.columns(2)
    with c_in:
        if st.button("Deposita", use_container_width=True):
            all_p[selected_p]["cash"] = port_cash + cash_mov
            all_p[selected_p]["capitale_iniziale_versato"] = float(all_p[selected_p].get("capitale_iniziale_versato", 0.0)) + cash_mov
            all_p[selected_p]["transazioni"].append({
                "data": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "tipo": "DEPOSITO_CASH", "ticker": "CASH", "quote": 0, "prezzo": 1.0,
                "lordo": cash_mov, "plusvalenza": 0.0, "tassa_pagata": 0.0, "netto_incassato": cash_mov
            })
            save_data_to_storage(all_p, f"Deposito Cash su {selected_p}")
            st.rerun()
    with c_out:
        if st.button("Preleva", use_container_width=True):
            if cash_mov <= port_cash:
                all_p[selected_p]["cash"] = port_cash - cash_mov
                all_p[selected_p]["capitale_iniziale_versato"] = max(0.0, float(all_p[selected_p].get("capitale_iniziale_versato", 0.0)) - cash_mov)
                all_p[selected_p]["transazioni"].append({
                    "data": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "tipo": "PRELIEVO_CASH", "ticker": "CASH", "quote": 0, "prezzo": 1.0,
                    "lordo": cash_mov, "plusvalenza": 0.0, "tassa_pagata": 0.0, "netto_incassato": -cash_mov
                })
                save_data_to_storage(all_p, f"Prelievo Cash da {selected_p}")
                st.rerun()
            else: st.error("Cash insufficiente.")

    st.divider()
    with st.expander("➕ Nuovo / Duplica"):
        new_p_name = st.text_input("Nome:")
        clone_from = st.selectbox("Copia da:", ["Vuoto Base"] + p_names)
        new_cap = st.number_input("Capitale (€):", value=50000.0, step=1000.0)
        if st.button("Crea Portafoglio", use_container_width=True) and new_p_name not in all_p:
            cloned_pos = copy.deepcopy(all_p[clone_from]["posizioni"]) if clone_from != "Vuoto Base" else [
                {"ticker": "SWDA.MI", "nome": "MSCI World", "target": 60.0, "tolleranza": 5.0, "quote": 100, "pmc": 85.00},
                {"ticker": "SXRM.DE", "nome": "Treasury 7-10yr", "target": 40.0, "tolleranza": 5.0, "quote": 200, "pmc": 27.00}
            ]
            all_p[new_p_name] = {
                "data_inizio": datetime.date.today().strftime("%Y-%m-%d"), "capitale_iniziale_versato": new_cap, "cash": 1000.0,
                "tasse_totali_pagate": 0.0, "zainetto_minusvalenze": 0.0, "posizioni": cloned_pos, "transazioni": []
            }
            save_data_to_storage(all_p, f"Creato portafoglio {new_p_name}")
            st.rerun()

    with st.expander("✏️ Gestisci"):
        ren_val = st.text_input("Rinomina in:", value=selected_p)
        cr1, cr2 = st.columns(2)
        with cr1:
            if st.button("Rinomina", use_container_width=True) and ren_val != selected_p and ren_val not in all_p:
                all_p[ren_val] = all_p.pop(selected_p)
                save_data_to_storage(all_p, f"Rinominato {selected_p} in {ren_val}")
                st.rerun()
        with cr2:
            if st.button("Elimina 🗑️", use_container_width=True):
                if len(all_p) > 1:
                    all_p.pop(selected_p)
                    save_data_to_storage(all_p, f"Eliminato {selected_p}")
                    st.rerun()
                else: st.error("Impossibile eliminare ultimo.")

# ==============================================================================
# 8. CALCOLO POSIZIONI & BENTO GRID
# ==============================================================================
curr_data = all_p[selected_p]
posizioni = curr_data.get("posizioni", [])
tickers = [p["ticker"] for p in posizioni if p.get("ticker")]

with st.spinner("Sync live data..."):
    prezzi_info = fetch_realtime_prices(tickers)

righe_tabella = []
valore_totale_strumenti, valore_totale_ieri, daily_pnl_totale_eur = 0.0, 0.0, 0.0
plusvalenze_latenti_totali, imposta_latente_stimata = 0.0, 0.0
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
    if gain_latente > 0: imposta_latente_stimata += gain_latente * prof_fisc["aliquota"]

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
    df_pos["Stato"] = df_pos.apply(lambda r: "🚨 RIBILANCIARE" if r["Fuori Banda"] else ("⚠️ VICINO SOGLIA" if r["Utilizzo Banda %"] >= 80 else "✅ IN TARGET"), axis=1)
    df_pos["Target Valore €"] = valore_portafoglio_totale * (df_pos["Target %"] / 100.0)
    df_pos["Azione €"] = df_pos["Target Valore €"] - df_pos["Controvalore €"]
    df_pos["Azione Quote"] = df_pos.apply(lambda r: int(round(r["Azione €"] / r["Prezzo €"])) if r["Prezzo €"] > 0 else 0, axis=1)
else:
    for col in ["Peso Attuale %", "Scostamento %", "Utilizzo Banda %", "Azione €", "Azione Quote"]: df_pos[col] = 0.0
    df_pos["Fuori Banda"] = False
    df_pos["Stato"] = "IN ATTESA"

# BENTO GRID METRICS
cap_versato = float(curr_data.get("capitale_iniziale_versato", valore_portafoglio_totale))
data_inizio_dt = datetime.datetime.strptime(curr_data.get("data_inizio", "2024-01-02"), "%Y-%m-%d").date()
anni_inv = max(1, (datetime.date.today() - data_inizio_dt).days) / 365.25

pnl_netto_eur = valore_portafoglio_totale - cap_versato
pnl_netto_pct = (pnl_netto_eur / cap_versato * 100.0) if cap_versato > 0 else 0.0
cagr_effettivo = (((valore_portafoglio_totale / cap_versato) ** (1.0 / anni_inv)) - 1.0) * 100.0 if (cap_versato > 0 and anni_inv > 0.05 and valore_portafoglio_totale > 0) else pnl_netto_pct
tasse_pagate = float(curr_data.get("tasse_totali_pagate", 0.0))

c_oggi = "pos-delta" if daily_pnl_totale_eur >= 0 else "neg-delta"
c_storico = "pos-delta" if pnl_netto_eur >= 0 else "neg-delta"
c_lat = "pos-delta" if plusvalenze_latenti_totali >= 0 else "neg-delta"

st.markdown(f"""
<div class="bento-grid">
    <div class="bento-card"><div class="bento-label">Patrimonio Totale</div><div class="bento-value">€ {valore_portafoglio_totale:,.2f}</div><div class="bento-sub neu-delta">Cash: € {port_cash:,.0f}</div></div>
    <div class="bento-card"><div class="bento-label">Performance Oggi</div><div class="bento-value {c_oggi}">€ {daily_pnl_totale_eur:+,.2f}</div><div class="bento-sub {c_oggi}">{daily_pnl_totale_pct:+.2f}% intraday</div></div>
    <div class="bento-card"><div class="bento-label">P&L Storico Reale</div><div class="bento-value {c_storico}">€ {pnl_netto_eur:+,.2f}</div><div class="bento-sub {c_storico}">{pnl_netto_pct:+.2f}% su versato</div></div>
    <div class="bento-card"><div class="bento-label">CAGR Effettivo</div><div class="bento-value">{cagr_effettivo:.2f}%</div><div class="bento-sub neu-delta">Attivo da {anni_inv:.1f} anni</div></div>
    <div class="bento-card"><div class="bento-label">P&L Latente Lordo</div><div class="bento-value {c_lat}">€ {plusvalenze_latenti_totali:+,.2f}</div><div class="bento-sub neu-delta">Netto: € {valore_portafoglio_totale - imposta_latente_stimata:,.0f}</div></div>
    <div class="bento-card"><div class="bento-label">Fisco & Zainetto</div><div class="bento-value">€ {tasse_pagate:,.2f}</div><div class="bento-sub neu-delta">Minus: € {zainetto_minus:,.0f}</div></div>
</div>
""", unsafe_allow_html=True)

# ==============================================================================
# 9. TABS PRINCIPALI (TOUCH SCREEN)
# ==============================================================================
t_reb, t_quant, t_comp, t_pac, t_tax, t_setup, t_cloud = st.tabs(["⚖️ Operatività", "📊 Quant", "⚔️ Confronto", "💰 PAC", "🧾 Fisco", "⚙️ Setup", "☁️ Backup"])

# ------------------------------------------------------------------------------
# TAB 1: RIBILANCIAMENTO A BANDE & OPERATIVITA' MANUALE
# ------------------------------------------------------------------------------
with t_reb:
    v_opt = st.radio("Formato view:", ["📱 Mobile Cards", "🖥️ Tabella Completa"], horizontal=True)
    if "Mobile" in v_opt:
        for _, r in df_pos.iterrows():
            bdg = "badge-alert" if r["Fuori Banda"] else ("badge-warn" if "VICINO" in r["Stato"] else "badge-ok")
            c_d = "pos-delta" if r["Var. Oggi %"] >= 0 else "neg-delta"
            c_p = "pos-delta" if r["P&L %"] >= 0 else "neg-delta"
            az = f"Compra {r['Azione Quote']:+,.0f} q (€ {abs(r['Azione €']):,.0f})" if r["Azione Quote"]>0 else (f"Vendi {abs(r['Azione Quote']):,.0f} q (€ {abs(r['Azione €']):,.0f})" if r["Azione Quote"]<0 else "Nessuna azione")
            st.markdown(f"""
            <div class="asset-card">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
                    <div><b>{r['Ticker']}</b> <span style="color:#64748B;font-size:0.85rem;">• {r['Nome']}</span></div><span class="{bdg}">{r['Stato']}</span>
                </div>
                <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:6px;font-size:0.84rem;">
                    <div>Prezzo: <b>€ {r['Prezzo €']:.2f}</b> <span class="{c_d}">({r['Var. Oggi %']:+.2f}%)</span></div>
                    <div>Valore: <b>€ {r['Controvalore €']:,.0f}</b></div><div>P&L: <b class="{c_p}">{r['P&L %']:+.1f}%</b></div>
                    <div>Peso: <b>{r['Peso Attuale %']:.1f}%</b> / {r['Target %']:.1f}%</div><div>Scost.: <b>{r['Scostamento %']:+.2f}%</b> (±{r['Tolleranza %']:.1f}%)</div><div>Az: <b>{az}</b></div>
                </div>
            </div>""", unsafe_allow_html=True)
    else:
        styled_pos = df_pos[["Ticker","Nome","Prezzo €","Var. Oggi %","Quote","PMC €","Controvalore €","P&L %","Peso Attuale %","Target %","Tolleranza %","Scostamento %","Stato","Azione Quote","Azione €","Regime Fiscale"]].style.format({
            "Prezzo €":"€ {:.2f}", "Var. Oggi %":"{:+.2f}%", "Quote":"{:,.0f}", "PMC €":"€ {:.2f}", "Controvalore €":"€ {:,.2f}", "P&L %":"{:+.2f}%",
            "Peso Attuale %":"{:.2f}%", "Target %":"{:.2f}%", "Tolleranza %":"±{:.2f}%", "Scostamento %":"{:+.2f}%", "Azione Quote":"{:+,.0f}", "Azione €":"€ {:+,.2f}"
        }).map(lambda v: "background-color: #FEE2E2; color: #991B1B; font-weight: bold;" if "RIBILANCIARE" in str(v) else ("background-color: #FEF3C7; color: #92400E; font-weight: bold;" if "VICINO" in str(v) else "background-color: #DCFCE7; color: #166534; font-weight: bold;"), subset=["Stato"])
        st.dataframe(styled_pos, use_container_width=True, height=360)

    cb_c, cp_c = st.columns([1.6, 1.2])
    with cb_c:
        st.markdown("##### 🎯 Corridor Chart: Scostamento vs Bande")
        if not df_pos.empty:
            fig_b = go.Figure()
            fig_b.add_trace(go.Bar(y=df_pos["Ticker"], x=df_pos["Tolleranza %"], orientation='h', marker=dict(color='rgba(148,163,184,0.25)', line=dict(color='#64748B',width=1))))
            fig_b.add_trace(go.Bar(y=df_pos["Ticker"], x=-df_pos["Tolleranza %"], orientation='h', marker=dict(color='rgba(148,163,184,0.25)', line=dict(color='#64748B',width=1))))
            c_s = ["#DC2626" if fb else "#16A34A" for fb in df_pos["Fuori Banda"]]
            fig_b.add_trace(go.Scatter(y=df_pos["Ticker"], x=df_pos["Scostamento %"], mode='markers+text', text=[f"{v:+.1f}%" for v in df_pos["Scostamento %"]], textposition="middle right", marker=dict(color=c_s, size=11, symbol="diamond")))
            fig_b.update_layout(barmode='overlay', template="plotly_white", height=310, margin=dict(t=10,b=10,l=10,r=35), showlegend=False)
            fig_b.add_vline(x=0, line_width=1.5, line_dash="dash", line_color="#0F172A")
            st.plotly_chart(fig_b, use_container_width=True)
    with cp_c:
        st.markdown("##### 🍩 Allocazione Effettiva")
        fig_p = go.Figure(data=[go.Pie(labels=list(df_pos["Ticker"])+["CASH"], values=list(df_pos["Controvalore €"])+[port_cash], hole=0.55, textinfo="label+percent", marker=dict(colors=px.colors.qualitative.Prism))])
        fig_p.update_layout(height=310, margin=dict(t=10,b=10,l=10,r=10), showlegend=False)
        st.plotly_chart(fig_p, use_container_width=True)

    st.divider()
    st.subheader("⚡ Ribilanciamento a Banda")
    oob = df_pos[df_pos["Fuori Banda"]].to_dict("records")
    if oob:
        for item in oob:
            tk, nome, q_act, pr, pmc_i = item["Ticker"], item["Nome"], item["Azione Quote"], item["Prezzo €"], item["PMC €"]
            c1, c2 = st.columns([3, 1])
            if q_act < 0:
                qs = abs(q_act)
                sim = calcola_vendita_fiscale(tk, nome, qs, pr, pmc_i, zainetto_minus)
                c1.markdown(f"🔴 **VENDI `{tk}`**: **{qs}** q a **€ {pr:.2f}** • Tassa: € {sim['imposta_dovuta']:,.2f} ➡️ **Netto su Cash: € {sim['incasso_netto']:,.2f}**")
                if c2.button(f"Vendi {tk}", key=f"bs_{tk}", use_container_width=True):
                    for p in posizioni:
                        if p["ticker"]==tk: p["quote"] = max(0, p["quote"] - qs)
                    all_p[selected_p]["cash"] = port_cash + sim["incasso_netto"]
                    all_p[selected_p]["tasse_totali_pagate"] = tasse_pagate + sim["imposta_dovuta"]
                    all_p[selected_p]["zainetto_minusvalenze"] = sim["nuovo_zainetto"]
                    all_p[selected_p]["transazioni"].append({"data": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "tipo": "VENDITA_BANDA", "ticker": tk, "quote": qs, "prezzo": pr, "pmc": pmc_i, "lordo": sim["controvalore_lordo"], "plusvalenza": sim["plusvalenza"], "minus_compensata": sim["minus_usata"], "tassa_pagata": sim["imposta_dovuta"], "netto_incassato": sim["incasso_netto"]})
                    save_data_to_storage(all_p, f"Vendita a banda {tk}")
                    st.rerun()
            elif q_act > 0:
                costo_b = q_act * pr
                c1.markdown(f"🟢 **COMPRA `{tk}`**: **{q_act}** q a **€ {pr:.2f}** • Spesa: **€ {costo_b:,.2f}**")
                if c2.button(f"Compra {tk}", key=f"bb_{tk}", use_container_width=True):
                    if costo_b > port_cash: st.error("Cash insufficiente.")
                    else:
                        for p in posizioni:
                            if p["ticker"]==tk:
                                nq = p["quote"] + q_act
                                p["pmc"] = round(((p["quote"]*p["pmc"]) + costo_b)/nq, 4)
                                p["quote"] = nq
                        all_p[selected_p]["cash"] = port_cash - costo_b
                        all_p[selected_p]["transazioni"].append({"data": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "tipo": "ACQUISTO_BANDA", "ticker": tk, "quote": q_act, "prezzo": pr, "pmc": pr, "lordo": costo_b, "plusvalenza": 0.0, "minus_compensata": 0.0, "tassa_pagata": 0.0, "netto_incassato": -costo_b})
                        save_data_to_storage(all_p, f"Acquisto a banda {tk}")
                        st.rerun()
    else: st.success("🎯 Tutti gli strumenti sono all'interno delle bande.")

    with st.expander("🛠️ Compravendita Estemporanea Manuale"):
        c1, c2, c3, c4 = st.columns([1.4, 1.2, 1.0, 1.0])
        with c1: etf_sel = st.selectbox("Strumento:", tickers, key="m_etf")
        a_obj = next((i for i in posizioni if i["ticker"]==etf_sel), None)
        p_mkt = prezzi_info.get(etf_sel, {}).get("price", 0.0)
        q_a, pmc_a, nm_a = a_obj["quote"] if a_obj else 0, a_obj["pmc"] if a_obj else 0.0, a_obj.get("nome", etf_sel) if a_obj else etf_sel

        with c2: t_op = st.radio("Azione:", ["Vendi", "Compra"], horizontal=True)
        with c3: q_m = st.number_input("Quote:", min_value=1, max_value=int(q_a) if ("Vendi" in t_op and q_a>0) else 100000, value=min(10, int(q_a)) if ("Vendi" in t_op and q_a>0) else 10, step=1)
        with c4: p_m = st.number_input("Prezzo (€):", min_value=0.01, value=float(p_mkt) if p_mkt>0 else 100.0, step=0.01, format="%.2f")

        if "Vendi" in t_op:
            sim = calcola_vendita_fiscale(etf_sel, nm_a, q_m, p_m, pmc_a, zainetto_minus)
            st.info(f"Lordo: **€ {sim['controvalore_lordo']:,.2f}** | P&L: **€ {sim['plusvalenza']:+,.2f}** | Minus usata: **€ {sim['minus_usata']:,.2f}** | Imposta: **€ {sim['imposta_dovuta']:,.2f}** ➡️ **Netto su Cash: € {sim['incasso_netto']:,.2f}**")
            if st.button("🔴 Conferma Vendita Manuale", type="primary", use_container_width=True) and q_m <= q_a:
                a_obj["quote"] = q_a - q_m
                all_p[selected_p]["cash"] = port_cash + sim["incasso_netto"]
                all_p[selected_p]["tasse_totali_pagate"] = tasse_pagate + sim["imposta_dovuta"]
                all_p[selected_p]["zainetto_minusvalenze"] = sim["nuovo_zainetto"]
                all_p[selected_p]["transazioni"].append({"data": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "tipo": "VENDITA_MANUALE", "ticker": etf_sel, "quote": q_m, "prezzo": p_m, "pmc": pmc_a, "lordo": sim["controvalore_lordo"], "plusvalenza": sim["plusvalenza"], "minus_compensata": sim["minus_usata"], "tassa_pagata": sim["imposta_dovuta"], "netto_incassato": sim["incasso_netto"]})
                save_data_to_storage(all_p, f"Vendita manuale {etf_sel}")
                st.rerun()
        else:
            cst = q_m * p_m
            new_q = q_a + q_m
            new_pmc = ((q_a*pmc_a)+cst)/new_q if new_q>0 else p_m
            st.info(f"Spesa: **€ {cst:,.2f}** | Cash residuo: **€ {port_cash-cst:,.2f}** | Nuovo PMC: **€ {new_pmc:.2f}**")
            if st.button("🟢 Conferma Acquisto Manuale", type="primary", use_container_width=True) and cst <= port_cash:
                a_obj["quote"] = new_q
                a_obj["pmc"] = round(new_pmc, 4)
                all_p[selected_p]["cash"] = port_cash - cst
                all_p[selected_p]["transazioni"].append({"data": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "tipo": "ACQUISTO_MANUALE", "ticker": etf_sel, "quote": q_m, "prezzo": p_m, "pmc": round(new_pmc, 4), "lordo": cst, "plusvalenza": 0.0, "minus_compensata": 0.0, "tassa_pagata": 0.0, "netto_incassato": -cst})
                save_data_to_storage(all_p, f"Acquisto manuale {etf_sel}")
                st.rerun()

# ------------------------------------------------------------------------------
# TAB 2: DASHBOARD QUANTITATIVA
# ------------------------------------------------------------------------------
with t_quant:
    cq1, cq2, cq3 = st.columns([1.5, 1.0, 1.0])
    with cq1: mod_a = st.radio("Serie:", ["Patrimonio Reale", "Backtest Target"], horizontal=True)
    with cq2: anni_b = st.selectbox("Anni Backtest:", [1, 3, 5, 10], index=2)
    with cq3: b_tk = st.selectbox("Benchmark:", ["SWDA.MI", "SPY", "QQQ", "URTH"], index=0)

    sq = str(curr_data.get("data_inizio", "2024-01-02")) if "Reale" in mod_a else (datetime.date.today() - datetime.timedelta(days=int(anni_b*365.25))).strftime("%Y-%m-%d")
    dh = fetch_historical_matrix(tickers+[b_tk], start_date=sq)

    if not dh.empty:
        vt = [t for t in tickers if t in dh.columns]
        if vt:
            if "Reale" in mod_a:
                ps = pd.Series(port_cash, index=dh.index)
                for p in posizioni:
                    if p["ticker"] in dh.columns: ps += dh[p["ticker"]] * float(p["quote"])
            else:
                ra = dh[vt].pct_change().fillna(0.0)
                tw = sum(float(p["target"]) for p in posizioni if p["ticker"] in vt)
                wv = np.array([float(p["target"])/tw for p in posizioni if p["ticker"] in vt]) if tw>0 else np.ones(len(vt))/len(vt)
                ps = (1.0 + ra.dot(wv)).cumprod() * 100.0

            bs = (1.0 + dh[b_tk].pct_change().fillna(0.0)).cumprod() * float(ps.iloc[0]) if b_tk in dh.columns else None
            qm = compute_quant_metrics(ps, rf_annual=rf_rate, bench_series=bs)

            if qm:
                st.markdown(f"""
                <div class="bento-grid">
                    <div class="bento-card"><div class="bento-label">CAGR Annuo</div><div class="bento-value">{qm['CAGR %']:.2f}%</div><div class="bento-sub neu-delta">Tot: {qm['Totale %']:+.1f}%</div></div>
                    <div class="bento-card"><div class="bento-label">Volatilità</div><div class="bento-value">{qm['Volatilità %']:.2f}%</div><div class="bento-sub neu-delta">Down: {qm['Downside Dev %']:.2f}%</div></div>
                    <div class="bento-card"><div class="bento-label">Sharpe / Sortino</div><div class="bento-value">{qm['Sharpe']:.2f} / {qm['Sortino']:.2f}</div><div class="bento-sub neu-delta">Rf: {rf_rate_pct:.1f}%</div></div>
                    <div class="bento-card"><div class="bento-label">Max Drawdown</div><div class="bento-value neg-delta">{qm['Max Drawdown %']:.2f}%</div><div class="bento-sub neu-delta">Ulcer: {qm['Ulcer Index']:.2f}</div></div>
                    <div class="bento-card"><div class="bento-label">Calmar / WinRate</div><div class="bento-value">{qm['Calmar']:.2f}</div><div class="bento-sub neu-delta">Win: {qm['Win Rate %']:.1f}%</div></div>
                    <div class="bento-card"><div class="bento-label">VaR / CVaR 95%</div><div class="bento-value neg-delta">{qm['VaR 95% (1g)']:.2f}%</div><div class="bento-sub neg-delta">CVaR: {qm['CVaR 95% (1g)']:.2f}%</div></div>
                </div>""", unsafe_allow_html=True)

                fe = go.Figure()
                fe.add_trace(go.Scatter(x=ps.index, y=ps, mode="lines", name=selected_p, line=dict(color="#2563EB", width=2.5)))
                if bs is not None: fe.add_trace(go.Scatter(x=bs.index, y=bs, mode="lines", name=b_tk, line=dict(color="#94A3B8", width=1.6, dash="dot")))
                fe.update_layout(title="Equity Curve", template="plotly_white", hovermode="x unified", height=330, margin=dict(t=35, b=10, l=10, r=10))
                st.plotly_chart(fe, use_container_width=True)

                fd = go.Figure()
                fd.add_trace(go.Scatter(x=qm["dd_series"].index, y=qm["dd_series"], mode="lines", fill="tozeroy", name="Drawdown %", line=dict(color="#DC2626", width=1.5), fillcolor="rgba(220,38,38,0.15)"))
                fd.update_layout(title="Underwater Drawdown (%)", template="plotly_white", height=230, margin=dict(t=35, b=10, l=10, r=10))
                st.plotly_chart(fd, use_container_width=True)

                st.markdown("##### 📅 Rendimenti Mensili (%)")
                df_m = compute_monthly_returns_table(ps)
                if not df_m.empty: st.dataframe(df_m.style.format("{:+.2f}%", na_rep="-").background_gradient(cmap="RdYlGn", vmin=-8, vmax=8), use_container_width=True)

                if len(vt) > 1:
                    st.markdown("##### 🔗 Matrice di Correlazione")
                    fig_c = px.imshow(dh[vt].pct_change().dropna().corr(), text_auto=".2f", color_continuous_scale="RdBu_r", zmin=-1, zmax=1, aspect="auto")
                    fig_c.update_layout(height=320, margin=dict(t=10, b=10, l=10, r=10), coloraxis_showscale=False)
                    st.plotly_chart(fig_c, use_container_width=True)

# ------------------------------------------------------------------------------
# TAB 3: CONFRONTO MULTI-PORTAFOGLIO
# ------------------------------------------------------------------------------
with t_comp:
    cc1, cc2, cc3 = st.columns([1.6, 1.2, 1.0])
    with cc1: sel_c = st.multiselect("Portafogli:", p_names, default=p_names)
    with cc2: mod_c = st.radio("Metodo:", ["Pesi Target", "Quote Reali"], horizontal=True)
    with cc3: yrs_c = st.selectbox("Orizzonte:", [1, 3, 5, 10], index=1)

    if sel_c:
        sc = (datetime.date.today() - datetime.timedelta(days=int(yrs_c*365.25))).strftime("%Y-%m-%d")
        act = {i["ticker"] for pn in sel_c for i in all_p[pn].get("posizioni", []) if i.get("ticker")}
        dhc = fetch_historical_matrix(list(act), start_date=sc)

        if not dhc.empty:
            ra_c = dhc.pct_change().fillna(0.0)
            cdict, mcomp = {}, []

            for pn in sel_c:
                plist = [x for x in all_p[pn].get("posizioni", []) if x.get("ticker") in dhc.columns]
                if not plist: continue
                if "Target" in mod_c:
                    tt = sum(float(x["target"]) for x in plist)
                    ws = {x["ticker"]: (float(x["target"])/tt if tt>0 else 1.0/len(plist)) for x in plist}
                    pr = sum(ra_c[tk]*w for tk, w in ws.items())
                    ec = (1.0 + pr).cumprod() * 100.0
                else:
                    vs = pd.Series(float(all_p[pn].get("cash", 0.0)), index=dhc.index)
                    for x in plist: vs += dhc[x["ticker"]] * float(x["quote"])
                    ec = (vs/vs.iloc[0]) * 100.0 if vs.iloc[0]>0 else vs

                cdict[pn] = ec
                mres = compute_quant_metrics(ec, rf_annual=rf_rate)
                if mres:
                    mcomp.append({"Portafoglio": pn, "CAGR %": mres["CAGR %"], "Volatilità %": mres["Volatilità %"], "Max DD %": mres["Max Drawdown %"], "Sharpe": mres["Sharpe"], "Sortino": mres["Sortino"]})

            if mcomp:
                st.dataframe(pd.DataFrame(mcomp).set_index("Portafoglio").style.format({"CAGR %":"{:+.2f}%", "Volatilità %":"{:.2f}%", "Max DD %":"{:.2f}%", "Sharpe":"{:.2f}", "Sortino":"{:.2f}"}).highlight_max(subset=["CAGR %", "Sharpe", "Sortino"], color="#DCFCE7").highlight_min(subset=["Volatilità %"], color="#DCFCE7"), use_container_width=True)
                fm = go.Figure()
                for nc, s in cdict.items(): fm.add_trace(go.Scatter(x=s.index, y=s, mode="lines", name=nc, line=dict(width=2.5)))
                fm.update_layout(title="Equity Curve (Base 100)", template="plotly_white", hovermode="x unified", height=350, margin=dict(t=35, b=10))
                st.plotly_chart(fm, use_container_width=True)

# ------------------------------------------------------------------------------
# TAB 4: SMART PAC
# ------------------------------------------------------------------------------
with t_pac:
    st.subheader("💡 Smart PAC (Bilanciamento via nuovi versamenti)")
    c_pac = st.number_input("Nuova liquidità da investire (€):", min_value=50.0, max_value=1000000.0, value=1500.0, step=100.0)
    nt_pac = valore_portafoglio_totale + c_pac
    gps = [max(0.0, nt_pac * (r["Target %"]/100.0) - r["Controvalore €"]) for _, r in df_pos.iterrows()]
    sg = sum(gps)
    
    p_rows = []
    for i, (_, r) in enumerate(df_pos.iterrows()):
        b = c_pac * (gps[i]/sg) if sg>0 else c_pac * (r["Target %"]/100.0)
        qb = int(b//r["Prezzo €"]) if r["Prezzo €"]>0 else 0
        se = qb * r["Prezzo €"]
        p_rows.append({"Ticker": r["Ticker"], "Prezzo €": r["Prezzo €"], "Da Comprare": qb, "Spesa €": se, "Nuovo Peso %": ((r["Controvalore €"]+se)/nt_pac)*100.0, "Target %": r["Target %"]})
    st.dataframe(pd.DataFrame(p_rows).style.format({"Prezzo €":"€ {:.2f}", "Da Comprare":"{:,.0f}", "Spesa €":"€ {:,.2f}", "Nuovo Peso %":"{:.2f}%", "Target %":"{:.2f}%"}), use_container_width=True)

# ------------------------------------------------------------------------------
# TAB 5: REGISTRO FISCALE
# ------------------------------------------------------------------------------
with t_tax:
    st.subheader("🧾 Zainetto Minusvalenze & Transazioni")
    nz = st.number_input("Zainetto Minus accumulate (€):", min_value=0.0, value=zainetto_minus, step=50.0)
    if st.button("Salva Zainetto"):
        all_p[selected_p]["zainetto_minusvalenze"] = nz
        save_data_to_storage(all_p, "Update zainetto manuale")
        st.rerun()
    tx_list = curr_data.get("transazioni", [])
    if tx_list: st.dataframe(pd.DataFrame(tx_list), use_container_width=True)
    else: st.info("Nessuna transazione.")

# ------------------------------------------------------------------------------
# TAB 6: SETUP
# ------------------------------------------------------------------------------
with t_setup:
    cs1, cs2 = st.columns(2)
    with cs1: ns_dt = st.date_input("Data Inizio:", data_inizio_dt)
    with cs2: nc_in = st.number_input("Capitale Versato (€):", value=cap_versato, step=500.0)
    edf = st.data_editor(pd.DataFrame(posizioni), num_rows="dynamic", use_container_width=True, column_config={
        "ticker": st.column_config.TextColumn("Ticker", required=True), "nome": st.column_config.TextColumn("Nome"),
        "target": st.column_config.NumberColumn("Target %", min_value=0.0, max_value=100.0, step=0.5, required=True),
        "tolleranza": st.column_config.NumberColumn("Banda (±%)", min_value=0.1, max_value=25.0, step=0.5, required=True),
        "quote": st.column_config.NumberColumn("Quote", min_value=0, step=1, required=True),
        "pmc": st.column_config.NumberColumn("PMC (€)", min_value=0.0, step=0.01, format="€ %.2f", required=True),
    })
    if st.button("💾 Salva Portafoglio", type="primary", use_container_width=True):
        cleaned = [{"ticker": str(r["ticker"]).strip().upper(), "nome": str(r.get("nome") or r["ticker"]).strip(), "target": float(r.get("target") or 0.0), "tolleranza": float(r.get("tolleranza") or 2.5), "quote": float(r.get("quote") or 0), "pmc": float(r.get("pmc") or 0.0)} for _, r in edf.iterrows() if pd.notna(r.get("ticker")) and str(r.get("ticker")).strip() != ""]
        all_p[selected_p]["data_inizio"] = str(ns_dt)
        all_p[selected_p]["capitale_iniziale_versato"] = float(nc_in)
        all_p[selected_p]["posizioni"] = cleaned
        ok, msg = save_data_to_storage(all_p, f"Aggiornamento parametri {selected_p}")
        st.cache_data.clear()
        st.success(msg) if ok else st.error(msg)
        st.rerun()

# ------------------------------------------------------------------------------
# TAB 7: CLOUD & BACKUP
# ------------------------------------------------------------------------------
with t_cloud:
    st.subheader("☁️ Stato Sincronizzazione & Backup JSON")
    st.write(f"Persistenza: **{st.session_state.get('storage_mode')}**")
    if st.button("🚀 Forza Sync su GitHub", use_container_width=True):
        ok, msg = save_data_to_storage(all_p, "Sync forzato")
        st.success(msg) if ok else st.error(msg)
    st.divider()
    st.download_button("⬇️ Scarica Copia JSON", data=json.dumps(all_p, indent=4, ensure_ascii=False), file_name=f"backup_{datetime.date.today()}.json", mime="application/json", use_container_width=True)
    up = st.file_uploader("⬆️ Ripristina JSON:", type=["json"])
    if up is not None and st.button("Ripristina Dati", use_container_width=True):
        all_p.update(json.load(up))
        save_data_to_storage(all_p, "Ripristino da backup")
        st.success("Ripristinato!")
        st.rerun()
