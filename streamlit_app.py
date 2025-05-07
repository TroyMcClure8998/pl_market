import requests
import pandas as pd
import json
from py_clob_client.client import ClobClient, ApiCreds, TradeParams, BookParams
import streamlit as st
import plotly.express as px
from typing import List
import re

st.set_page_config(layout="wide", page_title="Polymarket Dashboard", page_icon="📊")

# Initialize session state for wallet addresses
if "wallet_addresses" not in st.session_state:
    st.session_state.wallet_addresses = ["0xa5f8d182b6086ac0713e557fc28497e591da1aff"]  # Default wallet made a list

# Initialize session state for sorting
if "sort_by" not in st.session_state:
    st.session_state.sort_by = "market"
if "ascending" not in st.session_state:
    st.session_state.ascending = True


# Dark Theme Styling (remains the same)
st.markdown("""
    <style>
        .block-container { padding-top: 1rem; }
        header { visibility: hidden; }
        .stApp { background-color: #0e1a2b; }
        body { background-color: #0e1a2b; color: #ffffff; }
        .element-container { color: #ffffff; }
        .stButton>button {
            background-color: #1b2b44; color: white; border: 1px solid #00c0f2;
            border-radius: 5px; width: 100%;
            margin-bottom: 0.5rem;
        }
        .stButton>button:hover { background-color: #00c0f2; color: black; }
        .stTabs [data-baseweb="tab"] { background-color: #1b2b44; color: white; border: none; }
        .stTabs [aria-selected="true"] { background-color: #00c0f2; color: black; }
        
        div[data-testid="stHorizontalBlock"] > div {
            flex: 1 1 auto;
            min-width: 100px;
        }

        @media (max-width: 768px) {
            div[data-testid="stHorizontalBlock"] > div {
                flex: 1 1 100%;
            }
            .stButton>button{
                width: 100%;
            }
        }
    </style>
""", unsafe_allow_html=True)

st.title("📊 Polymarket Dashboard")

default_wallet =  ["0xa5f8d182b6086ac0713e557fc28497e591da1aff"] # Made default a list
polymarket_url = f"https://polymarket.com/profile/{default_wallet[0]}" # adjusted to show the first wallet
st.markdown(f"""<label for="wallet">Enter Polymarket Wallet(s) (comma-separated) <a href="{polymarket_url}" target="_blank" style="color: #00c0f2; text-decoration: none;">Address</a>:</label>""", unsafe_allow_html=True)
wallet_input = st.text_input("", value=",".join(default_wallet), key="wallet_input") # changed default value

# Update session state with the list of wallet addresses
if wallet_input:
    st.session_state.wallet_addresses = [addr.strip() for addr in wallet_input.split(",")]


@st.cache_data(ttl=60, show_spinner="Fetching Holdings...")
def fetch_holdings(wallet_addresses: List[str]):
    all_holdings = []
    for address in wallet_addresses:
        url = 'https://data-api.polymarket.com/positions?user=' + address
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            df = pd.DataFrame(data)
            if not df.empty:
                df['risk'] = df['initialValue'].round(2)
                df['avgPrice'] = df['avgPrice'].round(2)
                df['curPrice'] = df['curPrice'].round(2)
                df['reward'] = df['size'] - df['initialValue'] + df['realizedPnl']
                df['%_return'] = ((df['reward'] / df['initialValue']) * 100).round(2)
                df['market_link'] = "https://polymarket.com/event/" + df['eventSlug']
                all_holdings.append(df)
        except requests.exceptions.RequestException as e:
            st.error(f"Error fetching holdings for {address}: {e}")
            return pd.DataFrame()  # Return empty DataFrame on error

    if all_holdings:
        combined_df = pd.concat(all_holdings, ignore_index=True)
        return combined_df
    else:
        return pd.DataFrame()

