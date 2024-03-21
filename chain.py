from binance.helpers import round_step_size
from opportunity import Opportunity


class Chain:
    """
    Represents a chain of trading symbols in a triangular arbitrage strategy.

    Attributes:
    - base_currency (str): The base currency of the chain.
    - symbols (list): List of Symbol instances forming the chain.
    - sides (list): List of trading sides (BUY or SELL) for each symbol.
    - base_quantity (float): The initial quantity of the base currency.
    - ta_instance: The instance of TriangularArbitrage associated with the chain.
    - profit (float): The calculated profit percentage.
    - name (str): A name representing the chain.
    - opportunities (dict): Dictionary of opportunities within the chain.
    - qty_issue (bool): Indicates if there is a quantity issue within the chain.
    """

    def __init__(
        self, base_currency, symbol_instances, sides, base_quantity, ta_instance
    ):
        """
        Initializes the Chain instance.

        Parameters:
        - base_currency (str): The base currency of the chain.
        - symbol_instances (list): List of Symbol instances forming the chain.
        - sides (list): List of trading sides (BUY or SELL) for each symbol.
        - base_quantity (float): The initial quantity of the base currency.
        - ta_instance: The instance of TriangularArbitrage associated with the chain.
        """
        self.base_currency = base_currency
        self.symbols = symbol_instances
        self.sides = sides
        self.base_quantity = base_quantity
        self.ta_instance = ta_instance
        self.profit = 0
        self.name = " ".join([symbol.symbol_name for symbol in self.symbols])
        self.associate_symbols_with_chain()
        self.opportunities = {}
        self.qty_issue = False

    def associate_symbols_with_chain(self):
        """
        Associates each symbol in the chain with the current chain instance.
        """
        for symbol in self.symbols:
            symbol.associate_chain(self)

    async def calculate_profit(self, time_stamp):
        """
        Calculates the profit percentage for the chain.

        Parameters:
        - time_stamp (float): The timestamp when the profit calculation started.
        """
        self.time_stamp = time_stamp
        if all(
            symbol.ask_price != 0 and symbol.bid_price != 0 for symbol in self.symbols
        ):
            balance = self.base_quantity
            starting_balance = 0
            fees = 0
            self.qty_issue = False
            limit_prices = []
            target_balances = []
            for index, (symbol, side) in enumerate(zip(self.symbols, self.sides)):
                if side == "BUY":
                    balance = round_step_size(
                        balance / symbol.ask_price, symbol.stepSize
                    )
                    if balance > symbol.ask_qty:
                        self.qty_issue = True
                    limit_prices.append(symbol.ask_price)
                    if index == 0:
                        starting_balance = balance * symbol.ask_price
                else:
                    if balance > symbol.bid_qty:
                        self.qty_issue = True
                    balance = (
                        round_step_size(balance, symbol.stepSize) * symbol.bid_price
                    )
                    limit_prices.append(symbol.bid_price)
                    if index == 0:
                        starting_balance = balance / symbol.bid_price
                target_balances.append(balance)
                fees += self.base_quantity * symbol.trading_fee[1] * 0.75

            balance = balance - fees
            self.profit = ((balance - starting_balance) / starting_balance) * 100
            if self.profit > 0:
                limit_prices = tuple(limit_prices)
                if self.opportunities:
                    to_delete = [
                        prices
                        for prices, opp in self.opportunities.items()
                        if await opp.update_profit()
                    ]
                    for prices in to_delete:
                        del self.opportunities[prices]

                if not self.qty_issue and limit_prices not in self.opportunities:
                    self.opportunities[limit_prices] = Opportunity(
                        self.ta_instance,
                        self,
                        limit_prices,
                        target_balances,
                        self.profit,
                    )

            else:
                if self.opportunities:
                    for opp in self.opportunities.values():
                        await opp.delete()
                self.opportunities = {}