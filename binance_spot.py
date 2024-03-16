from binance.client import Client
import binance_f
import time
import requests
import pandas as pd
import json
from pathlib import Path
from dhooks import Webhook
import decimal
import cli_inputs
from threading import Thread


def get_credentials():
    root = Path(".")
    file_path = f"{root}/credentials.json"

    with open(file_path) as file:

        file = file.read()
        credentials = json.loads(file)

        api_key = credentials["binance_api_key"]
        api_secret = credentials["binance_api_secret"]

    return api_key, api_secret


def auth():
    api_key, api_secret = get_credentials()
    binance_client = Client(testnet=False, api_key=api_key, api_secret=api_secret)

    return binance_client


def get_spot_balances(client, display:bool):

    balances = client.get_account()["balances"]
    products = client.get_all_tickers()

    spot_positions = {}
    coin_prices = {}
    for row in products:
        ticker = row["symbol"].replace("USDT", "")
        price = float(row["price"])   # usd

        coin_prices[ticker] = price

    for balance in balances:
        coin = balance["asset"]
        coin_balance = float(balance["free"])

        if coin_balance > 0:
            if coin in coin_prices.keys() or coin in ["USDT", "USDC", "BUSD"]:

                if coin in ["USDT", "USDC", "BUSD"]:
                    usd_value = coin_balance
                else:
                    price = coin_prices[coin]
                    usd_value = round(coin_balance * price, 2)

                if usd_value > 3:
                    spot_positions[coin] = {"coin_amount": coin_balance, "usd_value": usd_value}

    if display:
        print("Current positions:")
        positions_df = pd.DataFrame.from_dict(spot_positions, orient="index")
        print(positions_df.to_markdown())

    return spot_positions


def get_spot_tickers(client):
    products = client.get_all_tickers()

    tickers = {}
    for row in products:
        symbol = row["symbol"]
        ticker = row["symbol"]
        if "USDT" in symbol:

            symbol = symbol.replace("USDT", "")

            tickers[symbol] = ticker

    return tickers


def get_last_price(ticker):

    endpoint = "https://api.binance.com/api/v3/ticker/price"

    resp = requests.get(endpoint, params={"symbol":ticker}).json()
    last_price = float(resp["price"])

    return last_price


def get_instrument_info(client, ticker):
    instrument_info = client.get_symbol_info(ticker)

    min_notional = None
    decimals = None
    min_qty = None
    max_qty = None
    max_notional = None
    tick_decimals = None
    for row in instrument_info["filters"]:
        if row["filterType"] == "NOTIONAL":
            min_notional = float(row["minNotional"])
            max_notional = float(row["maxNotional"])
        elif row["filterType"] == "LOT_SIZE":

            min_qty = float(row["minQty"])
            max_qty = float(row["maxQty"])

            min_qty_ = decimal.Decimal(row["minQty"]).normalize()
            decimals = abs(min_qty_.as_tuple().exponent)
        elif row["filterType"] == "PRICE_FILTER":
            tick_size = decimal.Decimal(row["tickSize"]).normalize()
            tick_decimals = abs(tick_size.as_tuple().exponent)

    return min_notional, max_notional, decimals, tick_decimals ,min_qty, max_qty


# orders
def market_order(client, usd_size, coin_sell_amount, ticker, side):
    """
    this order will split ur size into 20 equal orders and rapid execute them in 0.25s time intervals

    :param client: bybit client
    :param usd_size: size in usd
    :param ticker: choose ticker
    :param side:  b > buy, s > sell
    :return:
    """

    min_notional, max_notional, decimals, tick_decimals ,min_qty, max_qty = get_instrument_info(client, ticker)
    balances = get_spot_balances(client, display=False)

    orders = []

    if side == "b":
        if "USDT" in balances:
            usdt_balance = balances["USDT"]["coin_amount"]
        else:
            usdt_balance = 0
        if usd_size <= usdt_balance:
            last_price = get_last_price(ticker)
            single_order = int(usd_size / 20)
            single_order = round(single_order / last_price, decimals)

            if single_order > min_qty:
                if single_order < max_qty:
                    for i in range(20):
                        orders.append(single_order)
                else:
                    print(f"single order to big to execute market order || order size: {single_order} || max order size: {max_qty} coins")
            else:
                print(f"total market order size to low >> min qty is: {min_qty} coins")
        else:
            print(f"Not enough USDT to execute market buy order >> available USDT: {usdt_balance} || wanted buy size: {usd_size}")
    elif side == "s":
        # min order size is in coins
        if ticker[:-4] in balances:
            coin_balance = balances[ticker[:-4]]["coin_amount"]
        else:
            coin_balance = 0
        coins_to_sell = coin_sell_amount
        if coin_balance >= coin_sell_amount:
            single_order = round(coins_to_sell / 20, decimals)
            if single_order > min_qty:
                if single_order < max_qty:
                    for i in range(20):
                        orders.append(single_order)
                else:
                    print(f"single order to big to market order || order size: {single_order} coins|| max order size: {max_qty} coins ")
            else:
                print(f"total market order size to low >> min qty is: {min_qty} coins")
        else:
            print(f"Not enough coins to execute market sell order >> available coins: {coin_balance} || coin wanted to be sold: {coins_to_sell}")
    else:
        print(f"Error with side input || input: {side} || should be: b/s")

    time_delay = 0.25  # seconds
    if orders and side in ["b", "s"]:
        for order in orders:

            if side == "b":
                ord_ = client.order_market_buy(symbol=ticker, quantity=order)
            elif side == "s":
                ord_ = client.order_market_sell(symbol=ticker, quantity=order)
            time.sleep(time_delay)