@st.cache_data(ttl=60, show_spinner="Fetching Order Books...")
def fetch_order_books(asset_ids):
    if not asset_ids:
        return {}
    host: str = "https://clob.polymarket.com/"
    key: str = ""
    chain_id: int = 137
    api_keys = st.secrets["username"]
    client = ClobClient(host, key=api_keys, chain_id=chain_id)
    order_books = client.get_order_books([BookParams(token_id=token_id) for token_id in asset_ids])
    order_book_asset = {}

    for order_book in order_books:
        df = json.loads(order_book.json)

        if len(df['bids']) == 0:
            bids_df = pd.DataFrame({'price': [0.0], 'size': [0.0]})
        else:
            bids_df = pd.DataFrame(df['bids']).sort_values(by='price', ascending=True)
            bids_df['price'] = pd.to_numeric(bids_df['price'])

        if len(df['asks']) == 0:
            asks_df = pd.DataFrame({'price': [0.0], 'size': [0.0]})
        else:
            asks_df = pd.DataFrame(df['asks']).sort_values(by='price', ascending=True)
            asks_df['price'] = pd.to_numeric(asks_df['price'])

        bids_df['type'] = 'bid'
        asks_df['type'] = 'ask'

        bids_df['total'] = bids_df['price'] * bids_df['size'].astype(float)
        asks_df['total'] = asks_df['price'] * asks_df['size'].astype(float)

        bids_df['dollar_size'] = bids_df['total'].cumsum()
        asks_df['dollar_size'] = asks_df['total'].cumsum()

        asks_df['asset_id'] = df['asset_id']
        asks_df['hash'] = df['asset_id']
        asks_df['market'] = df['asset_id']
        asks_df['timestamp'] = df['asset_id']

        bids_df['asset_id'] = df['asset_id']
        bids_df['hash'] = df['asset_id']
        bids_df['market'] = df['asset_id']
        bids_df['timestamp'] = df['asset_id']

        if len(bids_df) == 1 and len(asks_df) == 1:
            combined_df = pd.concat([bids_df, asks_df])
        elif len(bids_df) == 1:
            combined_df = pd.concat([bids_df, asks_df], ignore_index=True).sort_values(by='price', ascending=False)
        elif len(asks_df) == 1:
            combined_df = pd.concat([bids_df, asks_df], ignore_index=True).sort_values(by='price', ascending=False)
        else:
            combined_df = pd.concat([bids_df, asks_df], ignore_index=True).sort_values(by='price', ascending=False)

        if 'total' in combined_df.columns:
            del combined_df['total']

        combined_df['price'] = combined_df['price'].astype(float)
        combined_df['size'] = combined_df['size'].astype(float)

        order_book_asset[df['asset_id']] = combined_df

    return order_book_asset

def get_partial_sell_price(position_size, order_book, percent=1.0):
    target_shares = position_size * percent
    remaining_shares = target_shares
    total_sell_value = 0
    final_sell_price = 0

    for idx, row in order_book.iterrows():
        if remaining_shares > 0:
            shares_to_sell = min(remaining_shares, row['size'])
            total_sell_value += shares_to_sell * row['price']
            final_sell_price = row['price']
            remaining_shares -= shares_to_sell
        if remaining_shares <= 0:
            break

    return final_sell_price, total_sell_value

@st.cache_data(show_spinner="Calculating Liquidation Prices...")
def add_partial_sell_prices(stock_info_df, order_books_dict, percent_list):
    if stock_info_df.empty:
        return stock_info_df
    stock_info_df['asset'] = stock_info_df['asset'].astype(str)

    for percent in percent_list:
        sell_prices = []
        total_values = []
        mark_pnls = []

        for _, stock in stock_info_df.iterrows():
            stock_name = stock['asset']
            order_book = order_books_dict.get(stock_name)
            if order_book is None:
                sell_prices.append(0)
                total_values.append(0)
                mark_pnls.append(0)
                continue

            order_book = order_book[order_book['type'] == 'bid'].sort_values(by='price', ascending=False)
            sell_price, total_sell_value = get_partial_sell_price(stock['size'], order_book, percent)
            sell_prices.append(sell_price)
            total_values.append(total_sell_value)

            partial_risk = stock['risk'] * percent
            mark_pnls.append(total_sell_value - partial_risk)

        pct_label = int(percent * 100)
        stock_info_df[f'sell_price_{pct_label}%'] = sell_prices
        stock_info_df[f'total_sell_value_{pct_label}%'] = total_values
        stock_info_df[f'market_pnl_{pct_label}%'] = mark_pnls

    if not stock_info_df['size'].fillna(0).astype(float).eq(0).all():
        stock_info_df['sell_price_100%'] = (stock_info_df['total_sell_value_100%'] / stock_info_df['size']).round(2)
    else:
        stock_info_df['sell_price_100%'] = 0.0
    return stock_info_df

