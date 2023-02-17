import asyncio

import ctc
from ctc import evm
from ctc.protocols import uniswap_v3_utils

import pandas as pd
import math
import sys

usdc = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
usdt = "0xdAC17F958D2ee523a2206206994597C13D831ec7"

pool = "0x3416cf6c708da44db2624d63ea0aaef7113527c6" # USDT-USDC V3

nftManager = "0xC36442b4a4522E871399CD717aBDD847Ab11FE88" # NonFungiblePositionsManager

ticks = {}
lp_providers = {}

last_tick = None
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
  swaps, mints, burns, increases, decreases, transfers = await asyncio.gather(  
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
      pool,
      event_name='Burn',
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
  burns = pd.DataFrame(burns.to_records())
  increases = pd.DataFrame(increases.to_records())
  decreases = pd.DataFrame(decreases.to_records())
  transfers = pd.DataFrame(transfers.to_records())
  transfers = transfers[transfers["arg__from"] == "0x0000000000000000000000000000000000000000"]

  return pd.concat(
    [swaps, mints, burns, increases, decreases, transfers]
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

def handle_swap_event(event):
  global net_liquidity
  global net_usdc_fee
  global net_usdt_fee
  global last_tick
  global fee

  curr_tick = int(event["arg__tick"])
  liquidity = event["arg__liquidity"]
  sqrtPriceX96 = event["arg__sqrtPriceX96"]
  amount0 = int(event["arg__amount0"])
  amount1 = int(event["arg__amount1"])

  first_swap = last_tick is None 
  is_multi_tick = last_tick != curr_tick and not first_swap

  usdc_fee = amount0 * fee
  usdt_fee = amount1 * fee
  
  net_usdc_fee += usdc_fee
  net_usdt_fee += usdt_fee

  if not is_multi_tick:
    tick = ticks.get(str(curr_tick), {
      'liquidity': 0,
      'positions': {}
    })

    if tick["liquidity"] > 0:
      for addr in tick['positions'].keys():
        provided_liquidity = tick['positions'][addr]['liquidity']
        lp_provider = lp_providers.get(addr, {
          "usdc_profit": 0,
          "usdt_profit": 0
        })

        lp_provider["usdc_profit"] += (usdc_fee * provided_liquidity / tick["liquidity"])
        lp_provider["usdt_profit"] += (usdt_fee * provided_liquidity / tick["liquidity"])

        lp_providers[addr] = lp_provider

  else:
    direction = last_tick < curr_tick # True for forward

    total_ticks = max(last_tick, curr_tick) - min(last_tick, curr_tick) + 1
    usdc_fee_per_tick = usdc_fee / total_ticks
    usdt_fee_per_tick = usdt_fee / total_ticks

    for tick in range(min(last_tick, curr_tick), max(last_tick, curr_tick) + 1):
      key = str(tick)
      tick = ticks.get(key, {
        'liquidity': 0,
        'positions': {}
      })

      if tick['liquidity'] <= 0:
        continue

      for addr in tick['positions'].keys():
        provided_liquidity = tick['positions'][addr]['liquidity']
        lp_provider = lp_providers.get(addr, {
          "usdc_profit": 0,
          "usdt_profit": 0
        })

        lp_provider["usdc_profit"] += (usdc_fee_per_tick * provided_liquidity / tick["liquidity"])
        lp_provider["usdt_profit"] += (usdt_fee_per_tick * provided_liquidity / tick["liquidity"])

      lp_providers[addr] = lp_provider
        
  if last_tick != curr_tick:
    # TODO: handle simulations here
    last_tick = curr_tick
  return

def handle_increase_event(event):
  token_id = str(event["arg__tokenId"])
  liquidity_added = event['arg__liquidity']
  increase_liquidity(token_id, liquidity_added)

def handle_decrease_event(event):
  token_id = str(event["arg__tokenId"])
  liquidity_removed = event['arg__liquidity']
  decrease_liquidity(token_id, liquidity_removed)

async def main():
  data = await collect()

  total = len(data)
  processed = 0
  pct5 = math.floor(5 * total / 100)

  print("Loaded {} events, processing them now".format(total))

  mint_map = {}

  for index, event in data.iterrows():
    if event["event_name"] == "Mint":
      handle_mint_event(event)
    elif event["event_name"] == "Transfer":
      handle_transfer_event(event)
    elif event["event_name"] == "Burn":
      handle_burn_event(event)
    elif event["event_name"] == "Swap":
      handle_swap_event(event)
    elif event["event_name"] == "IncreaseLiquidity":
      handle_increase_event(event)
    elif event["event_name"] == "DecreaseLiquidity":
      handle_decrease_event(event)

    processed += 1

    if processed % pct5 == 0:
      print("Processed {} events".format(str(math.floor(5 * processed / pct5)) + "%"))

    # if (processed / pct5) >= 2:
    #   break
    #   # sys.exit(1)

  print(lp_providers.get("0x58890A9cB27586E83Cb51d2d26bbE18a1a647245"))
  print(lp_providers.get("0x58890A9cB27586E83Cb51d2d26bbE18a1a647245".lower()))

  print("-------------------")
  print("Done!")

asyncio.run(main())
