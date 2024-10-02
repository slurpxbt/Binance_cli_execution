from binance.um_futures import UMFutures
import time
import requests
import pandas as pd
import json
from pathlib import Path
from dhooks import Webhook
import decimal
import cli_inputs
from threading import Thread
import math


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
    binance_usdt_m_client = UMFutures(key=api_key, secret=api_secret)

    return binance_usdt_m_client


def get_collateral_info(client, display:bool):
    tickers = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "BNB": "BNBUSDT"}
    collateral_values = {"BTC": 0.95, "BNB": 0.95, "ETH": 0.95}

    balances = client.balance()
    usdt_m_balances = {}
    for asset in balances:

        if asset["asset"] in tickers.keys():
            ticker = tickers[asset["asset"]]
            price = client.ticker_price(symbol=ticker)

            usd_value = round(float(asset["balance"]) * float(price["price"]), 1)
            collateral_value = usd_value * collateral_values[asset["asset"]]

            if usd_value > 10:
                usdt_m_balances[asset["asset"]] = {"coin_balance": float(asset["balance"]), "usd_value": usd_value, "collateral_usd_value": collateral_value}

        else:
            if float(asset["balance"]) > 10:
                usdt_m_balances[asset["asset"]] = {"coin_balance": float(asset["balance"]), "usd_value": round(float(asset["balance"]), 1), "collateral_usd_value": round(float(asset["balance"]), 1)}

    collaterall_df = pd.DataFrame.from_dict(usdt_m_balances, orient="index")
    total_colaterall_value = collaterall_df["collateral_usd_value"].sum()
    total_usd_value = collaterall_df["usd_value"].sum()

    totals = {}
    totals["totals"] = {"total_usd_value": total_usd_value, "total_collateral_value": total_colaterall_value}
    totals_df = pd.DataFrame.from_dict(totals, orient="index")

    if display:
        print("*" * 70)
        print(collaterall_df.to_markdown())
        print("*" * 70)
        print(totals_df.to_markdown())
        print("*" * 70)

    return usdt_m_balances, totals


def get_usdt_m_tickers(client):
    ticker_data = client.ticker_24hr_price_change()

    tickers = {}
    for row in ticker_data:
        symbol = row["symbol"]
        ticker = row["symbol"]
        if "USDT" in symbol:

            symbol = symbol.replace("USDT", "")

            if "10000" in symbol:
                symbol = symbol.replace("10000", "")
            elif "1000" in symbol:
                symbol = symbol.replace("1000", "")

            if "_" not in symbol:
                tickers[symbol] = ticker

    return tickers


def get_instrument_info(client, ticker):
    symbol_info = client.exchange_info()["symbols"]

    instrument_info = False
    for i in symbol_info:
        if i["symbol"] == ticker:

            instrument_info = i
            break

    min_notional = None
    min_qty = None
    max_qty = None
    decimals = None
    tick_decimals = None

    if instrument_info:
        # print(instrument_info)
        price_precision = instrument_info["pricePrecision"]
        quantity_precision = instrument_info["quantityPrecision"]
        decimals = quantity_precision

        filters = instrument_info["filters"]

        tick_size = decimal.Decimal(filters[0]["tickSize"]).normalize()
        tick_decimals = abs(tick_size.as_tuple().exponent)

        min_qty = float(filters[1]["minQty"])
        max_qty = float(filters[1]["maxQty"])
        min_notional = float(filters[5]["notional"])

        # print(price_precision)
        # print(quantity_precision)
        # print(decimals)
        # print(tick_size)
        # print(tick_decimals)
        # print(min_qty)
        # print(max_qty)
        # print(min_notional)

    return min_notional, min_qty, max_qty, decimals, tick_decimals


def get_last_price(client, ticker):
    price_data = client.ticker_price(symbol=ticker)

    last_price = float(price_data["price"])
    return last_price


def get_leverage_data(client):
    lev_notional_data = client.leverage_brackets()
    lev_and_notional_info = {}

    for coin in lev_notional_data:
        lev_and_notional_info[coin["symbol"]] = coin["brackets"]

    return lev_and_notional_info


