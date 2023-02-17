import asyncio

import ctc
from ctc import evm
from ctc.protocols import uniswap_v3_utils

import pandas as pd
import math
import sys
from pathlib import Path
from input import simulations

usdc = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
usdt = "0xdAC17F958D2ee523a2206206994597C13D831ec7"

pool = "0x3416cf6c708da44db2624d63ea0aaef7113527c6" # USDT-USDC V3

nftManager = "0xC36442b4a4522E871399CD717aBDD847Ab11FE88" # NonFungiblePositionsManager

cacheFilePath = "./chaindata.csv"

ticks = {}
lp_providers = {}

last_tick = None
latest_price = None
latest_price_x96 = None
net_liquidity = 0

fee = 0.0001 #0.01%

net_usdc_fee = 0
net_usdt_fee = 0

mint_ev_map = {}
token_id_owner_map = {}
token_id_mint_map = {}

start_block = "13609065"
end_block = "16642500"

# start_block = "16539882"
# end_block = "16539884"

async def collect():
  global start_block
  global end_block

  print("Reading data from blockchain...")

  swaps, mints, increases, decreases, transfers = await asyncio.gather(  
    ctc.async_get_events(
      pool,
      event_name='Swap',
      start_block=start_block,
      end_block=end_block,
    ),
    ctc.async_get_events(
      pool,
      event_name='Mint',
      start_block=start_block,
      end_block=end_block,
    ),
    ctc.async_get_events(
      nftManager,
      event_name='IncreaseLiquidity',
      start_block=start_block,
      end_block=end_block,
    ),
    ctc.async_get_events(
      nftManager,
      event_name='DecreaseLiquidity',
      start_block=start_block,
      end_block=end_block,
    ),
    ctc.async_get_events(
      nftManager,
      event_name='Transfer',
      start_block=start_block,
      end_block=end_block,
    ),
  )

  swaps = pd.DataFrame(swaps.to_records())
  mints = pd.DataFrame(mints.to_records())
  increases = pd.DataFrame(increases.to_records())
  decreases = pd.DataFrame(decreases.to_records())
  transfers = pd.DataFrame(transfers.to_records())
  transfers = transfers[transfers["arg__from"] == "0x0000000000000000000000000000000000000000"]

  return pd.concat(
    [swaps, mints, increases, decreases, transfers]
  ).sort_values(
    by=['block_number', 'transaction_index', 'log_index'],
    ascending=True,
    ignore_index=True,
  )

def handle_mint_event(event):
  key = event["block_hash"] + "_" + event["transaction_hash"]
  mint_ev_map[key] = event

def update_liquidity(token_id, liquidity_change, direction=1):
  global net_liquidity

  event = token_id_mint_map.get(token_id)
  provider = str(token_id_owner_map.get(token_id)).lower()

  if event is None or provider is None:
    # Unknown event?
    return

  lower_tick = int(event["arg__tickLower"])
  upper_tick = int(event["arg__tickUpper"])

  total_ticks = upper_tick - lower_tick + 1
  liquidity_per_tick = liquidity_change / total_ticks

  net_liquidity += (liquidity_change * direction)

  lp_provider = lp_providers.get(provider, {
    "net_liquidity": 0,
    "usdc_profit": 0,
    "usdt_profit": 0
  })
  lp_provider["net_liquidity"] += (liquidity_change * direction)
  lp_providers[provider] = lp_provider

  for i in range(total_ticks+1):
    key = str(lower_tick + i)
    tick = ticks.get(key, {
      'liquidity': 0,
      'positions': {}
    })

    pos = tick['positions'].get(provider, {
      'liquidity': 0
    })
    pos['liquidity'] += (liquidity_per_tick * direction)
    tick['positions'][provider] = pos

    tick['liquidity'] += (liquidity_per_tick * direction)

    ticks[key] = tick

def increase_liquidity(token_id, liquidity_added):
  update_liquidity(token_id, liquidity_added, 1)

def decrease_liquidity(token_id, liquidity_removed):
  update_liquidity(token_id, liquidity_removed, -1)

