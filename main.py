import asyncio
from binance import AsyncClient
import traceback

from triangular_arbitrage import TriangularArbitrage


async def main():
    """
    Main entry point for the triangular arbitrage trading bot.

    This function initializes the Binance client, sets up the TriangularArbitrage instance,
    and runs the main task of the bot.

    Note: Modify the trading pairs and quantities in the TriangularArbitrage constructor
    based on your trading preferences.

    Example:
    triangular_arbitrage = TriangularArbitrage(
        client,
        testnet,
        [["USDT", 50]],
    )
    """

    client = None
    triangular_arbitrage = None
    testnet = False
    timeout = 24 * 60 * 60

    # Use either the testnet or actual API key and secret based on the configuration
    if testnet:
        from config_testnet import api_key, api_secret
    else:
        from config import api_key, api_secret

    try:
        # Initialize the Binance client
        client = await AsyncClient.create(api_key, api_secret, testnet=testnet)

        # Initialize the TriangularArbitrage instance
        triangular_arbitrage = TriangularArbitrage(
            client,
            testnet,
            [["USDT", 50]],
        )

        # Run the main task of the bot
        main_task = asyncio.create_task(triangular_arbitrage.run())

        await asyncio.sleep(timeout)
        print("Timeout!", flush=True)
        triangular_arbitrage.cancel_in_progress = True

        main_task.cancel()

    except asyncio.CancelledError:
        print("Main task was cancelled", flush=True)
        triangular_arbitrage.cancel_in_progress = True
        main_task.cancel()
        print("main task cancelled", flush=True)
    except Exception as e:
        print("An error occurred within the main task:", e)
        traceback.print_exc()


if __name__ == "__main__":
    # Run the main function using asyncio
    asyncio.run(main())