# ORDER/POSITION OVERVIEW FUNCTIONS
def get_open_positions(client, display:bool):
    account_info = client.account()["positions"]

    open_positions = {}
    counter = 0
    for coin in account_info:
        if float(coin["positionAmt"]) != 0:
            ticker = coin["symbol"]
            tp_id, tp_price, sl_id, sl_price = get_active_stop_orders(client, ticker)

            coin_size = float(coin["positionAmt"])
            if coin_size > 0:
                side = "Buy"
            elif coin_size < 0:
                side = "Sell"

            upnl = round(float(coin["unrealizedProfit"]), 1)
            usd_size = float(coin["notional"])
            entry_price = float(coin["entryPrice"])

            open_positions[counter] = {"ticker": ticker, "side":side, "coin_size": abs(coin_size), "usd_size": abs(usd_size), "entry_price":entry_price, "uPnl[$]":upnl ,"SL_price": sl_price, "TP_price": tp_price}
            counter += 1

    if open_positions:
        if display:
            print("\n")
            print("Current positions:")
            positions_df = pd.DataFrame.from_dict(open_positions, orient="index")
            positions_df = positions_df[["ticker", "side", "coin_size", "usd_size", "entry_price", "uPnl[$]", "SL_price", "TP_price"]]
            print(positions_df.to_markdown())
            print("\n")

        return open_positions
    else:
        if display:
            print("\n")
            print("No open positions")
        return open_positions


def get_active_stop_orders(client, ticker):

    orders = client.get_orders(symbol=ticker)

    sl_id = None
    sl_price = None

    tp_id = None
    tp_price = None
    if len(orders) == 2:
        for order in orders:
            if order["type"] == "STOP_MARKET":
                sl_id = order["orderId"]
                sl_price = float(order["stopPrice"])
            elif order["type"] == "TAKE_PROFIT_MARKET":
                tp_id = order["orderId"]
                tp_price = float(order["stopPrice"])

    return tp_id, tp_price, sl_id, sl_price


