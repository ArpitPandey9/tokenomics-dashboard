import streamlit as st
import requests
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
import ccxt
import time

st.set_page_config(page_title="Tokenomics Dashboard", layout="wide")
st.title("📊 Tokenomics Dashboard")

# =========================
# TOKEN & TIME RANGE SELECTION
# =========================
token_map = {
    "AAVE": {"cg": "aave", "binance": "AAVE/USDT", "llama": "aave"},
    "Uniswap": {"cg": "uniswap", "binance": "UNI/USDT", "llama": "uniswap"},
    "Compound": {"cg": "compound-governance-token", "binance": "COMP/USDT", "llama": "compound"}
}
token_name = st.selectbox("Select Token", list(token_map.keys()))
days = int(st.selectbox("Select Time Range", ["7", "30", "90"], index=1))
cg_id = token_map[token_name]["cg"]
binance_symbol = token_map[token_name]["binance"]
llama_token = token_map[token_name]["llama"]

# =========================
# API HELPERS
# =========================
@st.cache_data(ttl=300)
def fetch_json(url, params=None):
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 429:
            time.sleep(3)
            resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        return None
    return None

@st.cache_data(ttl=300)
def get_cg_token_data(token):
    return fetch_json(f"https://api.coingecko.com/api/v3/coins/{token}")

@st.cache_data(ttl=300)
def get_cg_simple_price(token):
    j = fetch_json("https://api.coingecko.com/api/v3/simple/price", {"ids": token, "vs_currencies": "usd", "include_market_cap": "true"})
    return j.get(token, {}) if j else {}

@st.cache_data(ttl=300)
def get_cg_chart(token, days):
    j = fetch_json(f"https://api.coingecko.com/api/v3/coins/{token}/market_chart", {"vs_currency": "usd", "days": days})
    if j and "prices" in j and j["prices"]:
        return j
    end = int(datetime.now().timestamp())
    start = int((datetime.now() - timedelta(days=days)).timestamp())
    jr = fetch_json(f"https://api.coingecko.com/api/v3/coins/{token}/market_chart/range", {"vs_currency": "usd", "from": start, "to": end})
    if jr and "prices" in jr and jr["prices"]:
        return jr
    return None

@st.cache_data(ttl=300)
def get_llama_history(token, days):
    start_date = (datetime.now() - timedelta(days=days)).date()
    url = f"https://coins.llama.fi/prices/historical/{start_date}?coins=coingecko:{token}"
    data = fetch_json(url)
    prices = []
    if data and "coins" in data and f"coingecko:{token}" in data["coins"]:
        hist = data["coins"][f"coingecko:{token}"]
        for ts, price in hist.items():
            prices.append([int(ts)*1000, price])
    return prices

@st.cache_data(ttl=300)
def get_binance_ohlc(symbol, days):
    try:
        ex = ccxt.binance()
        since = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)
        ohlc = ex.fetch_ohlcv(symbol, timeframe='1d', since=since)
        return [[row[0], row[4]] for row in ohlc]  # timestamp, close
    except Exception:
        return []

@st.cache_data(ttl=300)
def get_tvl_llama(protocol):
    url = f"https://api.llama.fi/protocol/{protocol}"
    data = fetch_json(url)
    # Some tokens: tvl is a list of dicts with 'totalLiquidityUSD'
    # Some tokens: tvl is a float
    if data and "tvl" in data and data["tvl"]:
        tvl_data = data["tvl"]
        if isinstance(tvl_data, list) and len(tvl_data) > 0:
            # Get the last available TVL value
            last = tvl_data[-1]
            if isinstance(last, dict):
                for key in ['totalLiquidityUSD', 'tvl', 'totalLiquidity']:
                    if key in last:
                        return float(last[key])
            if isinstance(last, (float, int)):
                return float(last)
        elif isinstance(tvl_data, (float, int)):
            return float(tvl_data)
    return None

def format_large_number(num):
    try:
        if not isinstance(num, (float, int)) or num == 0:
            return "N/A"
        if num >= 1e9:
            return f"${num/1e9:.2f}B"
        elif num >= 1e6:
            return f"${num/1e6:.2f}M"
        return f"${num:,.0f}"
    except Exception:
        return "N/A"

# =========================
# METRICS FETCH & FALLBACKS
# =========================
cg_data = get_cg_token_data(cg_id)
cg_simple = get_cg_simple_price(cg_id)
tvl = get_tvl_llama(llama_token)
metrics_source = "CoinGecko"

market_info = cg_data.get("market_data", {}) if cg_data else {}
current_price = market_info.get("current_price", {}).get("usd", 0) if market_info else 0
market_cap = market_info.get("market_cap", {}).get("usd", 0) if market_info else 0
circulating_supply = market_info.get("circulating_supply", 0) if market_info else 0
total_supply = market_info.get("total_supply", 0) if market_info else 0
price_change_24h = market_info.get("price_change_percentage_24h", 0) if market_info else 0
price_change_7d = market_info.get("price_change_percentage_7d", 0) if market_info else 0
price_change_30d = market_info.get("price_change_percentage_30d", 0) if market_info else 0

