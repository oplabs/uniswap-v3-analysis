import asyncio

import os
import ctc
import pandas as pd
from pathlib import Path

from utils.const import pool, nft_manager

curr_dir = os.path.dirname(os.path.realpath(__file__))

async def _read_from_chain(start_block, end_block):
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
      nft_manager,
      event_name='IncreaseLiquidity',
      start_block=start_block,
      end_block=end_block,
    ),
    ctc.async_get_events(
      nft_manager,
      event_name='DecreaseLiquidity',
      start_block=start_block,
      end_block=end_block,
    ),
    ctc.async_get_events(
      nft_manager,
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

async def collect(start_block, end_block):
  cache_data_file = os.path.join(curr_dir, "chaindata_{}_{}.csv".format(start_block, end_block))

  cached_data = Path(cache_data_file).exists()
  data = None

  if cached_data: 
    print("Cache found, Reading data from cache...")
    data = pd.read_csv(cache_data_file)
  else:
    print("Reading data from blockchain...")
    data = await _read_from_chain(start_block, end_block)
    print("Caching loaded data...")
    data.to_csv(cache_data_file)

  print("Found {} events".format(len(data)))

  return data
