from enum import Enum  

simulations = [
  {
    "address": "0x1", # any string works
    "deposit_amount": 1000000, # in USD, $1 denomination, will be split into USDT and USDC
    "deposit_after": 0, # Block to deposit from
    "withdraw_before": 0, # Block to withdraw from
    "lower_tick": 0.9996, # in USD, $1 denomination
    "upper_tick": 1.0004, # in USD, $1 denomination
    "enable_rebalance": False, # If true, tries to chase the active
    "rebalance_frequency": 0, # How many blocks to wait before rebalancing
  },
  {
    "address": "0x2", # any string works
    "deposit_amount": 1000000, # in USD, $1 denomination, will be split into USDT and USDC
    "deposit_after": 0, # Block to deposit from
    "withdraw_before": 0, # Block to withdraw from
    "lower_tick": 0.996, # in USD, $1 denomination
    "upper_tick": 1.004, # in USD, $1 denomination
    "enable_rebalance": False, # If true, tries to chase the active
    "rebalance_frequency": 0, # How many blocks to wait before rebalancing
  },
  {
    "address": "0x3", # any string works
    "deposit_amount": 1000000, # in USD, $1 denomination, will be split into USDT and USDC
    "deposit_after": 0, # Block to deposit from
    "withdraw_before": 0, # Block to withdraw from
    "lower_tick": 0.94, # in USD, $1 denomination
    "upper_tick": 1.06, # in USD, $1 denomination
    "enable_rebalance": False, # If true, tries to chase the active
    "rebalance_frequency": 0, # How many blocks to wait before rebalancing
  },
]
