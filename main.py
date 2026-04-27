import os
import asyncio
import logging
from web3 import Web3
from web3.middleware import geth_poa_middleware
from telegram import Bot

# -------------------- LOGGING --------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# -------------------- TELEGRAM --------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    raise ValueError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")

# -------------------- CONTRACT ABI --------------------
CONTRACT_ABI = [
    {
        "inputs": [],
        "name": "readyForSupplyBlock",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function"
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

# -------------------- CHAIN CONFIG --------------------
CHAINS = [
    {
        "name": "PulseChain",
        "rpc": "https://rpc.pulsechain.com",
        "contract": "0x3B1489f3ea4643b7e7B29548e2E2cFEf094BB05E",
        "poa": True
    },
    {
        "name": "Ethereum",
        "rpc": "https://ethereum-sepolia-rpc.publicnode.com",
        "contract": "0xd7eac132347d4786248d665357aae8e33e8c0ed8",
        "poa": False
    }
]

# -------------------- TELEGRAM SEND --------------------
async def send_telegram_message(bot, message):
    try:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logger.info(f"Sent: {message}")
    except Exception as e:
        logger.error(f"Telegram error: {e}")

# -------------------- INIT CHAINS --------------------
def init_chains():
    chain_states = {}
    for chain in CHAINS:
        try:
            w3 = Web3(Web3.HTTPProvider(chain["rpc"]))
            if chain.get("poa"):
                w3.middleware_onion.inject(geth_poa_middleware, layer=0)
            if not w3.is_connected():
                logger.error(f"{chain['name']} connection failed")
                continue

            checksum_address = Web3.to_checksum_address(chain["contract"])
            contract = w3.eth.contract(
                address=checksum_address,
                abi=CONTRACT_ABI
            )
            latest_block = w3.eth.get_block("latest")["number"]

            chain_states[chain["name"]] = {
                "w3": w3,
                "contract": contract,
                "last_block": latest_block,
                "last_ready": False
            }
            logger.info(f"{chain['name']} initialized at block {latest_block}")

        except Exception as e:
            logger.error(f"Failed to init {chain['name']}: {e}")
            # continue to next chain instead of returning early
            continue

    return chain_states

# -------------------- MAIN LOOP --------------------
async def monitor():
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    chain_states = init_chains()

    if not chain_states:
        logger.error("No chains initialized. Exiting.")
        return

    logger.info("Monitoring started...")

    while True:
        for name, state in chain_states.items():
            try:
                w3 = state["w3"]
                contract = state["contract"]

                # -------- READY CHECK --------
                try:
                    current_ready = contract.functions.readyForSupplyBlock().call()

                    if current_ready and not state["last_ready"]:
                        await send_telegram_message(
                            bot,
                            f"supplyBlock on {name} ready"
                        )
                        state["last_ready"] = True

                    elif not current_ready and state["last_ready"]:
                        state["last_ready"] = False

                except Exception as e:
                    logger.error(f"{name} ready() error: {e}")

                # -------- EVENT CHECK --------
                try:
                    current_block = w3.eth.get_block("latest")["number"]

                    if current_block > state["last_block"]:
                        events = contract.events.SupplyBlockMined.get_logs(
                            fromBlock=state["last_block"] + 1,
                            toBlock=current_block
                        )

                        for event in events:
                            caller = event["args"]["caller"]

                            await send_telegram_message(
                                bot,
                                f"SupplyBlock executed on {name} by {caller}"
                            )

                            state["last_ready"] = False

                        state["last_block"] = current_block

                except Exception as e:
                    logger.error(f"{name} event error: {e}")

            except Exception as e:
                logger.error(f"{name} loop error: {e}")

        await asyncio.sleep(10)

# -------------------- ENTRY --------------------
if __name__ == "__main__":
    asyncio.run(monitor())
