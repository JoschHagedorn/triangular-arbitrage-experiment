import asyncio
import time


class Symbol:
    """
    Represents a trading symbol on Binance.

    Attributes:
    - symbol_name (str): The symbol name.
    - baseAsset (str): The base asset of the symbol.
    - quoteAsset (str): The quote asset of the symbol.
    - filters (list): List of filters defining trading constraints.
    - ta_instance: The instance of TriangularArbitrage associated with the symbol.
    - bid_price (float): The current best bid price.
    - ask_price (float): The current best ask price.
    - bid_qty (float): The quantity of the current best bid price.
    - ask_qty (float): The quantity of the current best ask price.
    - trading_fee (list): Trading fees associated with the symbol.
    - associated_chains (list): List of Chain instances associated with the symbol.
    - stepSize (float): The minimum tradable quantity based on LOT_SIZE filter.
    """

    def __init__(
        self, symbol_name, baseAsset, quoteAsset, filters, precision, ta_instance
    ):
        """
        Initializes the Symbol instance.

        Parameters:
        - symbol_name (str): The symbol name.
        - baseAsset (str): The base asset of the symbol.
        - quoteAsset (str): The quote asset of the symbol.
        - filters (list): List of filters defining trading constraints.
        - precision (int): The precision of the symbol.
        - ta_instance: The instance of TriangularArbitrage associated with the symbol.
        """
        self.symbol_name = symbol_name
        self.baseAsset = baseAsset
        self.quoteAsset = quoteAsset
        self.filters = filters
        self.precision = precision
        self.ta_instance = ta_instance
        self.bid_price = 0
        self.ask_price = 0
        self.bid_qty = 0
        self.ask_qty = 0
        self.trading_fee = None
        self.associated_chains = []
        self.stepSize = None

        # Extract stepSize from LOT_SIZE filter
        for filter in self.filters:
            if filter["filterType"] == "LOT_SIZE":
                self.stepSize = float(filter["stepSize"])

    def associate_chain(self, chain_instance):
        """
        Associates a Chain instance with the symbol.

        Parameters:
        - chain_instance: The Chain instance to be associated.
        """
        self.associated_chains.append(chain_instance)

    async def update_prices(self, bid_price, ask_price, bid_qty, ask_qty):
        """
        Updates bid and ask prices along with quantities.

        Parameters:
        - bid_price (float): The current best bid price.
        - ask_price (float): The current best ask price.
        - bid_qty (float): The quantity of the current best bid price.
        - ask_qty (float): The quantity of the current best ask price.
        """
        if self.bid_price == None and self.ask_price == None:
            self.bid_price = bid_price
            self.ask_price = ask_price
            self.bid_qty = bid_qty
            self.ask_qty = ask_qty
        else:
            if self.bid_price != bid_price or self.ask_price != ask_price:
                price_change = True
            else:
                price_change = False

            self.bid_price = bid_price
            self.ask_price = ask_price
            self.bid_qty = bid_qty
            self.ask_qty = ask_qty

            if price_change:
                time_stamp = time.monotonic_ns()
                asyncio.create_task(self.update_associated_chains(time_stamp))

            else:
                if any(chain.profit > 0 for chain in self.associated_chains):
                    time_stamp = time.monotonic_ns()
                    asyncio.create_task(self.update_profitable_chains(time_stamp))

    async def update_associated_chains(self, time_stamp):
        """
        Updates associated chains when there is a price change.
        """
        for chain in self.associated_chains:
            await chain.calculate_profit(time_stamp)

    async def update_profitable_chains(self, time_stamp):
        """
        Updates associated chains when there is a price change and profit is positive.
        """
        for chain in self.associated_chains:
            if chain.profit > 0:
                await chain.calculate_profit(time_stamp)

    def update_fee(self, trading_fee):
        """
        Updates trading fees associated with the symbol.

        Parameters:
        - trading_fee (list): List with [makerCommission, takerCommission].
        """
        self.trading_fee = trading_fee
