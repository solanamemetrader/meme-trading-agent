from dotenv import load_dotenv
import os
import json
import requests
from datetime import datetime, timezone

load_dotenv()

API_KEY = os.getenv("BIRDEYE_API_KEY")

print("RUNNING ROLLING MOMENTUM HISTORY VERSION")

HEADERS = {
    "X-API-KEY": API_KEY,
    "x-chain": "solana"
}

TRENDING_URL = "https://public-api.birdeye.so/defi/token_trending"
OVERVIEW_URL = "https://public-api.birdeye.so/defi/token_overview"
TRADE_URL = "https://public-api.birdeye.so/defi/txs/token"

HISTORY_FILE = "scanner_history.json"

# Keep the last 20 readings for each token.
MAX_HISTORY_PER_TOKEN = 20


# =================================
# BASIC HELPERS
# =================================

def safe_number(value):
    try:
        if value is None:
            return 0.0

        return float(value)

    except (TypeError, ValueError):
        return 0.0


def percent_change(old_value, new_value):

    if old_value <= 0:
        return 0.0

    return (
        (new_value - old_value)
        / old_value
    ) * 100


# =================================
# HISTORY
# =================================

def load_history():

    if not os.path.exists(HISTORY_FILE):
        return {}

    try:

        with open(
            HISTORY_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(file)

        if isinstance(data, dict):
            return data

        return {}

    except Exception:
        return {}


def save_history(history):

    try:

        with open(
            HISTORY_FILE,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                history,
                file,
                indent=2
            )

    except Exception as error:

        print()
        print(
            "Could not save history:"
        )

        print(error)


def get_previous_snapshot(
    history,
    address
):

    token_history = history.get(
        address,
        []
    )

    if not token_history:
        return None

    return token_history[-1]


def add_snapshot(
    history,
    address,
    snapshot
):

    if address not in history:
        history[address] = []

    history[address].append(
        snapshot
    )

    history[address] = (
        history[address][
            -MAX_HISTORY_PER_TOKEN:
        ]
    )


# =================================
# MOMENTUM COMPARISON
# =================================

def calculate_momentum(
    previous,
    current
):

    if not previous:

        return {
            "trend": "NEW",
            "score": 0,

            "buy_pressure_delta": 0,
            "transaction_ratio_delta": 0,
            "volume_change_percent": 0,
            "buy_pressure_15m_delta": 0,
            "price_change_delta": 0
        }


    previous_buy_pressure = safe_number(
        previous.get(
            "buy_pressure_5m"
        )
    )

    previous_transaction_ratio = safe_number(
        previous.get(
            "transaction_buy_ratio_5m"
        )
    )

    previous_volume = safe_number(
        previous.get(
            "total_volume_5m"
        )
    )

    previous_buy_pressure_15m = safe_number(
        previous.get(
            "buy_pressure_15m"
        )
    )

    previous_price_change = safe_number(
        previous.get(
            "price_change_5m"
        )
    )


    current_buy_pressure = safe_number(
        current.get(
            "buy_pressure_5m"
        )
    )

    current_transaction_ratio = safe_number(
        current.get(
            "transaction_buy_ratio_5m"
        )
    )

    current_volume = safe_number(
        current.get(
            "total_volume_5m"
        )
    )

    current_buy_pressure_15m = safe_number(
        current.get(
            "buy_pressure_15m"
        )
    )

    current_price_change = safe_number(
        current.get(
            "price_change_5m"
        )
    )


    buy_pressure_delta = (
        current_buy_pressure
        - previous_buy_pressure
    )

    transaction_ratio_delta = (
        current_transaction_ratio
        - previous_transaction_ratio
    )

    volume_change_percent = percent_change(
        previous_volume,
        current_volume
    )

    buy_pressure_15m_delta = (
        current_buy_pressure_15m
        - previous_buy_pressure_15m
    )

    price_change_delta = (
        current_price_change
        - previous_price_change
    )


    momentum_score = 0


    # ---------------------------------
    # 5M BUY PRESSURE TREND
    # ---------------------------------

    if buy_pressure_delta >= 5:

        momentum_score += 2

    elif buy_pressure_delta >= 2:

        momentum_score += 1

    elif buy_pressure_delta <= -5:

        momentum_score -= 2

    elif buy_pressure_delta <= -2:

        momentum_score -= 1


    # ---------------------------------
    # TRANSACTION BREADTH TREND
    # ---------------------------------

    if transaction_ratio_delta >= 5:

        momentum_score += 2

    elif transaction_ratio_delta >= 2:

        momentum_score += 1

    elif transaction_ratio_delta <= -5:

        momentum_score -= 2

    elif transaction_ratio_delta <= -2:

        momentum_score -= 1


    # ---------------------------------
    # 5M VOLUME TREND
    # ---------------------------------

    if volume_change_percent >= 50:

        momentum_score += 2

    elif volume_change_percent >= 20:

        momentum_score += 1

    elif volume_change_percent <= -50:

        momentum_score -= 2

    elif volume_change_percent <= -20:

        momentum_score -= 1


    # ---------------------------------
    # 15M BUY PRESSURE TREND
    # ---------------------------------

    if buy_pressure_15m_delta >= 4:

        momentum_score += 1

    elif buy_pressure_15m_delta <= -4:

        momentum_score -= 1


    # ---------------------------------
    # PRICE MOMENTUM TREND
    # ---------------------------------

    if price_change_delta >= 1:

        momentum_score += 1

    elif price_change_delta <= -1:

        momentum_score -= 1


    # ---------------------------------
    # TREND LABEL
    # ---------------------------------

    if momentum_score >= 5:

        trend = "ACCELERATING"

    elif momentum_score >= 2:

        trend = "RISING"

    elif momentum_score <= -5:

        trend = "FALLING FAST"

    elif momentum_score <= -2:

        trend = "FALLING"

    else:

        trend = "MIXED"


    return {
        "trend":
            trend,

        "score":
            momentum_score,

        "buy_pressure_delta":
            buy_pressure_delta,

        "transaction_ratio_delta":
            transaction_ratio_delta,

        "volume_change_percent":
            volume_change_percent,

        "buy_pressure_15m_delta":
            buy_pressure_15m_delta,

        "price_change_delta":
            price_change_delta
    }


# =================================
# INDIVIDUAL TRADE HELPERS
# =================================

def get_trade_usd(trade):

    quote = trade.get("quote") or {}
    base = trade.get("base") or {}

    quote_amount = safe_number(
        quote.get("uiAmount")
    )

    quote_price = safe_number(
        trade.get("quotePrice")
    )

    base_amount = safe_number(
        base.get("uiAmount")
    )

    base_price = safe_number(
        trade.get("basePrice")
    )

    quote_usd = (
        quote_amount
        * quote_price
    )

    base_usd = (
        base_amount
        * base_price
    )

    if quote_usd > 0:
        return quote_usd

    if base_usd > 0:
        return base_usd

    return 0.0


def get_recent_trade_pressure(
    address
):

    params = {
        "address": address,
        "tx_type": "swap",
        "sort_type": "desc",
        "offset": 0,
        "limit": 10
    }

    empty_result = {
        "available": False,
        "buy_count": 0,
        "sell_count": 0,
        "buy_usd": 0,
        "sell_usd": 0,
        "buy_ratio": 0,
        "buy_pressure": 0,
        "net_flow": 0,
        "pass": False
    }

    try:

        response = requests.get(
            TRADE_URL,
            headers=HEADERS,
            params=params,
            timeout=15
        )

        if response.status_code != 200:
            return empty_result

        data = response.json()

        if not data.get("success"):
            return empty_result

        items = (
            data.get("data", {})
            .get("items", [])
        )


        buy_count = 0
        sell_count = 0

        buy_usd = 0
        sell_usd = 0


        for trade in items:

            side = str(
                trade.get(
                    "side",
                    ""
                )
            ).lower()

            trade_usd = get_trade_usd(
                trade
            )

            if trade_usd <= 0:
                continue


            if side == "buy":

                buy_count += 1
                buy_usd += trade_usd


            elif side == "sell":

                sell_count += 1
                sell_usd += trade_usd


        total_count = (
            buy_count
            + sell_count
        )

        total_usd = (
            buy_usd
            + sell_usd
        )


        if total_count > 0:

            buy_ratio = (
                buy_count
                / total_count
            ) * 100

        else:

            buy_ratio = 0


        if total_usd > 0:

            buy_pressure = (
                buy_usd
                / total_usd
            ) * 100

        else:

            buy_pressure = 0


        net_flow = (
            buy_usd
            - sell_usd
        )


        recent_trade_pass = (
            buy_count > sell_count
            and buy_usd > sell_usd
        )


        return {
            "available":
                True,

            "buy_count":
                buy_count,

            "sell_count":
                sell_count,

            "buy_usd":
                buy_usd,

            "sell_usd":
                sell_usd,

            "buy_ratio":
                buy_ratio,

            "buy_pressure":
                buy_pressure,

            "net_flow":
                net_flow,

            "pass":
                recent_trade_pass
        }


    except Exception:

        return empty_result


# =================================
# LOAD PREVIOUS HISTORY
# =================================

history = load_history()

run_time = datetime.now(
    timezone.utc
).isoformat()


# =================================
# DISCOVER TRENDING TOKENS
# =================================

trending_params = {
    "sort_by": "rank",
    "sort_type": "asc",
    "interval": "1h",
    "offset": 0,
    "limit": 25
}


try:

    response = requests.get(
        TRENDING_URL,
        headers=HEADERS,
        params=trending_params,
        timeout=15
    )

    trending_data = response.json()


except Exception as error:

    print(
        "Trending request failed:"
    )

    print(error)

    exit()


if not trending_data.get(
    "success"
):

    print(
        "Could not load trending tokens"
    )

    exit()


tokens = [
    token.get("address")
    for token
    in trending_data["data"]["tokens"]
    if token.get("address")
]


print()
print(
    "Discovered",
    len(tokens),
    "trending Solana tokens"
)


results = []

analyzed_count = 0


# =================================
# ANALYZE TOKENS
# =================================

for address in tokens:

    try:

        response = requests.get(
            OVERVIEW_URL,
            headers=HEADERS,
            params={
                "address":
                    address,

                "frames":
                    "5m,15m"
            },
            timeout=15
        )

        data = response.json()


    except Exception:

        continue


    if not data.get(
        "success"
    ):
        continue


    token = data.get(
        "data"
    )

    if not token:
        continue


    analyzed_count += 1


    name = (
        token.get("name")
        or "Unknown"
    )

    symbol = (
        token.get("symbol")
        or "Unknown"
    )


    # =================================
    # 5M DATA
    # =================================

    price = safe_number(
        token.get("price")
    )

    buy_volume_5m = safe_number(
        token.get(
            "vBuy5mUSD"
        )
    )

    sell_volume_5m = safe_number(
        token.get(
            "vSell5mUSD"
        )
    )

    buy_count_5m = safe_number(
        token.get("buy5m")
    )

    sell_count_5m = safe_number(
        token.get("sell5m")
    )

    price_change_5m = safe_number(
        token.get(
            "priceChange5mPercent"
        )
    )

    volume_change_5m = safe_number(
        token.get(
            "v5mChangePercent"
        )
    )


    # =================================
    # 15M DATA
    # =================================

    buy_volume_15m = safe_number(
        token.get(
            "vBuy15mUSD"
        )
    )

    sell_volume_15m = safe_number(
        token.get(
            "vSell15mUSD"
        )
    )

    buy_count_15m = safe_number(
        token.get("buy15m")
    )

    sell_count_15m = safe_number(
        token.get("sell15m")
    )

    price_change_15m = safe_number(
        token.get(
            "priceChange15mPercent"
        )
    )


    # =================================
    # MARKET DATA
    # =================================

    liquidity = safe_number(
        token.get("liquidity")
    )

    holders = safe_number(
        token.get("holder")
    )


    # =================================
    # 5M BUY PRESSURE
    # =================================

    total_volume_5m = (
        buy_volume_5m
        + sell_volume_5m
    )


    if total_volume_5m > 0:

        buy_pressure_5m = (
            buy_volume_5m
            / total_volume_5m
        ) * 100

    else:

        buy_pressure_5m = 0


    # =================================
    # 5M TRANSACTION RATIO
    # =================================

    total_count_5m = (
        buy_count_5m
        + sell_count_5m
    )


    if total_count_5m > 0:

        transaction_buy_ratio_5m = (
            buy_count_5m
            / total_count_5m
        ) * 100

    else:

        transaction_buy_ratio_5m = 0


    transaction_confirmation_pass = (
        transaction_buy_ratio_5m
        >= 50
    )


    # =================================
    # TRANSACTION SCORE
    # =================================

    transaction_score = 0


    if transaction_buy_ratio_5m >= 60:

        transaction_score = 2

    elif transaction_buy_ratio_5m >= 55:

        transaction_score = 1

    elif transaction_buy_ratio_5m < 40:

        transaction_score = -2

    elif transaction_buy_ratio_5m < 45:

        transaction_score = -1


    # =================================
    # 15M BUY PRESSURE
    # =================================

    total_volume_15m = (
        buy_volume_15m
        + sell_volume_15m
    )


    if total_volume_15m > 0:

        buy_pressure_15m = (
            buy_volume_15m
            / total_volume_15m
        ) * 100

    else:

        buy_pressure_15m = 0


    total_count_15m = (
        buy_count_15m
        + sell_count_15m
    )


    if total_count_15m > 0:

        transaction_buy_ratio_15m = (
            buy_count_15m
            / total_count_15m
        ) * 100

    else:

        transaction_buy_ratio_15m = 0


    # =================================
    # BASE SCORE
    # =================================

    base_score = 0


    if buy_pressure_5m >= 70:

        base_score += 3

    elif buy_pressure_5m >= 65:

        base_score += 2

    elif buy_pressure_5m >= 55:

        base_score += 1


    if price_change_5m > 3:

        base_score += 2

    elif price_change_5m > 1:

        base_score += 1

    elif price_change_5m < -3:

        base_score -= 2

    elif price_change_5m < -1:

        base_score -= 1


    if volume_change_5m > 50:

        base_score += 2

    elif volume_change_5m > 25:

        base_score += 1

    elif volume_change_5m < -50:

        base_score -= 2

    elif volume_change_5m < -25:

        base_score -= 1


    # =================================
    # VOLUME SCORE
    # =================================

    volume_score = 0


    if total_volume_5m >= 500000:

        volume_score = 3

    elif total_volume_5m >= 100000:

        volume_score = 2

    elif total_volume_5m >= 25000:

        volume_score = 1


    # =================================
    # CONFIRMATION SCORE
    # =================================

    confirmation_score = 0


    if buy_pressure_15m >= 60:

        confirmation_score += 2

    elif buy_pressure_15m >= 55:

        confirmation_score += 1


    if price_change_15m > 1:

        confirmation_score += 1

    elif price_change_15m < -3:

        confirmation_score -= 1


    # =================================
    # FINAL SCORE
    # =================================

    final_score = (
        base_score
        + volume_score
        + confirmation_score
        + transaction_score
    )


    # =================================
    # BUILD HISTORY SNAPSHOT
    # =================================

    current_snapshot = {

        "time":
            run_time,

        "name":
            name,

        "symbol":
            symbol,

        "price":
            price,

        "buy_pressure_5m":
            buy_pressure_5m,

        "transaction_buy_ratio_5m":
            transaction_buy_ratio_5m,

        "total_volume_5m":
            total_volume_5m,

        "price_change_5m":
            price_change_5m,

        "volume_change_5m":
            volume_change_5m,

        "buy_pressure_15m":
            buy_pressure_15m,

        "transaction_buy_ratio_15m":
            transaction_buy_ratio_15m,

        "price_change_15m":
            price_change_15m,

        "liquidity":
            liquidity,

        "holders":
            holders,

        "final_score":
            final_score
    }


    previous_snapshot = (
        get_previous_snapshot(
            history,
            address
        )
    )


    momentum = calculate_momentum(
        previous_snapshot,
        current_snapshot
    )


    # Save EVERY analyzed token.
    add_snapshot(
        history,
        address,
        current_snapshot
    )


    # =================================
    # FILTERS
    # =================================

    score_pass = (
        final_score >= 2
    )

    buy_pressure_pass = (
        buy_pressure_5m >= 55
    )

    volume_pass = (
        total_volume_5m >= 5000
    )

    liquidity_pass = (
        liquidity >= 50000
    )

    holders_pass = (
        holders >= 500
    )


    if total_volume_5m > 0:

        liquidity_volume_ratio = (
            liquidity
            / total_volume_5m
        )

    else:

        liquidity_volume_ratio = 0


    market_structure_pass = (
        liquidity_volume_ratio >= 0.10
    )


    confirmation_pass = (
        buy_pressure_15m >= 50
    )


    early_momentum_pass = (
        buy_pressure_5m >= 60
        and buy_pressure_15m >= 40
        and buy_pressure_15m < 50
        and volume_pass
    )


    all_filters_pass = (
        score_pass
        and buy_pressure_pass
        and volume_pass
        and liquidity_pass
        and holders_pass
        and market_structure_pass
        and (
            confirmation_pass
            or early_momentum_pass
        )
    )


    if not all_filters_pass:
        continue


    # =================================
    # RECENT 10 TRADES
    # =================================

    recent = get_recent_trade_pressure(
        address
    )


    # Add recent trade information to
    # the current history snapshot too.

    current_snapshot[
        "recent_trade_available"
    ] = recent["available"]

    current_snapshot[
        "recent_net_flow"
    ] = recent["net_flow"]

    current_snapshot[
        "recent_buy_pressure"
    ] = recent["buy_pressure"]

    current_snapshot[
        "recent_trade_pass"
    ] = recent["pass"]


    # Because current_snapshot is already
    # inside history, these new values are
    # now part of the saved snapshot.


    # =================================
    # SIGNAL
    # =================================

    if (
        final_score >= 6
        and confirmation_pass
        and buy_pressure_5m >= 55
        and transaction_confirmation_pass
        and recent["pass"]
    ):

        signal = "STRONG BUY"


    elif (
        final_score >= 6
        and confirmation_pass
        and transaction_confirmation_pass
        and not recent["pass"]
    ):

        signal = (
            "WATCH - RECENT TRADES WEAK"
        )


    elif (
        early_momentum_pass
        and recent["pass"]
    ):

        signal = "EARLY MOMENTUM"


    elif (
        confirmation_pass
        and transaction_confirmation_pass
        and recent["pass"]
    ):

        signal = "WATCH / BULLISH"


    elif (
        confirmation_pass
        and not recent["pass"]
    ):

        signal = (
            "WATCH - RECENT TRADES WEAK"
        )


    elif confirmation_pass:

        signal = (
            "WATCH - TRANSACTIONS UNCONFIRMED"
        )


    else:

        signal = "NEUTRAL"


    # =================================
    # SAVE QUALIFYING RESULT
    # =================================

    results.append({

        "name":
            name,

        "symbol":
            symbol,

        "address":
            address,

        "price":
            price,

        "buy_pressure_5m":
            buy_pressure_5m,

        "buy_count_5m":
            buy_count_5m,

        "sell_count_5m":
            sell_count_5m,

        "transaction_buy_ratio_5m":
            transaction_buy_ratio_5m,

        "total_volume_5m":
            total_volume_5m,

        "price_change_5m":
            price_change_5m,

        "volume_change_5m":
            volume_change_5m,

        "buy_pressure_15m":
            buy_pressure_15m,

        "transaction_buy_ratio_15m":
            transaction_buy_ratio_15m,

        "price_change_15m":
            price_change_15m,

        "liquidity":
            liquidity,

        "holders":
            holders,

        "liquidity_volume_ratio":
            liquidity_volume_ratio,

        "base_score":
            base_score,

        "volume_score":
            volume_score,

        "confirmation_score":
            confirmation_score,

        "transaction_score":
            transaction_score,

        "final_score":
            final_score,

        "recent_available":
            recent["available"],

        "recent_buy_count":
            recent["buy_count"],

        "recent_sell_count":
            recent["sell_count"],

        "recent_buy_usd":
            recent["buy_usd"],

        "recent_sell_usd":
            recent["sell_usd"],

        "recent_buy_ratio":
            recent["buy_ratio"],

        "recent_buy_pressure":
            recent["buy_pressure"],

        "recent_net_flow":
            recent["net_flow"],

        "recent_trade_pass":
            recent["pass"],

        "momentum_trend":
            momentum["trend"],

        "momentum_score":
            momentum["score"],

        "buy_pressure_delta":
            momentum[
                "buy_pressure_delta"
            ],

        "transaction_ratio_delta":
            momentum[
                "transaction_ratio_delta"
            ],

        "history_volume_change":
            momentum[
                "volume_change_percent"
            ],

        "buy_pressure_15m_delta":
            momentum[
                "buy_pressure_15m_delta"
            ],

        "price_change_delta":
            momentum[
                "price_change_delta"
            ],

        "signal":
            signal
    })


# =================================
# SAVE HISTORY FILE
# =================================

save_history(
    history
)


print()
print(
    "Analyzed tokens:",
    analyzed_count
)

print(
    "History saved to:",
    HISTORY_FILE
)


# =================================
# RANK RESULTS
# =================================

results.sort(
    key=lambda token: (
        token["recent_trade_pass"],
        token["final_score"],
        token["momentum_score"],
        token["transaction_buy_ratio_5m"],
        token["total_volume_5m"]
    ),
    reverse=True
)


# =================================
# DISPLAY RESULTS
# =================================

print()
print("===================================")
print("QUALIFYING TOKEN RESULTS")
print("===================================")

print(
    "Qualifying tokens:",
    len(results)
)


if not results:

    print()
    print(
        "No qualifying setups right now."
    )


else:

    for position, token in enumerate(
        results,
        start=1
    ):

        print()
        print(
            "-----------------------------------"
        )

        print(
            "Rank:",
            position
        )

        print(
            "Token:",
            token["name"],
            "(" + token["symbol"] + ")"
        )

        print(
            "Address:",
            token["address"]
        )

        print(
            "Price: $",
            round(
                token["price"],
                8
            )
        )


        # =================================
        # 5M
        # =================================

        print()
        print("5M DATA")

        print(
            "5m Buy Pressure:",
            round(
                token[
                    "buy_pressure_5m"
                ],
                1
            ),
            "%"
        )

        print(
            "5m Buy Transactions:",
            int(
                token["buy_count_5m"]
            )
        )

        print(
            "5m Sell Transactions:",
            int(
                token["sell_count_5m"]
            )
        )

        print(
            "5m Transaction Buy Ratio:",
            round(
                token[
                    "transaction_buy_ratio_5m"
                ],
                1
            ),
            "%"
        )

        print(
            "5m Volume: $",
            round(
                token[
                    "total_volume_5m"
                ],
                2
            )
        )

        print(
            "5m Price Change:",
            round(
                token[
                    "price_change_5m"
                ],
                2
            ),
            "%"
        )

        print(
            "5m Volume Change:",
            round(
                token[
                    "volume_change_5m"
                ],
                2
            ),
            "%"
        )


        # =================================
        # 15M
        # =================================

        print()
        print("15M DATA")

        print(
            "15m Buy Pressure:",
            round(
                token[
                    "buy_pressure_15m"
                ],
                1
            ),
            "%"
        )

        print(
            "15m Transaction Buy Ratio:",
            round(
                token[
                    "transaction_buy_ratio_15m"
                ],
                1
            ),
            "%"
        )

        print(
            "15m Price Change:",
            round(
                token[
                    "price_change_15m"
                ],
                2
            ),
            "%"
        )


        # =================================
        # RECENT TRADES
        # =================================

        print()
        print("RECENT 10 TRADES")

        print(
            "Recent Buys:",
            token["recent_buy_count"]
        )

        print(
            "Recent Sells:",
            token["recent_sell_count"]
        )

        print(
            "Recent Buy USD: $",
            round(
                token[
                    "recent_buy_usd"
                ],
                2
            )
        )

        print(
            "Recent Sell USD: $",
            round(
                token[
                    "recent_sell_usd"
                ],
                2
            )
        )

        print(
            "Recent USD Buy Pressure:",
            round(
                token[
                    "recent_buy_pressure"
                ],
                1
            ),
            "%"
        )

        print(
            "Recent Net Flow: $",
            round(
                token[
                    "recent_net_flow"
                ],
                2
            )
        )

        print(
            "Recent Trade Confirmation:",
            token[
                "recent_trade_pass"
            ]
        )


        # =================================
        # MOMENTUM HISTORY
        # =================================

        print()
        print("MOMENTUM HISTORY")

        print(
            "Trend:",
            token[
                "momentum_trend"
            ]
        )

        print(
            "Momentum Score:",
            token[
                "momentum_score"
            ]
        )

        print(
            "5m Buy Pressure Change:",
            round(
                token[
                    "buy_pressure_delta"
                ],
                1
            ),
            "points"
        )

        print(
            "Transaction Ratio Change:",
            round(
                token[
                    "transaction_ratio_delta"
                ],
                1
            ),
            "points"
        )

        print(
            "5m Volume Change vs Last Run:",
            round(
                token[
                    "history_volume_change"
                ],
                1
            ),
            "%"
        )

        print(
            "15m Buy Pressure Change:",
            round(
                token[
                    "buy_pressure_15m_delta"
                ],
                1
            ),
            "points"
        )

        print(
            "Price Momentum Change:",
            round(
                token[
                    "price_change_delta"
                ],
                2
            ),
            "points"
        )


        # =================================
        # MARKET
        # =================================

        print()
        print("MARKET DATA")

        print(
            "Liquidity: $",
            round(
                token[
                    "liquidity"
                ],
                2
            )
        )

        print(
            "Liquidity / 5m Volume:",
            round(
                token[
                    "liquidity_volume_ratio"
                ],
                2
            )
        )

        print(
            "Holders:",
            int(
                token["holders"]
            )
        )


        # =================================
        # SCORING
        # =================================

        print()
        print("SCORING")

        print(
            "Base Score:",
            token["base_score"]
        )

        print(
            "Volume Score:",
            token["volume_score"]
        )

        print(
            "15m Confirmation Score:",
            token[
                "confirmation_score"
            ]
        )

        print(
            "Transaction Score:",
            token[
                "transaction_score"
            ]
        )

        print(
            "Final Score:",
            token["final_score"]
        )

        print(
            "Signal:",
            token["signal"]
        )