def extract_date_from_title(title: str) -> str:
    """
    Extracts a date from the title string, looking for "before", "after", or "by".
    Returns a string in YYYY-MM-DD format if found, otherwise "".
    """
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    date_patterns = [
        r"(before|after|by)\s*(\w+)\s*(\d{1,2})",  # e.g., "before May 31"
        r"(\w+)\s*(\d{1,2})\s*(before|after|by)",  # e.g., "May 31 before"
        r"(\d{4})",                                  # e.g., "2025"
    ]

    for pattern in date_patterns:
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            if pattern == r"(\d{4})":
                year = int(match.group(1))
                return f"{year}-12-31"  # Default to Dec 31 if only year is found

            else:
                month_str = match.group(2) if pattern.find("before|after|by") else match.group(1)
                day = int(match.group(3)) if pattern.find("before|after|by") else int(match.group(2))
                try:
                    month = next(i for i, m in enumerate(month_names, 1) if m.lower() == month_str[:3].lower())
                except StopIteration:
                    return ""  # Return empty string if month is invalid
                year = 2025  # Hardcoded year, adjust if needed
                return f"{year}-{month:02d}-{day:02d}"

    return ""  # Return empty string if no date found

risk_mapping = {(97, 99): "Very Low Risk",
    (91, 96): "Low Risk",
    (87, 90): "Moderately Low Risk",
    (79, 86): "Moderate Risk",
    (71, 79): "Moderately High Risk",
    (61, 70): "High Risk",
    (50, 60): "Very High Risk",
    (40, 49): "Extremely High Risk",
    (20, 30): "Speculative Risk",
    (0, 19): "Extreme Risk",}

# Create a DataFrame to display
risk_df = pd.DataFrame([{"Risk Category": v, "Score Range": f"{k[0]}%-{k[1]}%"}
    for k, v in risk_mapping.items()])

def get_risk_info_from_price(price):
    """
    Categorizes the risk and returns both the risk label and probability range
    based on the price of a share.
    Args:
        price (float): The price of a share (0.00 to 1.00).
    Returns:
        tuple: (risk_label, probability_range_str)
            Returns ("Invalid Price", "N/A") for invalid prices.
    """
    if not 0.00 <= price <= 1.00:
        return "Invalid Price", "N/A"
    probability_percentage = int(price * 100)
    for (lower_bound, upper_bound), label in risk_mapping.items():
        if lower_bound <= probability_percentage <= upper_bound:
            return label, f"{lower_bound}-{upper_bound}%"
    return "Invalid Probability", "N/A"  # Should not reach here if price is valid

def risk_color_scale(risk_value):
    # You can adjust these colors to fit your theme or use a gradient
    if 97 <= risk_value <= 99:
        return "#00f27d"  # Very Low Risk – Green
    elif 91 <= risk_value <= 96:
        return "#6ce191"
    elif 87 <= risk_value <= 90:
        return "#a6e17d"
    elif 79 <= risk_value <= 86:
        return "#e1df6c"
    elif 71 <= risk_value <= 78:
        return "#f4c242"
    elif 61 <= risk_value <= 70:
        return "#f79f3d"
    elif 50 <= risk_value <= 60:
        return "#f76d6d"
    elif 40 <= risk_value <= 49:
        return "#e1457b"
    elif 20 <= risk_value <= 39:
        return "#ba1f64"
    else:
        return "#a3004f"  # Extreme Risk – Deep Red