def linear_twap(client, usd_size, coin_sell_amount ,ticker, side, duration, order_amount):
    """
    fuction that split order into equal sized orders and executes them over specified duration with equal time delays
    :param client: bybit client
    :param usd_size: size in usd
    :param ticker: choose ticker
    :param side: b > buy, s > sell
    :param duration: in seconds
    :param order_amount: amount of orders [default: 100 orders, int: specific number of orders)
    :return:
    """

    min_notional, max_notional, decimals, tick_decimals ,min_qty, max_qty = get_instrument_info(client, ticker)
    balances = get_spot_balances(client, display=False)

    # check if size doesn't excedes available usdt qty
    # if based on order amount size becomes lower than min qty fix it to min qty
    orders = []
    if side == "b":
        if "USDT" in balances:
            usdt_balance = balances["USDT"]["coin_amount"]
        else:
            usdt_balance = 0
        if usd_size < usdt_balance:
            # min order size is in usd
            if order_amount == "default":
                single_order = int(usd_size / 100)
                last_price = get_last_price(ticker)
                single_order = round(single_order / last_price, decimals)

                if single_order > min_qty:
                    if single_order < max_qty:
                        for i in range(100):
                            orders.append(single_order)
                    else:
                        print(f"single order to big to execute twap || order size: {single_order} || max order size: {max_qty} ")
                else:
                    print(f"total twap size to low: {usd_size}")
            else:
                orders = []

                single_order = int(usd_size / order_amount)
                last_price = get_last_price(ticker)
                single_order = round(single_order / last_price, decimals)

                if single_order > min_qty:
                    if single_order < max_qty:
                        for i in range(order_amount):
                            orders.append(single_order)
                    else:
                        print(f"single order to big to execute twap || order size: {single_order} || max order size: {max_qty} ")
                else:
                    print(f"single order size to low to execute twap || order size: {int(usd_size / order_amount)} || min order size: {min_qty}")
        else:
            print(f"not enough usdt to execute twap || available funds: {usdt_balance} $ || twap size: {usd_size} $")

    elif side == "s":
        # min order size is in coins
        if ticker[:-4] in balances:
            coin_balance = balances[ticker[:-4]]["coin_amount"]
        else:
            coin_balance = 0

        coins_to_sell = coin_sell_amount
        if coin_balance >= coin_sell_amount:
            if order_amount == "auto":
                single_order = round(coins_to_sell / 100, decimals)
                if single_order > min_qty:
                    if single_order < max_qty:
                        for i in range(100):
                            orders.append(single_order)
                    else:
                        print(f"single order to big to execute twap || order size: {single_order} coins|| max order size: {max_qty} coins ")
                else:
                    print(f"total twap size to low: {usd_size} >> should be atleast 100$")
            else:
                orders = []
                single_order = round(coins_to_sell / order_amount, decimals)

                if single_order > min_qty:
                    if single_order < max_qty:
                        for i in range(order_amount):
                            orders.append(single_order)
                    else:
                        print(f"single order to big to execute twap || order size: {single_order} coins || max order size: {max_qty} coins")
                else:
                    print(f"single order size to low to execute twap || order size: {single_order} coins || min order size: {min_qty} coins")
        else:
            print(f"not enough coins to execute Sell twap || available funds: {coin_balance} coins || twap size: {coin_sell_amount} coins")

    else:
        print(f"Error with side input || input: {side} || should be: b/s")

    time_delay = duration / order_amount

    if orders and side in ["b", "s"]:
        for order in orders:
            start = time.time()
            if side == "b":
                ord_ = client.order_market_buy(symbol=ticker, quantity=order)
            elif side == "s":
                ord_ = client.order_market_sell(symbol=ticker, quantity=order)

            loop_time = time.time() - start
            delay = time_delay - loop_time
            if delay > 0:
                time.sleep(time_delay)