# Fallback to simple price
if current_price == 0 and cg_simple:
    current_price = cg_simple.get("usd", 0)
    market_cap = cg_simple.get("usd_market_cap", 0)
    metrics_source = "CoinGecko (Simple API)"

# Fallback to Binance price
if current_price == 0:
    bin_price = get_binance_ohlc(binance_symbol, 2)
    if bin_price:
        current_price = bin_price[-1][1]
        metrics_source = "Binance"
    # No market cap/supply fallback here (Binance doesn't provide)

if not tvl or tvl == 0:
    tvl = 6200000000  # placeholder
    tvl_source = "Placeholder"
else:
    tvl_source = "DeFiLlama"

# =========================
# DISPLAY METRICS
# =========================
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Current Price (USD)", f"${current_price:,.2f}", help=f"Source: {metrics_source}")
col2.metric("Market Cap", format_large_number(market_cap))
col3.metric("Circulating Supply", f"{circulating_supply:,.0f}")
col4.metric("Total Value Locked (TVL)", format_large_number(tvl), help=f"Source: {tvl_source}")
col5.metric("24h Change", f"{price_change_24h:.2f}%")

col6, col7 = st.columns(2)
col6.metric("7d Change", f"{price_change_7d:.2f}%")
col7.metric("30d Change", f"{price_change_30d:.2f}%")

# =========================
# TOKEN SUPPLY PIE CHART (with MISSING DATA warning)
# =========================
show_pie = (
    isinstance(circulating_supply, (int, float)) and circulating_supply > 0
    and isinstance(total_supply, (int, float)) and total_supply > 0
    and total_supply >= circulating_supply
)

if show_pie:
    remaining_supply = total_supply - circulating_supply
    fig_supply = px.pie(
        values=[circulating_supply, remaining_supply],
        names=["Circulating Supply", "Remaining Supply"],
        title=f"{token_name} Token Supply Distribution"
    )
    fig_supply.update_layout(legend=dict(orientation="h", y=-0.2))
    st.plotly_chart(fig_supply, use_container_width=True)
else:
    st.warning(
        f"Supply data is not available for {token_name}. "
        "Pie chart can't be shown. "
        "This is common for some DeFi tokens on CoinGecko."
    )

# =========================
# HISTORICAL PRICE & MARKET CAP CHARTS (MULTI-FALLBACK)
# =========================
chart_source = ""
price_data = []
market_data = get_cg_chart(cg_id, days)

if market_data and "prices" in market_data and len(market_data["prices"]) > 0:
    price_data = market_data["prices"]
    chart_source = "CoinGecko"
else:
    price_data = get_llama_history(cg_id, days)
    if price_data:
        chart_source = "DeFiLlama"
    else:
        price_data = get_binance_ohlc(binance_symbol, days)
        if price_data:
            chart_source = "Binance"
        else:
            st.error(f"❌ No historical price data available for {token_name} from any source.")

if price_data:
    price_df = pd.DataFrame(price_data, columns=["Timestamp", "Price"])
    price_df["Date"] = pd.to_datetime(price_df["Timestamp"], unit="ms")
    fig_price = px.line(price_df, x="Date", y="Price", title=f"{token_name} Historical Price ({days} Days) - Source: {chart_source}")
    fig_price.update_traces(hovertemplate="Date: %{x}<br>Price: $%{y:.2f}")
    st.plotly_chart(fig_price, use_container_width=True)

if market_data and "market_caps" in market_data and len(market_data["market_caps"]) > 0:
    marketcap_df = pd.DataFrame(market_data["market_caps"], columns=["Timestamp", "Market Cap"])
    marketcap_df["Date"] = pd.to_datetime(marketcap_df["Timestamp"], unit="ms")
    fig_marketcap = px.line(marketcap_df, x="Date", y="Market Cap", title=f"{token_name} Market Cap ({days} Days) - Source: CoinGecko")
    fig_marketcap.update_traces(hovertemplate="Date: %{x}<br>Market Cap: $%{y:,.0f}")
    st.plotly_chart(fig_marketcap, use_container_width=True)

# =========================
# EXPLANATIONS
# =========================
st.header("📚 Understanding Tokenomics & Metrics")
st.subheader("Market Cap")
st.write("Market capitalization is the total value of a cryptocurrency. "
         "It is calculated as the current price multiplied by the circulating supply.")
st.subheader("Total Value Locked (TVL)")
st.write("TVL represents the total assets staked or locked in a DeFi protocol. "
         "Higher TVL often suggests greater trust and adoption.")
st.subheader("Circulating Supply vs Total Supply")
st.write("Circulating supply is the amount of tokens actively available for trading. "
         "Total supply includes all existing tokens, even those locked or not yet released.")
