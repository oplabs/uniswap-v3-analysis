import math
from utils.const import pool_fee, usd_gas_estimate

from .data import collect, scenarios, SimulatorDataService
from rebalancer import Rebalancer
from utils.tick import find_tick_index, get_sqrt_ratio_at_tick
from utils.liquidity import get_liquidity_amounts, get_amounts_for_liquidity

ticks = {}
lp_providers = {}

last_tick = None
latest_price = None
latest_price_x96 = None
net_liquidity = 0

net_usdc_fee = 0
net_usdt_fee = 0

mint_ev_map = {}
token_id_owner_map = {}
token_id_mint_map = {}

def handle_mint_event(event):
  key = event["block_hash"] + "_" + event["transaction_hash"]
  mint_ev_map[key] = event

def update_liquidity(token_id, liquidity_change, direction=1):
  global net_liquidity
  global latest_price_x96

  event = token_id_mint_map.get(token_id)
  provider = str(token_id_owner_map.get(token_id)).lower()

  if event is None or provider is None:
    # Unknown event?
    return (0, 0)

  lower_tick = int(event["arg__tickLower"])
  upper_tick = int(event["arg__tickUpper"])
  
  total_ticks = upper_tick - lower_tick + 1

  ratio_curr = (latest_price_x96 / 2**96) if latest_price_x96 is not None else get_sqrt_ratio_at_tick(0)
  ratio_a = get_sqrt_ratio_at_tick(lower_tick)
  ratio_b = get_sqrt_ratio_at_tick(upper_tick)
  (usdc_for_liquidity, usdt_for_liquidity) = get_amounts_for_liquidity(ratio_curr, ratio_a, ratio_b, liquidity_change)

  liquidity_per_tick = liquidity_change / total_ticks
  # usdc_per_tick = usdc_for_liquidity / total_ticks
  # usdt_per_tick = usdt_for_liquidity / total_ticks

  net_liquidity += (liquidity_change * direction)

  lp_provider = lp_providers.get(provider, {
    "net_liquidity": 0,
    # "usdc_net": 0,
    # "usdt_net": 0,
    "usdc_profit": 0,
    "usdt_profit": 0
  })
  lp_provider["net_liquidity"] += (liquidity_change * direction)
  # lp_provider["usdc_net"] += (usdc_for_liquidity * direction)
  # lp_provider["usdt_net"] += (usdt_for_liquidity * direction)
  lp_providers[provider] = lp_provider

  for i in range(total_ticks+1):
    key = str(lower_tick + i)
    tick = ticks.get(key, {
      'liquidity': 0,
      # 'usdc': 0,
      # 'usdt': 0,
      'positions': {}
    })

    pos = tick['positions'].get(provider, {
      'liquidity': 0,
      # 'usdt': 0,
      # 'usdc': 0
    })
    pos['liquidity'] += (liquidity_per_tick * direction)
    # pos['usdc'] += (usdc_per_tick * direction)
    # pos['usdt'] += (usdt_per_tick * direction)

    tick['positions'][provider] = pos

    tick['liquidity'] += (liquidity_per_tick * direction)
    # tick['usdc'] += (usdc_per_tick * direction)
    # tick['usdc'] += (usdt_per_tick * direction)

    ticks[key] = tick

  return (usdc_for_liquidity, usdt_for_liquidity)

def increase_liquidity(token_id, liquidity_added):
  return update_liquidity(token_id, liquidity_added, 1)