def handle_transfer_event(transfer_event):
  block_hash = transfer_event["block_hash"]
  transaction_hash = transfer_event["transaction_hash"]

  key = block_hash + "_" + transaction_hash
  event = mint_ev_map.get(key)

  if event is None:
    # Probably not from USDT<>USDC pool
    return

  provider = transfer_event["arg__to"].lower()
  token_id = str(transfer_event["arg__tokenId"])

  token_id_owner_map[token_id] = provider
  token_id_mint_map[token_id] = event
  del mint_ev_map[key]

def handle_burn_event(event):
  return

def distribute_fee_to_tick(tick_index, usdc_fee, usdt_fee):
  tick = ticks.get(str(tick_index), {
    'liquidity': 0,
    'positions': {}
  })

  tick_liquidity = int(tick['liquidity'])
  if tick_liquidity > 0:
    for addr in tick['positions'].keys():
      lp_provider = lp_providers.get(addr, {
        "net_liquidity": 0,
        "usdc_profit": 0,
        "usdt_profit": 0
      })

      provided_liquidity = int(tick['positions'][addr]['liquidity'])
      lp_provider["usdc_profit"] += math.floor(usdc_fee * provided_liquidity / tick_liquidity)
      lp_provider["usdt_profit"] += math.floor(usdt_fee * provided_liquidity / tick_liquidity)

      lp_providers[addr] = lp_provider


def handle_swap_event(event):
  global net_liquidity
  global net_usdc_fee
  global net_usdt_fee
  global last_tick
  global latest_price_x96
  global latest_price

  curr_tick = int(event["arg__tick"])
  liquidity = int(event["arg__liquidity"])
  sqrtPriceX96 = int(event["arg__sqrtPriceX96"])
  amount0 = int(event["arg__amount0"])
  amount1 = int(event["arg__amount1"])

  first_swap = last_tick is None 
  is_multi_tick = last_tick != curr_tick and not first_swap

  usdc_fee = abs(amount0) * fee
  usdt_fee = abs(amount1) * fee
  
  net_usdc_fee += usdc_fee
  net_usdt_fee += usdt_fee

  if not is_multi_tick:
    distribute_fee_to_tick(curr_tick, usdc_fee, usdt_fee)

  else:
    direction = last_tick < curr_tick # True for forward

    total_ticks = max(last_tick, curr_tick) - min(last_tick, curr_tick) + 1
    usdc_fee_per_tick = usdc_fee / total_ticks
    usdt_fee_per_tick = usdt_fee / total_ticks

    for tick in range(min(last_tick, curr_tick), max(last_tick, curr_tick) + 1):
      distribute_fee_to_tick(str(tick), usdc_fee_per_tick, usdt_fee_per_tick)
        
  last_tick = curr_tick
  latest_price_x96 = sqrtPriceX96
  latest_price = math.floor(10**6 * (sqrtPriceX96 / 2**96)**2) / 10**6

def handle_increase_event(event):
  token_id = str(event["arg__tokenId"])
  liquidity_added = int(event['arg__liquidity'])
  increase_liquidity(token_id, liquidity_added)

def handle_decrease_event(event):
  token_id = str(event["arg__tokenId"])
  liquidity_removed = int(event['arg__liquidity'])
  decrease_liquidity(token_id, liquidity_removed)

def find_tick_index(price):
  return round(math.log(price, 1.0001))

def find_token_split(deposit_amount):
  global latest_price
  global latest_price_x96

  if latest_price is None:
    # First event?
    usdc_amount = math.floor(deposit_amount / 2)
    usdt_amount = usdc_amount
    liquidity = math.floor(10**6 * math.sqrt(usdt_amount * usdc_amount)) # Same as sqrt(10**6 * x * 10**6 * y)
    return (usdc_amount, usdt_amount, liquidity)


  usdc_amount = math.floor(10**6 * (latest_price * deposit_amount/2))
  usdt_amount = (deposit_amount * 10**6) - usdc_amount

  liquidity = math.floor(math.sqrt(usdc_amount * usdt_amount))

  return (usdc_amount, usdt_amount, liquidity)