# Fetch and process data based on the current wallet address in session state
holdings_df = fetch_holdings(st.session_state.wallet_addresses)  # Pass the list
dt_open = holdings_df[holdings_df['redeemable'] == False].reset_index(drop=True) if not holdings_df.empty else pd.DataFrame()
asset_ids = dt_open['asset'].tolist() if not dt_open.empty else []
order_book_asset = fetch_order_books(asset_ids)

percent_list = [0.25, 0.50, 0.75, 1]
stock_info_df = add_partial_sell_prices(dt_open.copy(), order_book_asset, percent_list).sort_values(by='title', ascending=True) if not dt_open.empty else pd.DataFrame()
# Apply the mapping to create the 'risk' and 'probability_range' columns
stock_info_df[['risk_range', 'probability_range']] = stock_info_df['curPrice'].apply(lambda x: pd.Series(get_risk_info_from_price(x)))

if not stock_info_df.empty:
    df = pd.DataFrame({"market": stock_info_df['title'],
        "outcome": stock_info_df['outcome'].str.capitalize(),
        "shares": stock_info_df['size'].round(1),
        "avg": (stock_info_df['avgPrice'] * 100).round(2),
        "reward": stock_info_df['reward'].round(2),
        "return_pct": stock_info_df['%_return'],
        "risk": stock_info_df['risk'],
        "current": (stock_info_df['curPrice'] * 100).round(2),
        "value": stock_info_df['currentValue'].round(2),
        "liquidation_25%": stock_info_df['market_pnl_25%'].round(2),
        "sell_25": stock_info_df['sell_price_25%'].round(2),
        "liquidation_50%": stock_info_df['market_pnl_50%'].round(2),
        "liquidation_75%": stock_info_df['market_pnl_75%'].round(2),
        "liquidation_100%": stock_info_df['market_pnl_100%'].round(2),
        "initial_value": stock_info_df['initialValue'].round(2),
        "pnl": (stock_info_df['currentValue'] - stock_info_df['initialValue']).round(2),
        "liquidation pnl": stock_info_df['market_pnl_100%'].round(2),
        "pnl_percent": stock_info_df['percentPnl'].round(2),
        "icon": stock_info_df['icon'],
        "market_link": stock_info_df['market_link'],
        "risk_range": stock_info_df['risk_range'],
        "end_date": stock_info_df.apply(lambda row: row['endDate'] if row['endDate'] else extract_date_from_title(row['title']), axis=1)})
    
    # Total Metrics
    total_risk = df['risk'].sum().round(2)
    total_value = df['value'].sum().round(2)
    total_pnl = df['pnl'].sum().round(2)
    market_pnl = df['liquidation_100%'].sum().round(2)

    col_a, col_b, col_c, col_d = st.columns(4)
    col_a.metric("💸 Total Risk", f"${total_risk:,.2f}")
    col_b.metric("📈 Total Value", f"${total_value:,.2f}")
    col_c.metric("📈 Market Value", f"${market_pnl:,.2f}")
    pnl_color = "🟢" if total_pnl > 0 else "🔴"
    col_d.metric(f"{pnl_color} Total PnL", f"${total_pnl:,.2f}")

    tabs = st.tabs(["📋 Dashboard", "📈 Analytics", '💸 PNL Range   '])
    with st.expander("📊 View Risk Classification Table"):
        st.table(risk_df)

    

    with tabs[0]:
        # Use st.columns with a list to define the column widths
        cols = [3, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]  # 12 values
        col_headers = st.columns(cols)

        def header_button(label, col_name):
            arrow = "↑" if st.session_state.sort_by == col_name and st.session_state.ascending else "↓"
            if st.button(f"{label} {arrow}" if st.session_state.sort_by == col_name else label, key=f"sort_button_{col_name}"):
                if st.session_state.sort_by == col_name:
                    st.session_state.ascending = not st.session_state.ascending
                else:
                    st.session_state.sort_by = col_name
                    st.session_state.ascending = True

        # Apply header_button to each column
        with col_headers[0]: header_button("MARKET", "market")
        with col_headers[1]: header_button("Risk Level", "risk_range")
        with col_headers[2]: header_button("Close Date", "end_date")
        with col_headers[3]: header_button("AVG", "avg")
        with col_headers[4]: header_button("CURRENT", "current")
        with col_headers[5]: header_button("RISK", "risk")
        with col_headers[6]: header_button("Liq 25%", "liquidation_25%")
        with col_headers[7]: header_button("Liq 50%", "liquidation_50%")
        with col_headers[8]: header_button("Liq 75%", "liquidation_75%")
        with col_headers[9]: header_button("Liq 100%", "liquidation pnl")
        with col_headers[10]: header_button("REWARD", "reward")
        with col_headers[11]: header_button("VALUE", "value")
        

        df = df.sort_values(by=st.session_state.sort_by, ascending=st.session_state.ascending)
    
        for _, row in df.iterrows():
            outcome_bg = "#f76d6d" if row['outcome'] == "No" else "#00c0f2"
            outcome_color = "#000"
            pnl_color = "#00f27d" if row['pnl'] > 0 else "#f76d6d"

            tooltip = ""
            for (low, high), label in risk_mapping.items():
                if low <= row['avg'] <= high:
                    tooltip = f"{label}: {low}%-{high}%"
                    break

            # HTML span with tooltip on hover
            risk_range_html = f"""
            <span title="{tooltip}" style="cursor: pointer; text-decoration: underline; color: #00c0f2;" onclick="alert('{tooltip}')">
                {row['risk_range']}
            </span>
            """
            
            st.markdown(f"""
            <div style="display: flex; align-items: center; border-bottom: 1px solid #1b2b44; padding: 10px 0; word-wrap: break-word;">
                <div style="flex: 3; display: flex; align-items: center;  min-width: 100px; max-width: 250px; overflow-x: auto;">  
                    <img src="{row['icon']}" width="40" height="40" style="border-radius: 4px; object-fit: cover; margin-right: 10px;" />
                    <div style="word-wrap: break-word;">
                        <div style="font-weight: 700; font-size: 15px; color: #ffffff; word-wrap: break-word;">
                            <a href='{row['market_link']}' target='_blank' style='color: #ffffff; text-decoration: none; word-wrap: break-word;'>{row['market']}</a>
                        </div>
                        <div style="margin-top: 5px; font-size: 12px; color: #b0b8c4; display: flex; align-items: center; gap: 8px; word-wrap: break-word;">
                            <span style="background: {outcome_bg}; color: {outcome_color}; padding: 2px 8px; border-radius: 6px; font-weight: bold; font-size: 11px; word-wrap: break-word;">{row['outcome']}</span>
                            {row['shares']:.1f} shares
                        </div> 
                    </div>
                </div>
                <div style="flex: 1; display: flex; align-items: center; justify-content: center; gap: 8px; min-width: 100px; max-width: 150px; overflow-x: auto;">
    <div style="width: 10px; height: 24px; border-radius: 4px; background-color: {risk_color_scale(row['current'])};"></div>
    <span>{risk_range_html}</span>
</div>
                <div style="flex: 1; text-align: center; min-width: 100px; max-width: 120px; overflow-x: auto;">{row['end_date']}</div>
                <div style="flex: 1; text-align: center; min-width: 100px; max-width: 100px; overflow-x: auto;">{row['avg']:.0f}¢</div>
                <div style="flex: 1; text-align: center; min-width: 100px; max-width: 100px; overflow-x: auto;">{row['current']:.0f}¢</div>
                <div style="flex: 1; text-align: center; min-width: 100px; max-width: 100px; overflow-x: auto;">${row['risk']:.2f}</div>
                <div style="flex: 1; text-align: center; color: {('#00f27d' if row['liquidation_25%'] > 0 else '#f76d6d')}; min-width: 100px; max-width: 120px; overflow-x: auto;">${row['liquidation_25%']:.2f}</div>
                <div style="flex: 1; text-align: center; color: {('#00f27d' if row['liquidation_50%'] > 0 else '#f76d6d')}; min-width: 100px; max-width: 120px; overflow-x: auto;">${row['liquidation_50%']:.2f}</div>
                <div style="flex: 1; text-align: center; color: {('#00f27d' if row['liquidation_75%'] > 0 else '#f76d6d')}; min-width: 100px; max-width: 120px; overflow-x: auto;">${row['liquidation_75%']:.2f}</div>
                <div style="flex: 1; text-align: center; color: {('#00f27d' if row['liquidation pnl'] > 0 else '#f76d6d')}; min-width: 100px; max-width: 120px; overflow-x: auto;">${row['liquidation pnl']:.2f}</div>
                <div style="flex: 1; text-align: center; min-width: 100px; max-width: 120px; overflow-x: auto;">${row['reward']:.2f}<div style="font-size: 12px; word-wrap: break-word;">{row['return_pct']:.2f}%</div></div>
                <div style="flex: 1; text-align: right; padding-right: 10px; min-width: 100px; max-width: 150px; overflow-x: auto; word-wrap: break-word;">${row['value']:.2f}<div style="font-size: 12px; color: {pnl_color}; word-wrap: break-word;">{f'+${row["pnl"]:.2f}' if row['pnl'] > 0 else f'${row["pnl"]:.2f}'} ({row['pnl_percent']:.2f}%)</div></div>
            </div>
            """, unsafe_allow_html=True)

    with tabs[1]:
        st.subheader("📊 Portfolio Analytics")

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("### PnL by Market")
            pnl_chart = px.bar(df.sort_values('pnl', ascending=False),
                x='market',
                y='pnl',
                color='pnl',
                color_continuous_scale='RdYlGn',
                title="PnL (Profit & Loss) by Market",
                labels={'pnl': 'PnL ($)', 'market': 'Market'},
                text_auto=".2s")
            pnl_chart.update_layout(
                xaxis_title="Market",
                yaxis_title="PnL ($)",
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                font=dict(color='white'))
            st.plotly_chart(pnl_chart, use_container_width=True)

        with col2:
            st.markdown("### Current Value by Market")
            value_chart = px.bar(
                df.sort_values('value', ascending=False),
                x='market',
                y='value',
                color='value',
                color_continuous_scale='Blues',
                title="Current Value by Market",
                labels={'value': 'Value ($)', 'market': 'Market'},
                text_auto=".2s")
            value_chart.update_layout(
                xaxis_title="Market",
                yaxis_title="Current Value ($)",
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                font=dict(color='white'))
            st.plotly_chart(value_chart, use_container_width=True)

        st.markdown("### Detailed Market Table")
        st.dataframe(df[["market", "outcome", "shares", 'end_date', "avg", "current", "risk", "liquidation_25%", "liquidation_50%", "liquidation_75%", "liquidation pnl", "reward", "return_pct", "value", "pnl"]],
            use_container_width=True,
            hide_index=True)
    with tabs[2]:
        dt = df.copy()
        dt['end_date'] = pd.to_datetime(dt['end_date'], format='%Y-%m-%d')
        dt['end_date'] = dt['end_date'].dt.strftime('%Y-%m-%d')
        dt['liquidation pnl'] = dt['liquidation pnl'].round(2)
        dt['End Date'] = pd.to_datetime(dt['end_date'])
        dt = dt.sort_values('End Date')
        #dt = dt.groupby('end_date')['liquidation pnl'].sum().reset_index()
        dt = dt.groupby(['End Date','risk_range']).agg({'liquidation pnl': 'sum'}).reset_index()

        st.dataframe(dt,
                    use_container_width=True,
                    hide_index=False)
