from binance.client import Client
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
import datetime as dt
import colorama
from colorama import Fore

colorama.init(autoreset=True)
pd.set_option('display.max_columns', 20)
pd.set_option('display.width', 500)

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
    binance_spot_client = Client(testnet=False, api_key=api_key, api_secret=api_secret)
    binance_usdt_m_client = UMFutures(key=api_key, secret=api_secret)

    return binance_spot_client, binance_usdt_m_client


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


def get_instrument_info_spot(client, ticker):
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


def get_instrument_info_usdt_m(client, ticker):
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


def get_filled_orders_spot(client):

    tickers = get_spot_tickers(client)
    ticker = cli_inputs.select_ticker(tickers)
    lookback_window = cli_inputs.select_lookback_window()
    orders = client.get_my_trades(symbol=ticker, limit=1000)
    min_notional, max_notional, decimals, tick_decimals, min_qty, max_qty = get_instrument_info_spot(client, ticker)

    start = dt.datetime.now() - dt.timedelta(hours=lookback_window)

    cum_buy_qty = 0
    buy_prc_times_qty = 0

    cum_sell_qty = 0
    sell_prc_times_qty = 0

    filled_orders = []
    for i in orders:
        i["time"] = dt.datetime.fromtimestamp(i["time"]/1000)
        if i["time"] >= start:
            if i["isBuyer"]:
                cum_buy_qty += float(i["qty"])
                buy_prc_times_qty += float(i["qty"]) * float(i["price"])

            else:
                cum_sell_qty += float(i["qty"])
                sell_prc_times_qty += float(i["qty"]) * float(i["price"])


    if cum_buy_qty > 0:
        filled_orders.append([ticker, "BUY", cum_buy_qty, round(buy_prc_times_qty / cum_buy_qty, tick_decimals)])

    if cum_sell_qty > 0:
        filled_orders.append([ticker, "SELL", cum_sell_qty, round(sell_prc_times_qty / cum_sell_qty, tick_decimals)])

    # print(f"BUY >> executed qty: {cum_buy_qty} || avg price: {round(buy_prc_times_qty / cum_buy_qty, tick_decimals)}")
    # print(f"SELL >> executed qty: {cum_sell_qty} || avg price: {round(sell_prc_times_qty / cum_sell_qty, tick_decimals)}")

    final_df = pd.DataFrame(filled_orders, columns=["ticker", "side" ,"coins", "avg_price"])
    final_df["usd_value"] = round(final_df["coins"] * final_df["avg_price"],2)
    print(final_df.to_markdown())


def view_open_orders_spot(client):
    pass

def get_filled_orders_usdt_m(client):

    tickers = get_usdt_m_tickers(client)
    ticker = cli_inputs.select_ticker(tickers)
    lookback_window = cli_inputs.select_lookback_window()
    orders = client.get_account_trades(symbol="BTCUSDT", limit=1000)
    min_notional, min_qty, max_qty, decimals, tick_decimals = get_instrument_info_usdt_m(client, ticker)

    start = dt.datetime.now() - dt.timedelta(hours=lookback_window)

    cum_buy_qty = 0
    buy_prc_times_qty = 0

    cum_sell_qty = 0
    sell_prc_times_qty = 0

    filled_orders = []
    for i in orders:
        i["time"] = dt.datetime.fromtimestamp(i["time"] / 1000)
        if i["time"] >= start:
            if i["buyer"]:
                cum_buy_qty += float(i["qty"])
                buy_prc_times_qty += float(i["qty"]) * float(i["price"])

            else:
                cum_sell_qty += float(i["qty"])
                sell_prc_times_qty += float(i["qty"]) * float(i["price"])

    if cum_buy_qty > 0:
        filled_orders.append([ticker, "BUY", cum_buy_qty, round(buy_prc_times_qty / cum_buy_qty, tick_decimals)])

    if cum_sell_qty > 0:
        filled_orders.append([ticker, "SELL", cum_sell_qty, round(sell_prc_times_qty / cum_sell_qty, tick_decimals)])

    # print(f"BUY >> executed qty: {cum_buy_qty} || avg price: {round(buy_prc_times_qty / cum_buy_qty, tick_decimals)}")
    # print(f"SELL >> executed qty: {cum_sell_qty} || avg price: {round(sell_prc_times_qty / cum_sell_qty, tick_decimals)}")

    final_df = pd.DataFrame(filled_orders, columns=["ticker", "side", "coins", "avg_price"])
    final_df["usd_value"] = round(final_df["coins"] * final_df["avg_price"], 2)
    print(final_df.to_markdown())


def orderOverview_binance_personal_SPOT():
    spot_client, usdt_m_client = auth()

    exit = False
    while not exit:
        print("\n")
        print(Fore.LIGHTYELLOW_EX +"What do you want to do:"
              "\n 1 >> display spot positions"
              "\n 2 >> view filled orders"
              "\n 3 >> view open limit orders"
              "\n 4 >> cancel orders"
              "\n 0 >> exit ")
        mode = int(input("input number >>> "))
        if mode == 0:
            exit = True
            print(Fore.LIGHTYELLOW_EX +f"Binance SPOT >> personal account - closing")
        elif mode == 1:
            print("\n")
            get_spot_balances(spot_client, True)
        elif mode == 2:
            print("\n")
            get_filled_orders_spot(spot_client)
        elif mode == 3:
            print("\n")
            print("Not available yet")
        elif mode == 4:
            print("\n")
            print("Not available yet")
            # print(Fore.LIGHTCYAN_EX + "cancel options:"
            #       "\n 1 >> cancel all orders for specific side"
            #       "\n 2 >> cancel orders between 2 prices for specific side")
            # price_mode = int(input(Fore.LIGHTCYAN_EX + "Input number >>> "))

def orderOverview_binance_personal_usdt_m():
    spot_client, usdt_m_client = auth()

    exit = False
    while not exit:
        print("\n")
        print(Fore.LIGHTYELLOW_EX +"What do you want to do:"
              "\n 1 >> view filled orders"
              "\n 2 >> view open limit orders"
              "\n 3 >> cancel orders"
              "\n 0 >> exit ")
        mode = int(input("input number >>> "))
        if mode == 0:
            exit = True
            print(Fore.LIGHTYELLOW_EX +f"Binance SPOT >> personal account - closing")
        elif mode == 1:
            print("\n")
            get_filled_orders_usdt_m(usdt_m_client)
        elif mode == 2:
            print("\n")
            print("Not available yet")
        elif mode == 3:
            print("\n")
            print("Not available yet")
            # print(Fore.LIGHTCYAN_EX + "cancel options:"
            #       "\n 1 >> cancel all orders for specific side"
            #       "\n 2 >> cancel orders between 2 prices for specific side")
            # price_mode = int(input(Fore.LIGHTCYAN_EX + "Input number >>> "))

def main():
    exit = False
    while not exit:
        print("\n")
        print(Fore.LIGHTYELLOW_EX + "Select account:"
              "\n 1 >> Binance - personal_SPOT"
              "\n 2 >> Binance - persoanl USDT-M"
              "\n 0 >> exit terminal")

        mode = int(input(Fore.LIGHTYELLOW_EX + "input number >>> "))
        if mode == 0:
            exit = True
            print("\n")
            print(Fore.LIGHTYELLOW_EX + "Terminal closing")
        elif mode == 1:
            print("\n")
            orderOverview_binance_personal_SPOT()
        elif mode == 2:
            print("\n")
            orderOverview_binance_personal_usdt_m()


if __name__ == "__main__":
    main()