def set_position_sl_tp(client):

    positions = get_open_positions(client=client, display=True)
    try:
        modify_id = int(input("select ID of the position you wish to modify >>> "))
    except:
        modify_id = None
        print("Error: ID must be number")

    modify_type = None
    if modify_id in positions.keys():
        try:
            print("What do you want to modify: 1=tp/sl, 2=tp, 3=sl")
            modify_type = int(input("Input the modification type you want[1, 2, 3] >>>"))
        except:
            modify_type = None
            print("Error: Modification type must me number")
    else:
        print("ID not found in positions")

    if modify_type is not None and modify_id is not None:
        if modify_id in positions.keys():
            position = positions[modify_id]
            ticker = position["ticker"]
            position_side = position["side"]

            tp_id, tp_price, sl_id, sl_price = get_active_stop_orders(client, ticker)

            last_price = get_last_price(client, ticker)
            print(f"{ticker} selected to modify")

            if position_side == "Buy":
                if modify_type == 1:
                    try:
                        new_tp_price = float(input("new TP price >>>  "))
                        if new_tp_price < last_price and new_tp_price != 0:
                            print("TP price below last price, TP won't be set/changed")
                            new_tp_price = None
                        else:
                            new_tp_price = str(new_tp_price)
                            takeProfit = new_tp_price

                            if tp_id is not None:
                                client.cancel_order(symbol=ticker, orderId=tp_id)
                            client.new_order(symbol=ticker, side="SELL", type="TAKE_PROFIT_MARKET", stopPrice=takeProfit, closePosition=True, timeInForce="GTE_GTC")
                            print(f"{ticker} TP modified >>> new TP: {takeProfit}")

                    except:
                        print("TP price should be number")

                    try:
                        new_sl_price = float(input("new SL price >>>  "))

                        if new_sl_price > last_price:
                            print("SL price above last price, SL won't be set/changed")
                            new_sl_price = None
                        else:
                            new_sl_price = str(new_sl_price)
                            stopLoss = new_sl_price

                            if sl_id is not None:
                                client.cancel_order(symbol=ticker, orderId=sl_id)
                            client.new_order(symbol=ticker, side="SELL", type="STOP_MARKET", stopPrice=stopLoss, closePosition=True, timeInForce="GTE_GTC")
                            print(f"{ticker} SL modified >>> new SL: {stopLoss}")

                    except:
                        print("SL price should be number")

                elif modify_type == 2:
                    try:
                        new_tp_price = float(input("new TP price >>>  "))
                        if new_tp_price < last_price and new_tp_price != 0:
                            print("TP price below last price, TP won't be set/changed")
                            new_tp_price = None
                        else:
                            new_tp_price = str(new_tp_price)
                            takeProfit = new_tp_price

                            if tp_id is not None:
                                client.cancel_order(symbol=ticker, orderId=tp_id)
                            client.new_order(symbol=ticker, side="SELL", type="TAKE_PROFIT_MARKET", stopPrice=takeProfit, closePosition=True, timeInForce="GTE_GTC")
                            print(f"{ticker} TP modified >>> new TP: {takeProfit}")
                    except:
                        print("TP price should be number")

                elif modify_type == 3:
                    try:
                        new_sl_price = float(input("new SL price >>>  "))

                        if new_sl_price > last_price:
                            print("SL price above last price, SL won't be set/changed")
                            new_sl_price = None
                        else:
                            new_sl_price = str(new_sl_price)
                            stopLoss = new_sl_price

                            if sl_id is not None:
                                client.cancel_order(symbol=ticker, orderId=sl_id)
                            client.new_order(symbol=ticker, side="SELL", type="STOP_MARKET", stopPrice=stopLoss, closePosition=True, timeInForce="GTE_GTC")
                            print(f"{ticker} SL modified >>> new SL: {stopLoss}")
                    except:
                        print("SL price should be number")

            elif position_side == "Sell":
                if modify_type == 1:
                    try:
                        new_tp_price = float(input("new TP price >>>  "))
                        if new_tp_price > last_price:
                            print("TP price above last price, TP won't be set/changed")
                            new_tp_price = None
                        else:
                            new_tp_price = str(new_tp_price)
                            takeProfit = new_tp_price

                            if tp_id is not None:
                                client.cancel_order(symbol=ticker, orderId=tp_id)
                            client.new_order(symbol=ticker, side="BUY", type="TAKE_PROFIT_MARKET", stopPrice=takeProfit, closePosition=True, timeInForce="GTE_GTC")
                            print(f"{ticker} TP modified >>> new TP: {takeProfit}")
                    except:
                        print("TP price should be number")

                    try:
                        new_sl_price = float(input("new SL price >>>  "))

                        if new_sl_price < last_price and new_sl_price != 0:
                            print("SL price below last price, SL won't be set/changed")
                            new_sl_price = None
                        else:
                            new_sl_price = str(new_sl_price)
                            stopLoss = new_sl_price

                            if sl_id is not None:
                                client.cancel_order(symbol=ticker, orderId=sl_id)
                            client.new_order(symbol=ticker, side="BUY", type="STOP_MARKET", stopPrice=stopLoss, closePosition=True, timeInForce="GTE_GTC")
                            print(f"{ticker} SL modified >>> new SL: {stopLoss}")
                    except:
                        print("SL price should be number")

                elif modify_type == 2:
                    try:
                        new_tp_price = float(input("new TP price >>>  "))
                        if new_tp_price > last_price:
                            print("TP price above last price, TP won't be set/changed")
                            new_tp_price = None
                        else:
                            new_tp_price = str(new_tp_price)
                            takeProfit = new_tp_price

                            if tp_id is not None:
                                client.cancel_order(symbol=ticker, orderId=tp_id)
                            client.new_order(symbol=ticker, side="BUY", type="TAKE_PROFIT_MARKET", stopPrice=takeProfit, closePosition=True, timeInForce="GTE_GTC")
                            print(f"{ticker} TP modified >>> new TP: {takeProfit}")

                    except:
                        print("TP price should be number")

                elif modify_type == 3:
                    try:
                        new_sl_price = float(input("new SL price >>>  "))

                        if new_sl_price < last_price and new_sl_price != 0:
                            print("SL price below last price, SL won't be set/changed")
                            new_sl_price = None
                        else:
                            new_sl_price = str(new_sl_price)
                            stopLoss = new_sl_price

                            if sl_id is not None:
                                client.cancel_order(symbol=ticker, orderId=sl_id)
                            client.new_order(symbol=ticker, side="BUY", type="STOP_MARKET", stopPrice=stopLoss, closePosition=True, timeInForce="GTE_GTC")
                            print(f"{ticker} SL modified >>> new SL: {stopLoss}")
                    except:
                        print("SL price should be number")


