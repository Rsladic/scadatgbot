import asyncio
from web3 import Web3
from web3.middleware import geth_poa_middleware
from telegram import Bot
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN = "7783890337:AAHAX7bHTKtMR8T3hIYKTNTj-f8lJBNL6XU"  # Replace with your bot token
TELEGRAM_CHAT_ID = "-1002696820701"     # Replace with your group chat ID

# Blockchain Configuration
RPC_URL = "https://rpc.pulsechain.com"  # Replace with PulseChain RPC URL
CONTRACT_ADDRESS = "0x563A4c367900e13Fe18659126458DBb200F9A4ba"  # Replace with your SCADAManager address

# Contract ABI
CONTRACT_ABI = [
    {
        "anonymous": False,
        "inputs": [
            {"indexed": False, "name": "ready", "type": "bool"},
            {"indexed": False, "name": "extraLP", "type": "uint256"},
            {"indexed": False, "name": "initialLP", "type": "uint256"},
            {"indexed": False, "name": "thresholdBps", "type": "uint256"}
        ],
        "name": "ReadyForSupplyBlock",
        "type": "event"
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": False, "name": "lpRemoved", "type": "uint256"},
            {"indexed": False, "name": "amountSCADA", "type": "uint256"},
            {"indexed": False, "name": "amountWPLS", "type": "uint256"},
            {"indexed": False, "name": "scadaBurned", "type": "uint256"},
            {"indexed": False, "name": "sharePoolReward", "type": "uint256"},
            {"indexed": False, "name": "callerReward", "type": "uint256"},
            {"indexed": True, "name": "caller", "type": "address"}
        ],
        "name": "SupplyBlockMined",
        "type": "event"
    }
]

async def send_telegram_message(bot, chat_id, message):
    """Send a message to the Telegram group."""
    try:
        await bot.send_message(chat_id=chat_id, text=message)
        logger.info(f"Sent Telegram message: {message}")
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")

def handle_ready_for_supply_block(event, last_notified_extra_lp, contract, w3):
    """Handle ReadyForSupplyBlock event, notify only when ready is true and extraLP crosses threshold."""
    ready = event['args']['ready']
    extra_lp = event['args']['extraLP']
    initial_lp = event['args']['initialLP']
    threshold_bps = event['args']['thresholdBps']
    
    # Calculate threshold
    threshold = (initial_lp * threshold_bps) // 10_000
    
    # Notify only if ready is true and extraLP has significantly increased
    if ready and extra_lp >= threshold and (last_notified_extra_lp == 0 or extra_lp >= last_notified_extra_lp + threshold // 10):
        # Verify current state
        try:
            current_ready = contract.functions.readyForSupplyBlock().call()
            if current_ready:
                return "supplyBlock function ready", extra_lp
        except Exception as e:
            logger.error(f"Error calling readyForSupplyBlock: {e}")
    return None, extra_lp

def handle_supply_block_mined(event):
    """Handle SupplyBlockMined event."""
    caller = event['args']['caller']
    return f"SupplyBlock executed by {caller}"

async def main():
    """Main function to set up Web3 and Telegram bot."""
    # Initialize Web3
    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    
    # Add PoA middleware for PulseChain
    w3.middleware_onion.inject(geth_poa_middleware, layer=0)
    
    if not w3.is_connected():
        logger.error("Failed to connect to PulseChain node")
        return
    
    logger.info("Connected to PulseChain node")
    
    # Initialize contract
    contract = w3.eth.contract(address=CONTRACT_ADDRESS, abi=CONTRACT_ABI)
    
    # Initialize Telegram bot
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    
    # Track the last block processed and last notified extraLP
    last_block = w3.eth.get_block('latest')['number']
    last_notified_extra_lp = 0  # Track last extraLP for which we sent a notification
    
    logger.info("Starting event polling...")
    
    while True:
        try:
            # Get the latest block
            current_block = w3.eth.get_block('latest')['number']
            
            # Poll for events in the block range
            if current_block > last_block:
                # ReadyForSupplyBlock events
                ready_events = contract.events.ReadyForSupplyBlock.get_logs(
                    fromBlock=last_block + 1,
                    toBlock=current_block
                )
                for event in ready_events:
                    message, new_extra_lp = handle_ready_for_supply_block(event, last_notified_extra_lp, contract, w3)
                    if message:
                        await send_telegram_message(bot, TELEGRAM_CHAT_ID, message)
                        last_notified_extra_lp = new_extra_lp
                
                # SupplyBlockMined events
                supply_events = contract.events.SupplyBlockMined.get_logs(
                    fromBlock=last_block + 1,
                    toBlock=current_block
                )
                for event in supply_events:
                    message = handle_supply_block_mined(event)
                    await send_telegram_message(bot, TELEGRAM_CHAT_ID, message)
                    last_notified_extra_lp = 0  # Reset after supplyBlock resets extraLP
                
                last_block = current_block
            
            # Sleep to avoid overwhelming the node
            await asyncio.sleep(10)
            
        except Exception as e:
            logger.error(f"Error in polling loop: {e}")
            await asyncio.sleep(10)  # Wait before retrying
    
if __name__ == "__main__":
    asyncio.run(main())