def print_profits(address):
  data = lp_providers.get(address.lower())

  print("Balances of {}:".format(address))
  if data is None:
    print("\tNOT FOUND")
    return

  print("\tNet Liquidity: {}".format(data["net_liquidity"]))
  print("\tUSDC Fee: {}".format(data["usdc_profit"] / 10**6))
  print("\tUSDT Fee: {}".format(data["usdt_profit"] / 10**6))

deposited_sims = set()
withdrawn_sims = set()
def handle_sims(block_number):
  global deposited_sims
  global withdrawn_sims
  global latest_price

  if latest_price is None:
    return

  for sim in simulations:
    address = sim["address"].lower()
    token_id = "simtoken_" + address
    deposit_after = sim["deposit_after"]
    withdraw_before = sim["withdraw_before"]
    deposit_amount = sim["deposit_amount"]
    lower_tick = sim["lower_tick"]
    upper_tick = sim["upper_tick"]

    if address not in deposited_sims and (deposit_after == 0 or deposit_after >= block_number):
      (usdc_amount, usdt_amount, liquidity) = find_token_split(deposit_amount)

      print("Adding liquidity for simulated address {}:".format(address))
      print("\tUSDC       : {}".format(usdc_amount / 10**6))
      print("\tUSDT       : {}".format(usdc_amount / 10**6))
      print("\tLiquidity  : {}".format(liquidity))
      print("\tLower tick : {} ({})".format(find_tick_index(lower_tick), lower_tick))
      print("\tUpper tick : {} ({})".format(find_tick_index(upper_tick), upper_tick))

      deposited_sims = deposited_sims | set([address])

      event = {
        "arg__tickLower": find_tick_index(lower_tick),
        "arg__tickUpper": find_tick_index(upper_tick),
      }

      token_id_mint_map[token_id] = event
      token_id_owner_map[token_id] = address.lower()

      increase_liquidity(token_id, liquidity)

    elif address not in withdrawn_sims and withdraw_before > 0 and withdraw_before <= block_number:
      (usdc_amount, usdt_amount, liquidity) = find_token_split(deposit_amount)

      print("Removing liquidity for simulated address {}:".format(address))
      print("\tUSDC       : {}".format(usdc_amount / 10**6))
      print("\tUSDT       : {}".format(usdc_amount / 10**6))
      print("\tLiquidity  : {}".format(liquidity))
      print("\tLower tick : {} ({})".format(find_tick_index(lower_tick), lower_tick))
      print("\tUpper tick : {} ({})".format(find_tick_index(upper_tick), upper_tick))

      withdrawn_sims = withdrawn_sims | set([address])

      decrease_liquidity(token_id, liquidity)
      

async def main():
  print("Found {} scenarios to simulate".format(len(simulations)))

  cached_data = Path(cacheFilePath).exists()

  if cached_data: print("Reading blockchain data from cache...")
  data = pd.read_csv(cacheFilePath) if cached_data else (await collect())

  if not cached_data:
    print("Caching loaded data...")
    data.to_csv(cacheFilePath)


  total = len(data)
  processed = 0
  pct5 = math.floor(5 * total / 100)

  print("Loaded {} events, processing them now".format(total))

  for index, event in data.iterrows():
    block_number = event["block_number"]
    event_name = event["event_name"]
    
    handle_sims(block_number)

    if event_name == "Mint":
      handle_mint_event(event)
    elif event_name == "Transfer":
      handle_transfer_event(event)
    elif event_name == "Burn":
      handle_burn_event(event)
    elif event_name == "Swap":
      handle_swap_event(event)
    elif event_name == "IncreaseLiquidity":
      handle_increase_event(event)
    elif event_name == "DecreaseLiquidity":
      handle_decrease_event(event)

    processed += 1

    if processed % pct5 == 0:
      print("Processed {} events".format(str(math.floor(5 * processed / pct5)) + "%"))
      # break

  for sim in simulations:
    print_profits(sim["address"])

  print_profits("0x58890A9cB27586E83Cb51d2d26bbE18a1a647245")

  print("-------------------")
  print("Done!")

asyncio.run(main())