def clear_stop_orders(client, ticker):
    tp_id, tp_price, sl_id, sl_price = get_active_stop_orders(client, ticker)
    if tp_id is not None:
        client.cancel_order(symbol=ticker, orderId=tp_id)

    if sl_id is not None:
        client.cancel_order(symbol=ticker, orderId=sl_id)

# market orders

def market_order_open(client, usd_size, ticker, side):
    """
    this order will split ur size into 20 equal orders and rapid execute them in 0.25s time intervals

    :param client: bybit client
    :param usd_size: size in usd
    :param ticker: choose ticker
    :param side:  b > buy, s > sell
    :return:
    """

    min_notional, min_qty, max_qty, decimals, tick_decimals = get_instrument_info(client, ticker)

    orders = []
    error = True
    if side == "b":
        side = "BUY"
        error = False
    elif side == "s":
        side = "SELL"
        error = False
    else:
        print(f"Error with side input || input: {side} || should be: b/s")

    if not error:
        last_price = get_last_price(client, ticker)
        total_coins = round(usd_size / last_price, decimals)

        single_order = round(total_coins / 20, decimals)

        if usd_size > 3000:
            if single_order >= min_qty:
                if single_order < max_qty:
                    for i in range(20):
                        orders.append(single_order)
                else:
                    print(f"single order to big to execute market order || order size: {single_order} || max order size: {max_qty} coins")
            else:
                if total_coins > min_qty:
                    orders = [total_coins]
                else:
                    print(f"total market order size to low >> min qty is: {min_qty} coins")
        else:
            if total_coins >= min_qty:
                orders = [total_coins]
            else:
                print(f"total market order size to low >> min qty is: {min_qty} coins")

        time_delay = 0.25
        for order in orders:
            client.new_order(symbol=ticker, side=side, type="MARKET", quantity=order, reduceOnly=False)
            time.sleep(time_delay)


def market_order_close(client, coin_size, ticker, side, pct):
    """
    this order will split ur size into 20 equal orders and rapid execute them in 0.25s time intervals

    :param client: bybit client
    :param usd_size: size in usd
    :param ticker: choose ticker
    :param side:  b > buy, s > sell
    :return:
    """

    min_notional, min_qty, max_qty, decimals, tick_decimals = get_instrument_info(client, ticker)

    orders = []
    error = True
    if side == "b":
        side = "BUY"
        error = False
    elif side == "s":
        side = "SELL"
        error = False
    else:
        print(f"Error with side input || input: {side} || should be: b/s")

    last_price = get_last_price(client, ticker)
    usd_size = coin_size * last_price

    if not error:
        single_order = round(coin_size / 20, decimals)

        if usd_size > 3000:
            if single_order >= min_qty:
                if single_order < max_qty:
                    for i in range(20):
                        orders.append(single_order)
                else:
                    print(f"single order to big to execute market order || order size: {single_order} || max order size: {max_qty} coins")
            else:
                if coin_size > min_qty:
                    orders = [coin_size]
                else:
                    print(f"total market order size to low >> min qty is: {min_qty} coins")
        else:
            if coin_size >= min_qty:
                orders = [coin_size]
            else:
                print(f"total market order size to low >> min qty is: {min_qty} coins")

        time_delay = 0.25
        for order in orders:
            client.new_order(symbol=ticker, side=side, type="MARKET", quantity=order, reduceOnly=True)
            time.sleep(time_delay)

        if pct == 1:
            clear_stop_orders(client, ticker)


def linear_twap_open(client, ticker, side, usd_size, duration, order_amount):
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

    min_notional, min_qty, max_qty, decimals, tick_decimals = get_instrument_info(client, ticker)

    orders = []
    error = True
    if side == "b":
        side = "BUY"
        error = False
    elif side == "s":
        side = "SELL"
        error = False
    else:
        print(f"Error with side input || input: {side} || should be: b/s")

    if not error:
        last_price = get_last_price(client, ticker)
        total_coins = round(usd_size / last_price, decimals)

        if order_amount == "default":
            single_order = round(total_coins / 100)
            for i in range(100):
                orders.append(single_order)
        else:
            single_order = round(total_coins / order_amount, decimals)
            for i in range(order_amount):
                orders.append(single_order)

        time_delay = duration / order_amount  # seconds

        for order in orders:
            loop_start = time.time()
            if order > min_qty:
                if order < max_qty:
                    client.new_order(symbol=ticker, side=side, type="MARKET", quantity=order, reduceOnly=False)
                else:
                    print(f"order to big tp execute || order: {order} || max order: {max_qty}")
                    break
            else:
                print(f"order to low to be able to execute || order: {order} || min order: {min_qty}")
                break

            loop_end = time.time()
            if loop_end - loop_start > time_delay:
                pass
            else:
                interval = time_delay - (loop_end - loop_start)
                time.sleep(interval)