def limit_tranche(client, usd_size, ticker, side, upper_price, lower_price, order_amount):
    """

    :param client: bybit client
    :param usd_size: total size
    :param ticker: ticker
    :param side: b > buy, s > sell
    :param upper_price:  upper bound for limit orders
    :param lower_price:  lower bound for limit orders
    :return:
    """

    if order_amount == "default":
        order_amount = 15

    min_notional, max_notional, decimals, tick_decimals ,min_qty, max_qty = get_instrument_info(client, ticker)
    balances = get_spot_balances(client, display=False)

    orders = []

    # Calculate the spacing between orders
    spacing = (upper_price - lower_price) / (order_amount)

    last_price = get_last_price(ticker)
    error = True
    if upper_price > lower_price:
        if side == "b":
            if last_price > upper_price:
                error = False
            else:
                print("on buy side last price should be higher than upper price limit")
        elif side == "s":
            if last_price < lower_price:
                error = False
            else:
                print("on sell side last price should be lower than lower price limit")
        else:
            print(f"Error with side input || input: {side} || should be: b/s")
    else:
        print("upper price limit should be higher than lower price limit")

    if not error:
        if side == "b":
            if "USDT" in balances:
                usdt_balance = balances["USDT"]["coin_amount"]
            else:
                usdt_balance = 0
            if usd_size < usdt_balance:
                single_order = int(usd_size / order_amount)
                last_price = get_last_price(ticker)
                single_order = round(single_order / last_price, decimals)

                price = lower_price
                for i in range(order_amount):
                    orders.append([single_order, round(price, tick_decimals)])
                    price += spacing

            else:
                print(f"Not enought usdt to execute the limit tranche order || usdt available: {usdt_balance} $")

        if side == "s":
            if ticker[:-4] in balances:
                coin_balance = balances[ticker[:-4]]["coin_amount"]
            else:
                coin_balance = 0

            coins_to_sell = round(usd_size / ((upper_price + lower_price) / 2), decimals)
            single_order = round(coins_to_sell / order_amount, decimals)
            if coins_to_sell < coin_balance:
                price = lower_price
                for i in range(order_amount):
                    orders.append([single_order, round(price, tick_decimals)])
                    price += spacing
            else:
                print(f"not enough coins available to create limit tranche order || coin balance: {coin_balance}")

        if orders and side in ["b", "s"]:
            for order in orders:
                if side == "b":
                    ord_ = client.order_limit_buy(symbol=ticker, quantity=order[0], price=str(order[1]))
                elif side == "s":
                    ord_ = client.order_limit_sell(symbol=ticker, quantity=order[0], price=str(order[1]))
                time.sleep(0.01)


def set_market_order_usd(client):
    """
    Basic market order executes in 20 swarm orders

    :param client:
    :return:
    """

    tickers = get_spot_tickers(client=client)
    ticker = cli_inputs.select_ticker(tickers=tickers)
    usd_size = cli_inputs.select_usdt_size()
    side = cli_inputs.select_side()

    if side == "s":
        last_price = get_last_price(ticker)
        coin_sell_amount = usd_size / last_price
    elif side == "b":
        coin_sell_amount = 0

    market_order_thread = Thread(target=market_order, args=(client, usd_size, coin_sell_amount, ticker, side), name=f"SPOT_{ticker}_{side}_{usd_size}").start()


def set_market_order_pct(client):
    """
    Basic market order executes in 20 swarm orders

    :param client:
    :return:
    """
    balances = get_spot_balances(client, display=False)
    tickers = get_spot_tickers(client=client)
    ticker = cli_inputs.select_ticker(tickers=tickers)
    side = cli_inputs.select_side()

    if side == "s":
        if ticker[:-4] in balances:
            coin_balance = balances[ticker[:-4]]["coin_amount"]
        else:
            coin_balance = 0

        acc_pct = cli_inputs.select_pct()
        if acc_pct == 1:
            acc_pct = 0.995

        coin_sell_amount = coin_balance * acc_pct
        usd_size = 0
    else:
        if "USDT" in balances:
            usdt_balance = balances["USDT"]["coin_amount"]
        else:
            usdt_balance = 0
        acc_pct = cli_inputs.select_pct()
        if acc_pct == 1:
            acc_pct = 0.995
        usd_size = round(usdt_balance * acc_pct)
        coin_sell_amount = 0

    market_order_thread = Thread(target=market_order, args=(client, usd_size, coin_sell_amount ,ticker, side), name=f"SPOT_{ticker}_{side}_{usd_size}").start()