def decrease_liquidity(token_id, liquidity_removed):
  return update_liquidity(token_id, liquidity_removed, -1)

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
    # 'usdc': 0,
    # 'usdt': 0,
    'positions': {}
  })

  tick_liquidity = int(tick['liquidity'])
  if tick_liquidity > 0:
    for addr in tick['positions'].keys():
      lp_provider = lp_providers.get(addr, {
        "net_liquidity": 0,
        # "usdc_net": 0,
        # "usdt_net": 0,
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

  usdc_fee = abs(amount0) * pool_fee
  usdt_fee = abs(amount1) * pool_fee
  
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

def find_token_split(max_usdc_amount, max_usdt_amount, lower_tick, upper_tick):
  global latest_price
  global latest_price_x96

  ratio_curr = latest_price_x96 / 2**96
  ratio_a = get_sqrt_ratio_at_tick(lower_tick)
  ratio_b = get_sqrt_ratio_at_tick(upper_tick)

  liquidity = get_liquidity_amounts(ratio_curr, ratio_a, ratio_b, max_usdc_amount, max_usdt_amount)

  (usdc_amount, usdt_amount) = get_amounts_for_liquidity(ratio_curr, ratio_a, ratio_b, liquidity)
  return (usdc_amount, usdt_amount, liquidity)

deposited_sims = set()
withdrawn_sims = set()
rebalancer_map = {}
sim_usdt_balances = {}
sim_usdc_balances = {}
data_service = SimulatorDataService()
def handle_sims(block_number):
  global deposited_sims
  global withdrawn_sims
  global latest_price
  global last_tick

  if latest_price is None:
    return

  data_service.set_latest_block(block_number)
  data_service.set_latest_tick(last_tick)

  handle_rebalances()

  for sim in scenarios:
    address = sim["address"].lower()
    token_id = address

    deposit_after = sim.get("deposit_after", 0)
    withdraw_before = sim.get("withdraw_before", 0)

    enable_rebalancer = sim.get("enable_rebalancer", False)
    rebalance_frequency = sim.get("rebalance_frequency", 0)
    target_tick_range = sim.get("target_tick_range", 1)

    max_usdc_amount = math.floor(sim["usdc_amount"] * 10**6)
    max_usdt_amount = math.floor(sim["usdt_amount"] * 10**6)

    lower_tick = sim["lower_tick"]
    upper_tick = sim["upper_tick"]
    lower_tick_index = find_tick_index(lower_tick)
    upper_tick_index = find_tick_index(upper_tick)

    if enable_rebalancer and address in deposited_sims and address not in withdrawn_sims:
      rebalancer = rebalancer_map[address]
      rebalancer.run()

    if address not in deposited_sims and (deposit_after == 0 or deposit_after <= block_number):
      (usdc_amount, usdt_amount, liquidity) = find_token_split(max_usdc_amount, max_usdt_amount, lower_tick_index, upper_tick_index)

      print("Adding liquidity for simulated address {}:".format(address))
      print("\tUSDC       : {}".format(usdc_amount / 10**6))
      print("\tUSDT       : {}".format(usdt_amount / 10**6))
      print("\tLiquidity  : {}".format(liquidity))
      print("\tLower tick : {} ({})".format(lower_tick_index, lower_tick))
      print("\tUpper tick : {} ({})".format(upper_tick_index, upper_tick))

      deposited_sims = deposited_sims | set([address])

      sim_usdc_balances[address] = max_usdc_amount - usdc_amount
      sim_usdt_balances[address] = max_usdt_amount - usdt_amount

      event = {
        "arg__tickLower": lower_tick_index,
        "arg__tickUpper": upper_tick_index,
      }

      token_id_mint_map[token_id] = event
      token_id_owner_map[token_id] = address.lower()

      increase_liquidity(token_id, liquidity)

      data_service.set_position_data(address, (lower_tick_index, upper_tick_index))

      rebalancer = Rebalancer(data_service, address, target_tick_range, rebalance_frequency)
      rebalancer_map[address] = rebalancer

    elif address not in withdrawn_sims and withdraw_before > 0 and withdraw_before >= block_number:
      provider = lp_providers.get(address)
      liquidity_to_remove = provider.get("net_liquidity")
      (usdc_amount, usdt_amount) = decrease_liquidity(token_id, liquidity_to_remove)
      print("Removing liquidity for simulated address {}:".format(address))
      print("\tUSDC       : {}".format(usdc_amount / 10**6))
      print("\tUSDT       : {}".format(usdt_amount / 10**6))
      print("\tLiquidity  : {}".format(liquidity_to_remove))
      print("\tLower tick : {} ({})".format(lower_tick_index, lower_tick))
      print("\tUpper tick : {} ({})".format(upper_tick_index, upper_tick))

      withdrawn_sims = withdrawn_sims | set([address])

      decrease_liquidity(token_id, liquidity)

      sim_usdc_balances[address] += usdc_amount
      sim_usdt_balances[address] += usdt_amount

rebalance_counter = {}
def handle_rebalances():
  rebalance_requests = data_service.get_rebalance_requests()
  for req in rebalance_requests:
    (address, lower_tick, upper_tick) = req
    address = address
    token_id = address
    provider = lp_providers.get(address)
    if provider is not None:
      liquidity_to_remove = provider.get("net_liquidity")
      (usdc_received, usdt_received) = decrease_liquidity(token_id, liquidity_to_remove)
      
      max_usdc = sim_usdc_balances[address] + (usdc_received * (1 - pool_fee))
      max_usdt = sim_usdt_balances[address] + (usdt_received * (1 - pool_fee))
      net_gas_estimate = usd_gas_estimate * 10**6

      if (max_usdc + max_usdt) < net_gas_estimate:
        # Lost all capital??
        sim_usdc_balances[address] = max_usdc
        sim_usdt_balances[address] = max_usdt
        data_service.pause_position(token_id)
        continue
      elif (max_usdc >= net_gas_estimate / 2) and (max_usdt >= net_gas_estimate / 2):
        max_usdc -= (net_gas_estimate / 2)
        max_usdt -= (net_gas_estimate / 2)
      elif max_usdc >= net_gas_estimate:
        max_usdc -= net_gas_estimate
      elif max_usdt >= net_gas_estimate:
        max_usdt -= net_gas_estimate
      else:
        new_bal = max_usdc + max_usdt - net_gas_estimate
        max_usdc = new_bal if max_usdc > max_usdt else 0
        max_usdt = new_bal if max_usdc <= max_usdt else 0

      sim_usdc_balances[address] = max_usdc
      sim_usdt_balances[address] = max_usdt

      event = {
        "arg__tickLower": lower_tick,
        "arg__tickUpper": upper_tick,
      }
      token_id_mint_map[token_id] = event

      ratio_curr = latest_price_x96 / 2**96
      ratio_a = get_sqrt_ratio_at_tick(lower_tick)
      ratio_b = get_sqrt_ratio_at_tick(upper_tick)

      liquidity_to_add = get_liquidity_amounts(ratio_curr, ratio_a, ratio_b, max_usdc, max_usdt)

      (usdc_added, usdt_added) = increase_liquidity(token_id, liquidity_to_add)
      sim_usdc_balances[address] -= usdc_added
      sim_usdt_balances[address] -= usdt_added

      data_service.set_position_data(address, (lower_tick, upper_tick))
      rebalance_counter[address] = (rebalance_counter.get(address, 0)) + 1

def print_profits(address, initial_usdc, initial_usdt):
  data = lp_providers.get(address.lower())

  print("\n\nBalances of {}:".format(address))
  if data is None:
    print("\tNOT FOUND")
    return

  usdc_fee = data["usdc_profit"]
  usdt_fee = data["usdt_profit"]
  usdc_bal = sim_usdc_balances[address]
  usdt_bal = sim_usdt_balances[address]
  liquidity = data["net_liquidity"]

  event = token_id_mint_map[address]
  lower_tick = event["arg__tickLower"]
  upper_tick = event["arg__tickUpper"]
  ratio_curr = (latest_price_x96 / 2**96) if latest_price_x96 is not None else get_sqrt_ratio_at_tick(0)
  ratio_a = get_sqrt_ratio_at_tick(lower_tick)
  ratio_b = get_sqrt_ratio_at_tick(upper_tick)
  (usdc_for_liquidity, usdt_for_liquidity) = get_amounts_for_liquidity(ratio_curr, ratio_a, ratio_b, liquidity)

  net_usdc = usdc_for_liquidity + usdc_fee + usdc_bal
  net_usdt = usdt_for_liquidity + usdt_fee + usdt_bal
  net_fee = usdc_fee + usdt_fee

  initial_deposit = math.floor((initial_usdc + initial_usdt) / 10**6)
  current_value = math.floor((net_usdc + net_usdt) / 10**6)
  diff = current_value - initial_deposit

  growth = math.floor(10000 * diff / initial_deposit) / 100

  print("\tGrowth: {}".format(growth))
  print("\tInitial Deposit Value: {}".format(initial_deposit))
  print("\tCurrent Deposit Value: {}".format(current_value))
  print("\tDiff in Deposit Value: {}".format(diff))
  print("\tNet Liquidity: {}".format(liquidity))
  print("\tTotal Rebalances: {}".format(rebalance_counter.get(address, 0)))
  print("\tNet Fee Earned: {}".format(net_fee / 10**6))
  print("\tNet USDC: {}".format(net_usdc / 10**6))
  print("\t\tLiquidity: {}".format(usdc_for_liquidity / 10**6))
  print("\t\tBal: {}".format(usdc_bal / 10**6))
  print("\t\tFee: {}".format(usdc_fee / 10**6))

  print("\tNet USDT: {}".format((usdt_for_liquidity + usdt_fee + usdt_bal) / 10**6))
  print("\t\tLiquidity: {}".format(usdt_for_liquidity / 10**6))
  print("\t\tBal: {}".format(usdt_bal / 10**6))
  print("\t\tFee: {}".format(usdt_fee / 10**6))

async def simulate(start_block, end_block):
  print("Found {} scenarios to simulate".format(len(scenarios)))

  data = await collect(start_block, end_block)

  total = len(data)
  processed = 0
  pct5 = math.floor(5 * total / 100)

  print("Loaded {} events, processing them now".format(total))

  for index, event in data.iterrows():
    block_number = int(event["block_number"])
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

  for sim in scenarios:
    print_profits(sim["address"], sim["usdc_amount"] * 10**6, sim["usdt_amount"] * 10**6)

  print("Done!")