def linear_twap_close(client, ticker, side, coin_size, duration, order_amount, pct):
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

    min_notional, min_qty, max_qty, decimals, tick_decimals = get_instrument_info(client, ticker)

    orders = []
    error = True
    if side == "b":
        side = "BUY"
        error = False
    elif side == "s":
        side = "SELL"
        error = False
    else:
        print(f"Error with side input || input: {side} || should be: b/s")

    if not error:
        total_coins = coin_size

        if order_amount == "default":
            single_order = round(total_coins / 100)
            for i in range(100):
                orders.append(single_order)
        else:
            single_order = round(total_coins / order_amount, decimals)
            for i in range(order_amount):
                orders.append(single_order)

        time_delay = duration / order_amount  # seconds

        for order in orders:
            loop_start = time.time()
            if order > min_qty:
                if order < max_qty:
                    client.new_order(symbol=ticker, side=side, type="MARKET", quantity=order, reduceOnly=True)
                else:
                    print(f"order to big tp execute || order: {order} || max order: {max_qty}")
                    break
            else:
                print(f"order to low to be able to execute || order: {order} || min order: {min_qty}")
                break

            loop_end = time.time()
            if loop_end - loop_start > time_delay:
                pass
            else:
                interval = time_delay - (loop_end - loop_start)
                time.sleep(interval)

        if pct == 1:
            clear_stop_orders(client, ticker)

# limit oders
def limit_tranche_open(client, usd_size, ticker, side, upper_price, lower_price, order_amount, bid_ask:bool):

    min_notional, min_qty, max_qty, decimals, tick_decimals = get_instrument_info(client, ticker)
    orders = []

    spacing = (upper_price - lower_price) / (order_amount)
    last_price = get_last_price(client, ticker)
    if side == "b":
        side = "BUY"
    elif side == "s":
        side = "SELL"

    error = True
    if not bid_ask:
        if upper_price > lower_price:
            if side == "BUY":
                if last_price > upper_price:
                    error = False
                else:
                    print("on buy side last price should be higher than upper price limit")
            elif side == "SELL":
                if last_price < lower_price:
                    error = False
                else:
                    print("on sell side last price should be lower than lower price limit")
            else:
                print(f"Error with side input || input: {side} || should be: b/s")
        else:
            print("upper price limit should be higher than lower price limit")
    else:
        error = False

    if not error:
        last_price = get_last_price(client, ticker)
        total_coins = round(usd_size / last_price, decimals)

        single_order = round(total_coins / order_amount, decimals)

        price = lower_price
        for i in range(order_amount):
            orders.append([round(single_order, decimals), round(price, tick_decimals)])
            price += spacing

        for order in orders:
            client.new_order(symbol=ticker, side=side, type="LIMIT", quantity=order[0], price=order[1], timeInForce="GTC")
            time.sleep(0.01)


def limit_tranche_close(client, coin_size, ticker, side, upper_price, lower_price, order_amount, bid_ask:bool):

    min_notional, min_qty, max_qty, decimals, tick_decimals = get_instrument_info(client, ticker)
    orders = []

    spacing = (upper_price - lower_price) / (order_amount)
    last_price = get_last_price(client, ticker)
    if side == "b":
        side = "BUY"
    elif side == "s":
        side = "SELL"

    error = True
    if not bid_ask:
        if upper_price > lower_price:
            if side == "BUY":
                if last_price > upper_price:
                    error = False
                else:
                    print("on buy side last price should be higher than upper price limit")
            elif side == "SELL":
                if last_price < lower_price:
                    error = False
                else:
                    print("on sell side last price should be lower than lower price limit")
            else:
                print(f"Error with side input || input: {side} || should be: b/s")
        else:
            print("upper price limit should be higher than lower price limit")
    else:
        error = False


    if not error:
        last_price = get_last_price(client, ticker)
        total_coins = coin_size

        single_order = round(total_coins / order_amount, decimals)

        price = lower_price
        for i in range(order_amount):
            orders.append([round(single_order, decimals), round(price, tick_decimals)])
            price += spacing

        for order in orders:
            client.new_order(symbol=ticker, side=side, type="LIMIT", quantity=order[0], price=order[1], timeInForce="GTC", reduceOnly=True)
            time.sleep(0.01)


