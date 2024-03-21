import json


class Opportunity:

    def __init__(self, ta, chain, limit_prices, target_balances, profit):
        """
        Initializes the Opportunity instance.

        Parameters:
        - ta_instance: The instance of TriangularArbitrage associated with the opportunity.
        - chain_instance: The instance of Chain associated with the opportunity.
        - limit_prices (tuple): Tuple of limit prices for each symbol in the chain.
        - target_balances (list): List of target balances for each symbol in the chain.
        - profit (float): The starting profit percentage.
        """
        self.ta = ta
        self.chain = chain
        self.limit_prices = limit_prices
        self.target_balances = target_balances
        self.start_time = self.chain.time_stamp
        self.starting_profit = profit
        self.profit = self.starting_profit
        self.profit_trajectory = [[0, self.starting_profit]]
        self.deleted = False
        self.trades_possible = [True, True, True]

    async def update_profit(self):
        """
        Updates the profit percentage for the opportunity.
        """
        for index, (symbol, side, limit_price) in enumerate(
            zip(self.chain.symbols, self.chain.sides, self.limit_prices)
        ):
            if side == "BUY":
                if symbol.ask_price > limit_price:
                    self.trades_possible[index] = False
                else:
                    self.trades_possible[index] = True
            else:
                if symbol.bid_price < limit_price:
                    self.trades_possible[index] = False
                else:
                    self.trades_possible[index] = True

        if all(self.trades_possible):
            self.profit = self.starting_profit
        else:
            self.profit = 0

        if not self.deleted:
            if self.profit > 0 and not self.chain.qty_issue:
                self.profit_trajectory.append(
                    [self.chain.time_stamp - self.start_time, self.profit]
                )
            elif self.profit > 0 and self.chain.qty_issue:
                self.profit_trajectory.append(
                    [self.chain.time_stamp - self.start_time, 0]
                )
            else:
                await self.delete()

        return self.deleted

    async def delete(self):
        """
        Deletes the opportunity and records the profit duration.
        """
        self.deleted = True
        profit_duration = self.chain.time_stamp - self.start_time
        self.profit_trajectory.append([profit_duration, 0])

        # Serialize the profit_trajectory to a JSON string
        trajectory_json = json.dumps(self.profit_trajectory)

        self.ta.data_base_batch["duration"].append(profit_duration)
        self.ta.data_base_batch["profit"].append(self.starting_profit)
        self.ta.data_base_batch["base_currency"].append(self.chain.base_currency)
        self.ta.data_base_batch["name"].append(self.chain.name)
        self.ta.data_base_batch["trajectory"].append(trajectory_json)
