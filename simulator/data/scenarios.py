scenarios = [
  {
    "address": "0xr1", # any string works
    "usdc_amount": 500000, # USDC to deposit, in dollar denomination
    "usdt_amount": 500000, # USDT to deposit, in dollar denomination
    "deposit_after": 14236000, # Block to deposit from
    "withdraw_before": 0, # Block to withdraw from
    "lower_tick": 0.9996, # in USD, $1 denomination
    "upper_tick": 1.0004, # in USD, $1 denomination
    "enable_rebalancer": True, # If true, tries to chase the active
    "rebalance_frequency": 0, # How many blocks to wait before rebalancing
    "target_tick_range": 1,
  },
  {
    "address": "0xr2", # any string works
    "usdc_amount": 500000, # USDC to deposit, in dollar denomination
    "usdt_amount": 500000, # USDT to deposit, in dollar denomination
    "deposit_after": 14236000, # Block to deposit from
    "withdraw_before": 0, # Block to withdraw from
    "lower_tick": 0.9996, # in USD, $1 denomination
    "upper_tick": 1.0004, # in USD, $1 denomination
    "enable_rebalancer": True, # If true, tries to chase the active
    "rebalance_frequency": 0, # How many blocks to wait before rebalancing
    "target_tick_range": 10,
  },
  {
    "address": "0xr3", # any string works
    "usdc_amount": 500000, # USDC to deposit, in dollar denomination
    "usdt_amount": 500000, # USDT to deposit, in dollar denomination
    "deposit_after": 14236000, # Block to deposit from
    "withdraw_before": 0, # Block to withdraw from
    "lower_tick": 0.9996, # in USD, $1 denomination
    "upper_tick": 1.0004, # in USD, $1 denomination
    "enable_rebalancer": True, # If true, tries to chase the active
    "rebalance_frequency": 0, # How many blocks to wait before rebalancing
    "target_tick_range": 100,
  },
  {
    "address": "0xf1", # any string works
    "usdc_amount": 500000, # USDC to deposit, in dollar denomination
    "usdt_amount": 500000, # USDT to deposit, in dollar denomination
    "deposit_after": 14236000, # Block to deposit from
    "withdraw_before": 0, # Block to withdraw from
    "lower_tick": 0.9996, # in USD, $1 denomination
    "upper_tick": 1.0004, # in USD, $1 denomination
  },
  {
    "address": "0xf2", # any string works
    "usdc_amount": 500000, # USDC to deposit, in dollar denomination
    "usdt_amount": 500000, # USDT to deposit, in dollar denomination
    "deposit_after": 14236000, # Block to deposit from
    "withdraw_before": 0, # Block to withdraw from
    "lower_tick": 0.996, # in USD, $1 denomination
    "upper_tick": 1.004, # in USD, $1 denomination
  },
  {
    "address": "0xf3", # any string works
    "usdc_amount": 500000, # USDC to deposit, in dollar denomination
    "usdt_amount": 500000, # USDT to deposit, in dollar denomination
    "deposit_after": 14236000, # Block to deposit from
    "withdraw_before": 0, # Block to withdraw from
    "lower_tick": 0.96, # in USD, $1 denomination
    "upper_tick": 1.04, # in USD, $1 denomination
  },
  {
    "address": "0xf4", # any string works
    "usdc_amount": 500000, # USDC to deposit, in dollar denomination
    "usdt_amount": 500000, # USDT to deposit, in dollar denomination
    "deposit_after": 14236000, # Block to deposit from
    "withdraw_before": 0, # Block to withdraw from
    "lower_tick": 0.99, # in USD, $1 denomination
    "upper_tick": 1.01, # in USD, $1 denomination
  },
]