def select_close_id_futures(client):
    positions = get_open_positions(client=client, display=True)

    try:

        while True:
            close_id = int(input("select ID of the position you wish to close >>> "))

            if close_id in positions.keys():
                position = positions[close_id]
                ticker = position["ticker"]
                side = position["side"]
                size = float(position["coin_size"])
                usd_value = float(position["usd_size"])

                if side == "Buy":
                    side = "s"
                elif side == "Sell":
                    side = "b"

                return close_id, ticker, side, size, usd_value
            else:
                print("Wrong ID selected")
    except:
        print("Error: ID must be number")

# create order functions
def set_market_order_open(client):
    """

    :param client:
    :return:
    """

    tickers = get_usdt_m_tickers(client=client)
    ticker = cli_inputs.select_ticker(tickers=tickers, spot=False)

    side = cli_inputs.select_side()
    usd_size = cli_inputs.select_usdt_size()

    market_order_thread = Thread(target=market_order_open, args=(client, usd_size, ticker, side), name=f"BinanceF_{ticker}_{side}_{usd_size}").start()


def set_market_order_close(client):
    """

    :param client:
    :return:
    """

    close_id, ticker, side, coin_size, usd_value = select_close_id_futures(client)
    min_notional, min_qty, max_qty, decimals, tick_decimals = get_instrument_info(client, ticker)

    pct = cli_inputs.select_pct()
    coin_size = round(coin_size * pct, decimals)

    market_order_thread = Thread(target=market_order_close, args=(client,coin_size, ticker, side, pct), name=f"BinanceF_{ticker}_{side}_{coin_size}_coins").start()


def set_linear_twap_open(client):
    tickers = get_usdt_m_tickers(client=client)
    ticker = cli_inputs.select_ticker(tickers=tickers, spot=False)

    side = cli_inputs.select_side()
    usd_size = cli_inputs.select_usdt_size()
    duration = cli_inputs.select_duration()
    order_amount = cli_inputs.select_order_amount()

    linear_twap_thread = Thread(target=linear_twap_open, args=(client, ticker, side, usd_size, duration, order_amount), name=f"BinanceF_{ticker}_{side}_{usd_size}_twap{round(duration / 60)}min").start()


def set_linear_twap_close(client):
    """

       :param client:
       :return:
       """

    close_id, ticker, side, coin_size, usd_value = select_close_id_futures(client)
    min_notional, min_qty, max_qty, decimals, tick_decimals = get_instrument_info(client, ticker)

    pct = cli_inputs.select_pct()
    coin_size = round(coin_size * pct, decimals)
    duration = cli_inputs.select_duration()
    order_amount = cli_inputs.select_order_amount()

    linear_twap_thread = Thread(target=linear_twap_close, args=(client, ticker, side, coin_size, duration, order_amount, pct), name=f"BinanceF_{ticker}_{side}_{coin_size}_coins_twap{round(duration / 60)}min").start()


