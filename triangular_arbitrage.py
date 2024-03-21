import asyncio
import traceback
import sqlite3
from binance import BinanceSocketManager
from binance.exceptions import BinanceAPIException
from chain import Chain
from crypto_symbol import Symbol
import os
import numpy as np


class TriangularArbitrage:
    """
    Class for implementing triangular arbitrage trading strategy on Binance.
    """

    def __init__(self, client, testnet, holdings):
        """
        Initializes the TriangularArbitrage instance.

        Parameters:
        - client: Binance client instance.
        - testnet: Boolean indicating whether to use the Binance testnet.
        - holdings: List of tuples representing base currency and quantity.
        """
        self.client = client
        self.testnet = testnet
        self.holdings = holdings
        self.symbols = {}
        self.chains = []
        self.unique_symbols = set()
        self.cancel_in_progress = False
        self.data_base_batch = {
            "name": [],
            "base_currency": [],
            "duration": [],
            "profit": [],
            "trajectory": [],
        }
        self.bm = BinanceSocketManager(self.client)

        # Database
        # Check if the database file exists
        if os.path.exists("data.db"):
            # Delete the database file
            os.remove("data.db")

        self.conn = sqlite3.connect("data.db")
        self.c = self.conn.cursor()

        # Create profit_durations table if not exists
        self.c.execute(
            """CREATE TABLE IF NOT EXISTS profit_durations
                       (id INTEGER PRIMARY KEY, name TEXT, base_currency TEXT, duration INTEGER, starting_profit REAL)"""
        )

        # Create profit_trajectories table if not exists
        self.c.execute(
            """CREATE TABLE IF NOT EXISTS profit_trajectories
                          (id INTEGER PRIMARY KEY, trajectory TEXT)"""
        )

        # Commit changes
        self.conn.commit()

    async def get_exchange_info(self):
        """
        Retrieves exchange information and initializes symbols for trading.
        """
        try:
            exchange_info = await self.client.get_exchange_info()
        except BinanceAPIException as e:
            print(e, flush=True)

        symbol_info = exchange_info["symbols"]
        self.symbols = {
            d["symbol"]: Symbol(
                symbol_name=d["symbol"],
                baseAsset=d["baseAsset"],
                quoteAsset=d["quoteAsset"],
                filters=d["filters"],
                precision=d["quotePrecision"],
                ta_instance=self,
            )
            for d in symbol_info
            if d["status"] == "TRADING"
            and d["isSpotTradingAllowed"]
            and "MARKET" in d["orderTypes"]
            and d["quoteOrderQtyMarketAllowed"]
        }

    async def generate_triangular_chains(self):
        """
        Generates triangular chains based on available symbols and holdings.
        """

        def is_base_or_quote(symbol, currency):
            return symbol.baseAsset == currency or symbol.quoteAsset == currency

        def is_base_and_quote(symbol, first_currency, second_currency):
            return (
                symbol.baseAsset == first_currency
                and symbol.quoteAsset == second_currency
            ) or (
                symbol.baseAsset == second_currency
                and symbol.quoteAsset == first_currency
            )

        def is_eligible(symbol, excluded_currency):
            return (
                symbol.baseAsset != excluded_currency
                and symbol.quoteAsset != excluded_currency
                and any(symbol.baseAsset in [a.baseAsset, a.quoteAsset] for a in first)
                and any(symbol.quoteAsset in [a.baseAsset, a.quoteAsset] for a in first)
            )

        def direction(symbols, currency):
            directions = []
            if symbols[0].quoteAsset == currency:
                directions.append("BUY")
            else:
                directions.append("SELL")

            if symbols[1].quoteAsset in [symbols[0].baseAsset, symbols[0].quoteAsset]:
                directions.append("BUY")
            else:
                directions.append("SELL")

            if symbols[2].quoteAsset in [symbols[1].baseAsset, symbols[1].quoteAsset]:
                directions.append("BUY")
            else:
                directions.append("SELL")

            return directions

        chains = []
        for base_currency, quantity in self.holdings:
            first = [
                symbol
                for symbol in self.symbols.values()
                if is_base_or_quote(symbol, base_currency)
            ]
            second = [
                symbol
                for symbol in self.symbols.values()
                if is_eligible(symbol, base_currency)
            ]

            for a in first:
                for b in second:
                    if a.baseAsset == b.baseAsset or a.quoteAsset == b.baseAsset:
                        for c in first:
                            if is_base_and_quote(c, base_currency, b.quoteAsset):
                                chains.append(
                                    Chain(
                                        base_currency,
                                        [a, b, c],
                                        direction([a, b, c], base_currency),
                                        quantity,
                                        self,
                                    )
                                )
                    if a.baseAsset == b.quoteAsset or a.quoteAsset == b.quoteAsset:
                        for c in first:
                            if is_base_and_quote(c, base_currency, b.baseAsset):
                                chains.append(
                                    Chain(
                                        base_currency,
                                        [a, b, c],
                                        direction([a, b, c], base_currency),
                                        quantity,
                                        self,
                                    )
                                )

        self.chains = chains
        # Remove symbols that do not have chains associated with them
        symbols_to_remove = [
            symbol_name
            for symbol_name, symbol in self.symbols.items()
            if not symbol.associated_chains
        ]
        for symbol_name in symbols_to_remove:
            self.symbols.pop(symbol_name)
        print("Need to listen to {} symbols".format(len(self.symbols)), flush=True)
        print("Watching {} chains".format(len(self.chains)), flush=True)

    async def get_trade_fees(self):
        """
        Retrieves trade fees for symbols and updates associated symbols.
        """
        try:
            trade_fee_info = await self.client.get_trade_fee()
        except BinanceAPIException as e:
            print("Could not access fee info. Setting all fees to zero.")
            default_fee = [0.0, 0.0]
            fees = {symbol_name: default_fee for symbol_name in self.symbols}
        else:
            fees = {
                fee["symbol"]: [
                    float(fee["makerCommission"]),
                    float(fee["takerCommission"]),
                ]
                for fee in trade_fee_info
            }

        for symbol_name, fee in fees.items():
            if symbol_name in self.symbols:
                self.symbols[symbol_name].update_fee(fee)

    async def init_orderbook_info(self):
        """
        Initializes orderbook information for symbols.
        """
        try:
            orderbook_ticker = await self.client.get_orderbook_ticker()
        except BinanceAPIException as e:
            print(e, flush=True)
        for res in orderbook_ticker:
            symbol_name = res["symbol"]
            if symbol_name in self.symbols:
                bid_price = float(res["bidPrice"])
                ask_price = float(res["askPrice"])
                bid_qty = float(res["bidQty"])
                ask_qty = float(res["askQty"])
                symbol = self.symbols[symbol_name]
                await symbol.update_prices(bid_price, ask_price, bid_qty, ask_qty)

    async def market_data(self, num_sockets=5):
        """
        Collects market data and stores it in a database.

        Parameters:
        - num_sockets: Number of websocket connections to use.
        """
        self.c.execute(
            """CREATE TABLE IF NOT EXISTS arbitrage_correlation
                          (id INTEGER PRIMARY KEY, arbitrage_num INTEGER, duration FLOAT, profit FLOAT, volatility FLOAT, volume FLOAT)"""
        )

        # Commit changes
        self.conn.commit()

        self.current_start_time = None
        self.warm_up_done = False
        self.volatility = 0
        self.volume = 0

        symbols_to_subscribe = list(self.symbols.values())

        # Divide symbols into approximately equal parts
        symbols_per_socket = len(symbols_to_subscribe) // num_sockets
        symbol_chunks = [
            symbols_to_subscribe[i : i + symbols_per_socket]
            for i in range(0, len(symbols_to_subscribe), symbols_per_socket)
        ]

        async def process_chunk(chunk):
            async with self.bm.multiplex_socket(
                [symbol.symbol_name.lower() + "@kline_1m" for symbol in chunk]
            ) as tscm:
                while not self.cancel_in_progress:
                    try:
                        res = await tscm.recv()
                        if res["data"]["k"]["x"] == True:
                            self.current_start_time = res["data"]["k"]["t"]
                            self.volatility += abs(
                                len(self.symbols[res["data"]["s"]].associated_chains)
                                / (3 * len(self.chains))
                                * (
                                    float(res["data"]["k"]["h"])
                                    - float(res["data"]["k"]["l"])
                                )
                                / float(res["data"]["k"]["l"])
                            )
                            if res["data"]["s"].endswith("USDT"):
                                self.volume += float(res["data"]["k"]["q"])
                            elif res["data"]["s"].startswith("USDT"):
                                self.volume += float(res["data"]["k"]["v"])
                        elif (
                            res["data"]["k"]["x"] == False
                            and self.current_start_time != None
                        ):
                            if self.warm_up_done == True:
                                self.c.execute(
                                    "INSERT INTO arbitrage_correlation (arbitrage_num, duration, profit, volatility, volume) VALUES (?, ?, ?, ?, ?)",
                                    (
                                        len(self.data_base_batch["profit"]),
                                        np.mean(self.data_base_batch["duration"]),
                                        np.mean(self.data_base_batch["profit"]),
                                        self.volatility,
                                        self.volume,
                                    ),
                                )

                                with self.conn:
                                    self.c.executemany(
                                        "INSERT INTO profit_durations (name, base_currency, duration, starting_profit) VALUES (?, ?, ?, ?)",
                                        zip(
                                            self.data_base_batch["name"],
                                            self.data_base_batch["base_currency"],
                                            self.data_base_batch["duration"],
                                            self.data_base_batch["profit"],
                                        ),
                                    )
                                    self.c.executemany(
                                        "INSERT INTO profit_trajectories (trajectory) VALUES (?)",
                                        [
                                            (trajectory,)
                                            for trajectory in self.data_base_batch[
                                                "trajectory"
                                            ]
                                        ],
                                    )

                                self.conn.commit()

                                for data in self.data_base_batch:
                                    self.data_base_batch[data] = []

                                self.volatility = 0
                                self.volume = 0
                                self.current_start_time = None
                            else:
                                self.warm_up_done = True
                                for data in self.data_base_batch:
                                    self.data_base_batch[data] = []

                                self.volatility = 0
                                self.volume = 0
                                self.current_start_time = None

                    except Exception as e:
                        print(e, flush=True)
                    except asyncio.CancelledError:
                        # Handle cancellation, e.g., cleanup or logging
                        self.cancel_in_progress = True
                        print("Cancel in progress set to True", flush=True)

        async with asyncio.TaskGroup() as tg:
            for chunk in symbol_chunks:
                tg.create_task(process_chunk(chunk))

        await asyncio.sleep(2)

    async def update_orderbook_info(self, num_sockets=5):
        """
        Updates orderbook information for symbols using websockets.

        Parameters:
        - num_sockets: Number of websocket connections to use.
        """
        symbols_to_subscribe = list(self.symbols.values())

        # Divide symbols into approximately equal parts
        symbols_per_socket = len(symbols_to_subscribe) // num_sockets
        symbol_chunks = [
            symbols_to_subscribe[i : i + symbols_per_socket]
            for i in range(0, len(symbols_to_subscribe), symbols_per_socket)
        ]

        async def process_chunk(chunk):
            async with self.bm.multiplex_socket(
                [symbol.symbol_name.lower() + "@bookTicker" for symbol in chunk]
            ) as tscm:
                while not self.cancel_in_progress:
                    try:
                        res = await tscm.recv()
                        symbol_name = res["data"]["s"]
                        bid_price = float(res["data"]["b"])
                        ask_price = float(res["data"]["a"])
                        bid_qty = float(res["data"]["B"])
                        ask_qty = float(res["data"]["A"])
                        symbol = self.symbols[symbol_name]
                        await symbol.update_prices(
                            bid_price, ask_price, bid_qty, ask_qty
                        )
                    except Exception as e:
                        print(e, flush=True)
                    except asyncio.CancelledError:
                        # Handle cancellation, e.g., cleanup or logging
                        self.cancel_in_progress = True
                        print("Cancel in progress set to True", flush=True)

        async with asyncio.TaskGroup() as tg:
            for chunk in symbol_chunks:
                tg.create_task(process_chunk(chunk))

    async def cleanup(self):
        """
        Cleans up resources and closes connections.
        """
        print("Starting cleanup...", flush=True)
        if self.client:
            await asyncio.sleep(3)
            await self.client.close_connection()
            print("Connections closed", flush=True)
        self.conn.close()

        print("Cleanup done", flush=True)

    async def run(self):
        """
        Main execution method for the TriangularArbitrage instance.
        """
        try:
            await self.get_exchange_info()
            print("Exchange Info done", flush=True)
            await self.generate_triangular_chains()
            print("Generating chains done", flush=True)
            await self.get_trade_fees()
            print("Getting fees done", flush=True)
            await self.init_orderbook_info()
            print("Initializing orderbook done", flush=True)
            self.market_data_task = asyncio.create_task(self.market_data())
            print("Watching market data", flush=True)
            self.update_task = asyncio.create_task(self.update_orderbook_info())
            await asyncio.gather(
                self.update_task, self.market_data_task
            )  # Wait for the tasks to finish
        except Exception as e:
            print("An error occurred within the run method:", e)
            traceback.print_exc()
        finally:
            await self.cleanup()

# Usage example:
# client = ...  # Binance client instance
# testnet = True  # Use the Binance testnet
# holdings = [('BTC', 1), ('ETH', 1), ('BNB', 1)]  # Example holdings
# ta = TriangularArbitrage(client, testnet, holdings)
# asyncio.run(ta.run())
