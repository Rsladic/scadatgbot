import asyncio
from web3 import Web3
from web3.middleware import geth_poa_middleware
from telegram import Bot
import json
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN = "7783890337:AAHAX7bHTKtMR8T3hIYKTNTj-f8lJBNL6XU"  # Replace with your bot token
TELEGRAM_CHAT_ID = "-1002696820701"     # Replace with your group chat ID

# Blockchain Configuration
RPC_URL = "rpc.pulsechain.com"  # Replace with PulseChain RPC URL (e.g., Infura, Alchemy, or public node)
CONTRACT_ADDRESS = "0x563A4c367900e13Fe18659126458DBb200F9A4ba"  # Replace with your deployed SCADAManager contract address

# SCADAManager Contract ABI (trimmed to include only the events we need)
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

def handle_ready_for_supply_block(event):
    """Handle ReadyForSupplyBlock event."""
    ready = event['args']['ready']
    extra_lp = event['args']['extraLP']
    initial_lp = event['args']['initialLP']
    threshold_bps = event['args']['thresholdBps']
    
    message = (
        f"🚨 ReadyForSupplyBlock Event Emitted!\n"
        f"Ready: {ready}\n"
        f"Extra LP: {Web3.from_wei(extra_lp, 'ether')} LP\n"
        f"Initial LP: {Web3.from_wei(initial_lp, 'ether')} LP\n"
        f"Threshold (bps): {threshold_bps}"
    )
    return message

def handle_supply_block_mined(event):
    """Handle SupplyBlockMined event."""
    lp_removed = event['args']['lpRemoved']
    amount_scada = event['args']['amountSCADA']
    amount_wpls = event['args']['amountWPLS']
    scada_burned = event['args']['scadaBurned']
    share_pool_reward = event['args']['sharePoolReward']
    caller_reward = event['args']['callerReward']
    caller = event['args']['caller']
    
    message = (
        f"🎉 SupplyBlockMined Event Emitted!\n"
        f"LP Removed: {Web3.from_wei(lp_removed, 'ether')} LP\n"
        f"SCADA Amount: {Web3.from_wei(amount_scada, 'ether')} SCADA\n"
        f"WPLS Amount: {Web3.from_wei(amount_wpls, 'ether')} WPLS\n"
        f"SCADA Burned: {Web3.from_wei(scada_burned, 'ether')} SCADA\n"
        f"Share Pool Reward: {Web3.from_wei(share_pool_reward, 'ether')} SCADA\n"
        f"Caller Reward: {Web3.from_wei(caller_reward, 'ether')} SCADA\n"
        f"Caller: {caller}"
    )
    return message

async def main():
    """Main function to set up Web3 and Telegram bot."""
    # Initialize Web3
    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    
    # Add PoA middleware for PulseChain compatibility
    w3.middleware_onion.inject(geth_poa_middleware, layer=0)
    
    if not w3.is_connected():
        logger.error("Failed to connect to PulseChain node")
        return
    
    logger.info("Connected to PulseChain node")
    
    # Initialize contract
    contract = w3.eth.contract(address=CONTRACT_ADDRESS, abi=CONTRACT_ABI)
    
    # Initialize Telegram bot
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    
    # Set up event filters
    ready_filter = contract.events.ReadyForSupplyBlock.create_filter(fromBlock='latest')
    supply_block_filter = contract.events.SupplyBlockMined.create_filter(fromBlock='latest')
    
    logger.info("Starting event listeners...")
    
    while True:
        try:
            # Check for ReadyForSupplyBlock events
            for event in ready_filter.get_new_entries():
                message = handle_ready_for_supply_block(event)
                await send_telegram_message(bot, TELEGRAM_CHAT_ID, message)
            
            # Check for SupplyBlockMined events
            for event in supply_block_filter.get_new_entries():
                message = handle_supply_block_mined(event)
                await send_telegram_message(bot, TELEGRAM_CHAT_ID, message)
            
            # Sleep to avoid overwhelming the node
            await asyncio.sleep(10)
            
        except Exception as e:
            logger.error(f"Error in event loop: {e}")
            await asyncio.sleep(10)  # Wait before retrying
    
if __name__ == "__main__":
    asyncio.run(main())