def set_limits_open(client):

    positions = get_open_positions(client, False)

    tickers = get_usdt_m_tickers(client=client)
    ticker = cli_inputs.select_ticker(tickers=tickers, spot=False)
    side = cli_inputs.select_side()
    usd_size = cli_inputs.select_usdt_size()
    upper_price = cli_inputs.select_upper_limit_price()
    lower_price = cli_inputs.select_lower_limit_price()
    order_amount = cli_inputs.select_order_amount()

    bid_ask = False
    position_exits = False
    position = None
    for key, value in positions.items():
        if value["ticker"] == ticker:
            position_exits = True
            position = value
            break

    if not position_exits:
        # do you want to place sl ?
        sl_check = 0
        while sl_check not in [1, 2]:
            sl_check = int(input("Do you want to place stoploss ?[1 > yes, 2 > no] >>> "))
            if sl_check in [1, 2]:
                if sl_check == 1:
                    sl_price_ok = False
                    sl_side = None
                    while not sl_price_ok:
                        if side == "b":
                            sl_price = float(input("Choose stoploss price >>> "))
                            try:
                                if sl_price > 0 and sl_price < lower_price:
                                    sl_price_ok = True
                                    sl_side = "SELL"

                                    client.new_order(symbol=ticker, side=sl_side, type="STOP_MARKET ", stopPrice=sl_price, closePosition=True, timeInForce="GTC")
                            except:
                                print("Wrong stoploss input, must be number and lower than lowest limit order")

                        elif side == "s":
                            sl_price = float(input("Choose stoploss price >>> "))
                            try:
                                if sl_price > upper_price:
                                    sl_price_ok = True
                                    sl_side = "BUY"
                                    client.new_order(symbol=ticker, side=sl_side, type="STOP_MARKET ", stopPrice=sl_price, closePosition=True, timeInForce="GTC")

                            except:
                                print("Wrong stoploss input, must be number and higher than highest limit order")
            else:
                print("wrong input, try again")

    limit_open_thread = Thread(target=limit_tranche_open, args=(client, usd_size, ticker, side, upper_price, lower_price, order_amount, bid_ask), name=f"BinanceF_{ticker}_{side}_limit_tranche_{usd_size}").start()


def set_limits_close(client):
    close_id, ticker, side, coin_size, usd_value = select_close_id_futures(client)
    min_notional, min_qty, max_qty, decimals, tick_decimals = get_instrument_info(client, ticker)
    bid_ask = False
    close = False
    while not close:
        close_by = input("close by: usd size or % [1-usd, 2-%] >>> ")
        if int(close_by) == 1:
            usd_size = cli_inputs.select_usdt_size()
            last_price = get_last_price(client, ticker)
            coin_size = round(usd_size / last_price, decimals)
            close = True
        elif int(close_by) == 2:
            pct = cli_inputs.select_pct()
            coin_size = round(coin_size * pct, decimals)
            close = True
        else:
            print("Wrong input should be 1 or 2")

    upper_price = cli_inputs.select_upper_limit_price()
    lower_price = cli_inputs.select_lower_limit_price()
    order_amount = cli_inputs.select_order_amount()


    # limit_tranche_close(client, coin_size, ticker, side, upper_price, lower_price, order_amount)
    if close:
        limit_close_thread = Thread(target=limit_tranche_close, args=(client, coin_size, ticker, side, upper_price, lower_price, order_amount, bid_ask), name=f"BinanceF_{ticker}_{side}_limit_tranche_{coin_size}").start()


def set_limits_at_bidask_open(client):
    positions = get_open_positions(client, False)

    tickers = get_usdt_m_tickers(client=client)
    ticker = cli_inputs.select_ticker(tickers=tickers, spot=False)
    min_notional, min_qty, max_qty, decimals, tick_decimals = get_instrument_info(client, ticker)

    side = cli_inputs.select_side()
    usd_size = cli_inputs.select_usdt_size()

    bps_range = 0.004
    if ticker in ["BTCUSDT", "ETHUSDT"]:
        bps_range = 0.001
    last_price = get_last_price(client, ticker)

    if side == "b":
        upper_price = last_price
        lower_price = round(upper_price - (last_price * bps_range), tick_decimals)
    elif side == "s":
        lower_price = last_price
        upper_price = round(lower_price + (last_price * bps_range), tick_decimals)

    order_amount = 10
    bid_ask = True

    position_exits = False
    position = None
    for key, value in positions.items():
        if value["ticker"] == ticker:
            position_exits = True
            position = value
            break

    if not position_exits:
        # do you want to place sl ?
        sl_check = 0
        while sl_check not in [1, 2]:
            sl_check = int(input("Do you want to place stoploss ?[1 > yes, 2 > no] >>> "))
            if sl_check in [1, 2]:
                if sl_check == 1:
                    sl_price_ok = False
                    sl_side = None
                    while not sl_price_ok:
                        if side == "b":
                            sl_price = float(input("Choose stoploss price >>> "))
                            try:
                                if sl_price > 0 and sl_price < lower_price:
                                    sl_price_ok = True
                                    sl_side = "SELL"

                                    client.new_order(symbol=ticker, side=sl_side, type="STOP_MARKET ", stopPrice=sl_price, closePosition=True, timeInForce="GTC")
                            except:
                                print("Wrong stoploss input, must be number and lower than lowest limit order")

                        elif side == "s":
                            sl_price = float(input("Choose stoploss price >>> "))
                            try:
                                if sl_price > upper_price:
                                    sl_price_ok = True
                                    sl_side = "BUY"
                                    client.new_order(symbol=ticker, side=sl_side, type="STOP_MARKET ", stopPrice=sl_price, closePosition=True, timeInForce="GTC")

                            except:
                                print("Wrong stoploss input, must be number and higher than highest limit order")
            else:
                print("wrong input, try again")

    limit_open_thread = Thread(target=limit_tranche_open, args=(client, usd_size, ticker, side, upper_price, lower_price, order_amount, bid_ask), name=f"BinanceF_{ticker}_{side}_limit_tranche_{usd_size}").start()


