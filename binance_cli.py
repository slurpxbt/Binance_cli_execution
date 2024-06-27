import binance_spot
import binance_usdt_futures
import threading
import colorama
from colorama import Fore

colorama.init(autoreset=True)


def get_all_running_threads():
    if len(threading.enumerate()) == 1:
        print(Fore.LIGHTYELLOW_EX + "No running proceses")
    else:
        print(Fore.LIGHTYELLOW_EX + "Current running processes:")
        for thread in threading.enumerate():
            if thread.name != "MainThread":
                print(thread.name)


def binance_spot_cli():

    client = binance_spot.auth()

    exit = False
    while not exit:
        print("\n")
        print(Fore.LIGHTYELLOW_EX + "What do you want to do:"
              "\n 1 >> display positions"
              "\n 2 >> market orders"
              "\n 3 >> limit orders"
              "\n 4 >> limits at bid/ask"
              "\n 5 >> TWAPS"
              "\n 0 >> exit - Binance SPOT"
              "\n 99 >> restart client"
              "\n 999 >> check current running processes")

        try:
            mode = int(input(Fore.LIGHTYELLOW_EX + "input number >>> "))
        except:
            print(Fore.LIGHTYELLOW_EX +"input must be number")
            mode = 0

        if mode == 0:
            exit = True
            print(Fore.LIGHTYELLOW_EX + f"Binance SPOT - closing")
        elif mode == 1:
            binance_spot.get_spot_balances(client, display=True)
        elif mode == 2:
            print("\n")
            print(Fore.LIGHTYELLOW_EX +"Market order mode selected >> options:"
                  "\n 1 >> market order by $ amount"
                  "\n 2 >> market order by acc %")
            try:
                order_mode = int(input(Fore.LIGHTYELLOW_EX + "input number >>> "))
            except:
                print(Fore.LIGHTYELLOW_EX + "input must be number")
                order_mode = 0

            if order_mode == 1:
                binance_spot.set_market_order_usd(client)
            elif order_mode == 2:
                binance_spot.set_market_order_pct(client)

            print("\n")
        elif mode == 3:
            print("\n")
            print(Fore.LIGHTYELLOW_EX + "Limit order mode selected >> options:"
                  "\n 1 >> limit orders between 2 prices by $ amount"
                  "\n 2 >> limit orders between 2 prices by account %"
                  )
            try:
                order_mode = int(input(Fore.LIGHTYELLOW_EX + "input number >>> "))
            except:
                print(Fore.LIGHTYELLOW_EX + "input must be number")
                order_mode = 0

            if order_mode == 1:
                binance_spot.set_limit_orders_usd(client)
            elif order_mode == 2:
                binance_spot.set_limit_orders_pct(client)

            print("\n")
        elif mode == 4:
            print("\n")
            print(Fore.LIGHTYELLOW_EX + "Limit order mode selected >> options:"
                                        "\n 1 >> limit orders by $ amount"
                                        "\n 2 >> limit orders by account %"
                  )
            try:
                order_mode = int(input(Fore.LIGHTYELLOW_EX + "input number >>> "))
            except:
                print(Fore.LIGHTYELLOW_EX + "input must be number")
                order_mode = 0

            if order_mode == 1:
                binance_spot.set_limit_orders_usd_bidask(client)
            elif order_mode == 2:
                binance_spot.set_limit_orders_pct_bid_ask(client)

        elif mode == 5:
            print("\n")
            print(Fore.LIGHTYELLOW_EX + "TWAP mode selected >> options:"
                  "\n 1 >> linear twap by $ amount"
                  "\n 2 >> linear twap by account %")
            try:
                order_mode = int(input(Fore.LIGHTYELLOW_EX +"input number >>> "))
            except:
                print(Fore.LIGHTYELLOW_EX + "input must be number")
                order_mode = 0

            if order_mode == 1:
                binance_spot.set_linear_twap_usd(client)
            elif order_mode == 2:
                binance_spot.set_linear_twap_pct(client)
        elif mode == 999:
            print("\n")
            get_all_running_threads()
            print("\n")
        elif mode == 99:
            print(Fore.LIGHTYELLOW_EX + "Reconnecting client")
            client = binance_spot.auth()
            print("\n")