def set_linear_twap_usd(client):
    """
    Basic linear twap setup

    :param client:
    :return:
    """
    tickers = get_spot_tickers(client=client)
    ticker = cli_inputs.select_ticker(tickers=tickers)
    usd_size = cli_inputs.select_usdt_size()
    side = cli_inputs.select_side()

    duration = cli_inputs.select_duration()
    order_amount = cli_inputs.select_order_amount()

    if side == "s":
        last_price = get_last_price(ticker)
        coin_sell_amount = usd_size / last_price
    elif side == "b":
        coin_sell_amount = 0

    twap_thread = Thread(target=linear_twap, args=(client, usd_size, coin_sell_amount, ticker, side, duration, order_amount), name=f"SPOT_{ticker}_{side}_{usd_size}_twap{round(duration / 60, 1)}min").start()


def set_linear_twap_pct(client):
    """
    Basic linear twap setup

    :param client:
    :return:
    """
    balances = get_spot_balances(client, display=False)

    tickers = get_spot_tickers(client=client)
    ticker = cli_inputs.select_ticker(tickers=tickers)
    side = cli_inputs.select_side()

    if side == "s":
        if ticker[:-4] in balances:
            coin_balance = balances[ticker[:-4]]["coin_amount"]
        else:
            coin_balance = 0
        acc_pct = cli_inputs.select_pct()
        if acc_pct == 1:
            acc_pct = 0.995
        coin_sell_amount = coin_balance * acc_pct
        usd_size = 0
    elif side == "b":
        if "USDT" in balances:
            usdt_balance = balances["USDT"]["coin_amount"]
        else:
            usdt_balance = 0
        acc_pct = cli_inputs.select_pct()
        if acc_pct == 1:
            acc_pct = 0.995
        usd_size = round(usdt_balance * acc_pct)
        coin_sell_amount = 0

    duration = cli_inputs.select_duration()
    order_amount = cli_inputs.select_order_amount()

    twap_thread = Thread(target=linear_twap, args=(client, usd_size, coin_sell_amount, ticker, side, duration, order_amount), name=f"BYBIT_SPOT_{ticker}_{side}_{usd_size}_twap{round(duration / 60, 1)}min").start()


def set_limit_orders_usd(client):
    """
    Functions that sets basic limit orders

    :return:
    """
    tickers = get_spot_tickers(client=client)
    ticker = cli_inputs.select_ticker(tickers=tickers)
    usd_size = cli_inputs.select_usdt_size()
    side = cli_inputs.select_side()
    upper_price = cli_inputs.select_upper_limit_price()
    lower_price = cli_inputs.select_lower_limit_price()
    order_amount = cli_inputs.select_order_amount()


    limit_thread = Thread(target=limit_tranche, args=(client, usd_size, ticker, side, upper_price, lower_price, order_amount), name=f"SPOT_{ticker}_{side}_{usd_size}limit_tranche").start()


def set_limit_orders_pct(client):
    """
       Functions that sets basic limit orders

       :return:
       """
    balances = get_spot_balances(client, display=False)

    tickers = get_spot_tickers(client=client)
    ticker = cli_inputs.select_ticker(tickers=tickers)
    side = cli_inputs.select_side()
    upper_price = cli_inputs.select_upper_limit_price()
    lower_price = cli_inputs.select_lower_limit_price()
    avg_prc = (upper_price + lower_price) / 2
    if side == "s":
        if ticker[:-4] in balances:
            coin_balance = balances[ticker[:-4]]["coin_amount"]
        else:
            coin_balance = 0
        acc_pct = cli_inputs.select_pct()
        if acc_pct == 1:
            acc_pct = 0.995
        usd_size = round((coin_balance * avg_prc * 0.999) * acc_pct)
    else:
        if "USDT" in balances:
            usdt_balance = balances["USDT"]["coin_amount"]
        else:
            usdt_balance = 0
        acc_pct = cli_inputs.select_pct()
        if acc_pct == 1:
            acc_pct = 0.995
        usd_size = round(usdt_balance * acc_pct)

    order_amount = cli_inputs.select_order_amount()

    limit_thread = Thread(target=limit_tranche, args=(client, usd_size, ticker, side, upper_price, lower_price, order_amount), name=f"SPOT_{ticker}_{side}_{usd_size}limit_tranche").start()



# client = auth()
# balances = get_spot_balances(client, display=True)
# tickers = get_spot_tickers(client)
# prc = get_last_price("AIUSDT")
# min_notional, max_notional, decimals, tick_decimals ,min_qty, max_qty = get_instrument_info(client, "AIUSDT")
# print(min_notional, decimals , min_qty)

# set_market_order_usd(client)
# set_market_order_pct(client)

# set_linear_twap_usd(client)
# set_linear_twap_pct(client)

# set_limit_orders_usd(client)
# set_limit_orders_pct(client)