def set_limits_at_bidask_close(client):
    close_id, ticker, side, coin_size, usd_value = select_close_id_futures(client)
    min_notional, min_qty, max_qty, decimals, tick_decimals = get_instrument_info(client, ticker)

    bps_range = 0.004
    if ticker in ["BTCUSDT", "ETHUSDT"]:
        bps_range = 0.001

    bid_ask = True
    close = False
    while not close:
        close_by = input("close by: usd size or % [1-usd, 2-%] >>> ")
        if int(close_by) == 1:
            usd_size = cli_inputs.select_usdt_size()
            last_price = get_last_price(client, ticker)
            coin_size = round(usd_size / last_price, decimals)
            close = True
        elif int(close_by) == 2:
            pct = cli_inputs.select_pct()
            coin_size = round(coin_size * pct, decimals)
            close = True
        else:
            print("Wrong input should be 1 or 2")

    last_price = get_last_price(client, ticker)
    if side == "b":
        upper_price = last_price
        lower_price = round(upper_price - (last_price * bps_range), tick_decimals)
    elif side == "s":
        lower_price = last_price
        upper_price = round(lower_price + (last_price * bps_range), tick_decimals)

    order_amount = 10

    # limit_tranche_close(client, coin_size, ticker, side, upper_price, lower_price, order_amount)
    if close:
        limit_close_thread = Thread(target=limit_tranche_close, args=(client, coin_size, ticker, side, upper_price, lower_price, order_amount, bid_ask), name=f"BinanceF_{ticker}_{side}_limit_tranche_{coin_size}").start()


def close_all_positions(client):
    """
    Function that close all open positions
    :param client:
    :return:
    """

    positions = get_open_positions(client=client, display=False)
    if positions:
        print("Select duration in which you want to close all positions[minutes]")
        duration = cli_inputs.select_duration()
        for close_id in positions.keys():
            pct = 1
            position = positions[close_id]
            ticker = position["ticker"]
            side = position["side"]
            coin_size = float(position["coin_size"])
            usd_value = float(position["usd_size"])

            if side == "Buy":
                side_ = "long"
                side = "s"
            elif side == "Sell":
                side_ = "short"
                side = "b"

            if duration > 400:
                if usd_value <= 20000:
                    order_amount = 20
                elif 20000 < usd_value <= 50000:
                    order_amount = 50
                elif 50000 < usd_value <= 100000:
                    order_amount = 100
                elif 100000 < usd_value <= 250000:
                    order_amount = 150
                elif 250000 < usd_value <= 500000:
                    order_amount = 200
                elif 500000 < usd_value <= 1000000:
                    order_amount = 300
                elif usd_value > 1000000:
                    order_amount = 400
            else:
                if usd_value <= 20000:
                    order_amount = 1
                elif 20000 < usd_value <= 50000:
                    order_amount = 3
                elif 50000 < usd_value <= 100000:
                    order_amount = 5
                elif 100000 < usd_value <= 250000:
                    order_amount = 10
                elif 250000 < usd_value <= 500000:
                    order_amount = 15
                elif 500000 < usd_value <= 1000000:
                    order_amount = 30
                elif usd_value > 1000000:
                    order_amount = 45

            print(f"started closing {ticker} {side_} || {coin_size} coins")
            linear_twap_thread = Thread(target=linear_twap_close, args=(client, ticker, side, coin_size, duration, order_amount, pct), name=f"BinanceF_{ticker}_{side}_{coin_size}_coins_twap{round(duration / 60)}min").start()
    else:
        print("\nNo open positions")