def binance_futures_cli():

    client = binance_usdt_futures.auth()

    exit = False
    while not exit:
        print("\n")
        print(Fore.LIGHTYELLOW_EX + "What do you want to do:"
              "\n 1 >> display positions"
              "\n 2 >> open position"
              "\n 3 >> close/reduce position"
              "\n 4 >> modify tp/sl"
              "\n 0 >> exit - Binance Futures"
              "\n 99 >> restart client"
              "\n 999 >> check current running processes")
        try:
            mode = int(input(Fore.LIGHTYELLOW_EX + "input number >>> "))
        except:
            print(Fore.LIGHTYELLOW_EX +"input must be number")
            mode = 0

        if mode == 0:
            exit = True
            print(Fore.LIGHTYELLOW_EX + f"Binance Futures - closing")
        elif mode == 1:
            binance_usdt_futures.get_open_positions(client, display=True)
        elif mode == 2:
            print("\n")
            print("Open position mode selected >> options:"
                  "\n 1 >> market orders"
                  "\n 2 >> limit orders"
                  "\n 3 >> limits at bid/ask"
                  "\n 4 >> TWAPS")
            try:
                order_mode = int(input("input number >>> "))
            except:
                print("input must be number")
                order_mode = 0

            if order_mode == 1:
                binance_usdt_futures.set_market_order_open(client)
            elif order_mode == 2:
                binance_usdt_futures.set_limits_open(client)
            elif order_mode == 3:
                binance_usdt_futures.set_limits_at_bidask_open(client)
            elif order_mode == 4:
                binance_usdt_futures.set_linear_twap_open(client)

        elif mode == 3:
            print("\n")
            print("Close / reduce position mode selected >> options:"
                  "\n 1 >> market orders"
                  "\n 2 >> limit orders"
                  "\n 3 >> limits at bid/ask"
                  "\n 4 >> TWAPS"
                  "\n 5 >> close all positions")
            try:
                order_mode = int(input("input number >>> "))
            except:
                print("input must be number")
                order_mode = 0

            if order_mode == 1:
                binance_usdt_futures.set_market_order_close(client)
            elif order_mode == 2:
                binance_usdt_futures.set_limits_close(client)
            elif order_mode == 3:
                binance_usdt_futures.set_limits_at_bidask_close(client)
            elif order_mode == 4:
                binance_usdt_futures.set_linear_twap_close(client)
            elif order_mode == 5:
                binance_usdt_futures.close_all_positions(client)

        elif mode == 4:
            binance_usdt_futures.set_position_sl_tp(client)

        elif mode == 999:
            print("\n")
            get_all_running_threads()
            print("\n")
        elif mode == 99:
            print(Fore.LIGHTYELLOW_EX + "Reconnecting client")
            client = binance_spot.auth()
            print("\n")


def main():

    exit = False
    while not exit:
        print("\n")
        print(Fore.LIGHTYELLOW_EX + "Select account:"
              "\n 1 >> Binance SPOT"
              "\n 2 >> Binance USDT perps"
              "\n 999 >> check current running processes"
              "\n 0 >> exit terminal")

        mode = int(input(Fore.LIGHTYELLOW_EX + "input number >>> "))

        if mode == 0:
            exit = True
            print("\n")
            print(Fore.LIGHTYELLOW_EX + "Terminal closing")
        elif mode == 999:
            print("\n")
            get_all_running_threads()
            print("\n")
        elif mode == 1:
            print("\n")
            binance_spot_cli()
        elif mode == 2:
            print("\n")
            binance_futures_cli()



if __name__ == "__main__":
    main()