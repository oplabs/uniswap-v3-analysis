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

block_tx_map = {}
token_id_mint_map = {}

last_mint = {}

async def collect():
  swaps, mints, burns, increases, decreases = await asyncio.gather(  
    ctc.async_get_events(
      pool,
      event_name='Swap',
      end_block='16642500',
    ),
    ctc.async_get_events(
      pool,
      event_name='Mint',
      end_block='16642500',
    ),
    ctc.async_get_events(
      pool,
      event_name='Burn',
      end_block='16642500',
    ),
    ctc.async_get_events(
      nftManager,
      event_name='IncreaseLiquidity',
      end_block='16642500',
    ),
    ctc.async_get_events(
      nftManager,
      event_name='DecreaseLiquidity',
      end_block='16642500',
    ),
  )

  swaps = pd.DataFrame(swaps.to_records())
  mints = pd.DataFrame(mints.to_records())
  burns = pd.DataFrame(burns.to_records())
  increases = pd.DataFrame(increases.to_records())
  decreases = pd.DataFrame(decreases.to_records())

  return pd.concat(
    [swaps, mints, burns, increases, decreases]
  ).sort_values(
    by=['block_number', 'transaction_index', 'log_index'],
    ascending=True,
    ignore_index=True,
  )

def handle_mint_event(event):
  global net_liquidity
  lower_tick = int(event["arg__tickLower"])
  upper_tick = int(event["arg__tickUpper"])
  liquidity_added = event["arg__amount"]
  owner = event["arg__owner"]
  block_number = event["block_number"]
  transaction_hash = event["transaction_hash"]

  total_ticks = upper_tick - lower_tick + 1
  liquidity_per_tick = liquidity_added / total_ticks

  net_liquidity += liquidity_added

  for i in range(total_ticks+1):
    key = str(lower_tick + i)
    tick = ticks.get(key, {
      'liquidity': 0,
      'positions': {}
    })

    pos = tick['positions'].get(owner, {
      'liquidity': 0
    })
    pos['liquidity'] += liquidity_per_tick
    tick['positions'][owner] = pos

    tick['liquidity'] += liquidity_per_tick

    ticks[key] = tick

  mkey_prefix = str(block_number) + "_" + str(transaction_hash)
  block_tx_map[mkey_prefix + "_last_mint"] = event
  token_id = block_tx_map.get(mkey_prefix + "_token_id")
  if token_id is not None and token_id_mint_map.get(token_id) is None:
    token_id_mint_map[token_id] = event

  return

def handle_burn_event(event):
  global net_liquidity

  lower_tick = int(event["arg__tickLower"])
  upper_tick = int(event["arg__tickUpper"])
  liquidity_removed = event["arg__amount"]
  owner = event["arg__owner"]

  total_ticks = upper_tick - lower_tick + 1
  liquidity_per_tick = liquidity_removed / total_ticks

  net_liquidity -= liquidity_removed

  for i in range(total_ticks+1):
    key = str(lower_tick + i)
    tick = ticks.get(key, {
      'liquidity': 0,
      'positions': {}
    })

    pos = tick['positions'].get(owner, {
      'liquidity': 0
    })
    pos['liquidity'] -= liquidity_per_tick
    tick['positions'][owner] = pos

    tick['liquidity'] -= liquidity_per_tick

    ticks[key] = tick

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

    # mid_tick_liquidity = 0

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
      # mid_tick_liquidity += tick['liquidity']

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
  block_number = event["block_number"]
  transaction_hash = event["transaction_hash"]

  token_key = str(block_number) + "_" + str(transaction_hash) + "_token_id"
  block_tx_map[token_key] = token_id
  mint_event = token_id_mint_map.get(token_id)

  mkey = str(block_number) + "_" + str(transaction_hash) + "_last_mint"
  if block_tx_map.get(mkey) is None:
    # IncreaseLiquidity also fires with Mints, ignore if already processed
    return

  if mint_event is None:
    return

  mint_event['arg__amount'] = event['arg__liquidity']

  handle_mint_event(mint_eventTrue)

def handle_decrease_event(event):
  token_id = str(event["arg__tokenId"])

  mint_event = token_id_mint_map.get(token_id)

  if mint_event is None:


  mint_event['arg__amount'] = event['arg__liquidity']

  handle_burn_event(mint_event)

async def main():
  data = await collect()

  total = len(data)
  processed = 0
  pct5 = math.floor(5 * total / 100)

  print("Loaded {} events, processing them now".format(total))

  print(data.head())

  for index, event in data.iterrows():
    if event["event_name"] == "Mint":
      handle_mint_event(event)
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

  print("-------------------")
  print("Done!")

asyncio.run(main())
