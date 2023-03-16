import math
import copy
from decimal import Decimal
from utils.const import pool_fee, usd_gas_estimate
import pickle
import ujson
from matplotlib import pyplot as plt

from .data import collect, scenarios, SimulatorDataService
from .data.rpc import blockNumberListToTimestamp
from rebalancer import Rebalancer, CustomRebalancer
from utils.tick import find_tick_index, get_sqrt_ratio_at_tick
from utils.liquidity import get_liquidity_amounts, get_amounts_for_liquidity
from cli_tables.cli_tables import *

#### Global vars (Snapshot-able) ####
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

amount_swapped = {
  'within_tick': 0,
  'accross_ticks': 0
}

deposited_sims = set()
withdrawn_sims = set()
rebalancer_map = {}
sim_usdt_balances = {}
sim_usdc_balances = {}

data_service = SimulatorDataService()
rebalance_counter = {}

# these are used just to figure out possible balance changes `handle_simulation` function
# might have made
sim_balances_temp = {}
# first & last block of scenario with balance - for APR calculation
sim_balance_ranges = {}
balance_changes = {
  'USDT': {},
  'USDC': {}
}
#### end of Snapshot-able Global vars ####

#### NON Snapshot-able Global vars ####
deposit_after = 0
snapshot = {}
prewarm_done = False

table_data = []
apy_table_data = []
usdc_table_data = []
usdt_table_data = []

serialize_engine = pickle
#serialize_engine = ujson

# simulation earnings broken down by block ranges
sim_per_block_data = {}

# saves a snapshot of the global state
def save_snapshot(block_number):
  global snapshot
  snapshot = {
    'ticks': serialize_engine.dumps(ticks, -1),
    'lp_providers': serialize_engine.dumps(lp_providers, -1),
    'last_tick': last_tick,
    'latest_price': latest_price,
    'latest_price_x96': latest_price_x96,
    'net_liquidity': net_liquidity,
    'net_usdc_fee': net_usdc_fee,
    'net_usdt_fee': net_usdt_fee,
    'mint_ev_map': serialize_engine.dumps(mint_ev_map, -1),
    'token_id_owner_map': serialize_engine.dumps(token_id_owner_map, -1),
    'token_id_mint_map': serialize_engine.dumps(token_id_mint_map, -1),
    'amount_swapped': serialize_engine.dumps(amount_swapped, -1),
    'deposited_sims': deposited_sims.copy(),
    'withdrawn_sims': withdrawn_sims.copy(),
    'rebalancer_map': serialize_engine.dumps(rebalancer_map, -1),
    'sim_usdt_balances': serialize_engine.dumps(sim_usdt_balances, -1),
    'sim_usdc_balances': serialize_engine.dumps(sim_usdc_balances, -1),
    'data_service': serialize_engine.dumps(data_service, -1),
    'rebalance_counter': serialize_engine.dumps(rebalance_counter, -1),
    'sim_balances_temp': serialize_engine.dumps(sim_balances_temp, -1),
    'sim_balance_ranges': serialize_engine.dumps(sim_balance_ranges, -1),
    'balance_changes': serialize_engine.dumps(balance_changes, -1),
  }
  print("Saving snapshot at block {}".format(block_number))

def load_snapshot(block_number):
  global ticks
  global lp_providers
  global last_tick
  global latest_price
  global latest_price_x96
  global net_liquidity
  global net_usdc_fee
  global net_usdt_fee
  global mint_ev_map
  global token_id_owner_map
  global token_id_mint_map
  global amount_swapped
  global deposited_sims
  global withdrawn_sims
  global rebalancer_map
  global sim_usdt_balances
  global sim_usdc_balances
  global data_service
  global rebalance_counter
  global sim_balances_temp
  global sim_balance_ranges
  global balance_changes

  ticks = serialize_engine.loads(snapshot['ticks'])
  lp_providers = serialize_engine.loads(snapshot['lp_providers'])
  last_tick = snapshot['last_tick']
  latest_price = snapshot['latest_price']
  latest_price_x96 = snapshot['latest_price_x96']
  net_liquidity = snapshot['net_liquidity']
  net_usdc_fee = snapshot['net_usdc_fee']
  net_usdt_fee = snapshot['net_usdt_fee']
  mint_ev_map = serialize_engine.loads(snapshot['mint_ev_map'])
  token_id_owner_map = serialize_engine.loads(snapshot['token_id_owner_map'])
  token_id_mint_map = serialize_engine.loads(snapshot['token_id_mint_map'])
  amount_swapped = serialize_engine.loads(snapshot['amount_swapped'])
  deposited_sims = snapshot['deposited_sims'].copy()
  withdrawn_sims = snapshot['withdrawn_sims'].copy()
  rebalancer_map = serialize_engine.loads(snapshot['rebalancer_map'])
  sim_usdt_balances = serialize_engine.loads(snapshot['sim_usdt_balances'])
  sim_usdc_balances = serialize_engine.loads(snapshot['sim_usdc_balances'])
  data_service = serialize_engine.loads(snapshot['data_service'])
  rebalance_counter = serialize_engine.loads(snapshot['rebalance_counter'])
  sim_balances_temp = serialize_engine.loads(snapshot['sim_balances_temp'])
  sim_balance_ranges = serialize_engine.loads(snapshot['sim_balance_ranges'])
  balance_changes = serialize_engine.loads(snapshot['balance_changes'])

  print("Snapshot loaded at block {}".format(block_number))

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

def distribute_fee_to_tick(tick_index, usdc_fee, usdt_fee, block_number):
  global sim_per_block_data

  tick = ticks.get(str(tick_index), {
    'liquidity': 0,
    # 'usdc': 0,
    # 'usdt': 0,
    'positions': {}
  })

  tick_liquidity = int(tick['liquidity'])
  if tick_liquidity > 0:
    for addr in tick['positions'].keys():
      is_simulation_address = addr.startswith("0xsim")
      if is_simulation_address:
        if 'earnings' not in sim_per_block_data.keys():
          sim_per_block_data['earnings'] = {}
        if addr not in sim_per_block_data['earnings'].keys():
          sim_per_block_data['earnings'][addr] = []

        earnings_per_block = sim_per_block_data['earnings'][addr]
        # if empty array init value ranges for earnings
        if not bool(earnings_per_block):
          start_block = int(sim_per_block_data['start_block'])
          end_block = int(sim_per_block_data['end_block'])
          EARNINGS_RESOLUTION = sim_per_block_data['EARNINGS_RESOLUTION']
          for i in range(EARNINGS_RESOLUTION):
            chunk_size = (end_block - start_block) / EARNINGS_RESOLUTION
            start_block_range = start_block + i * chunk_size
            earnings_per_block.append({
              "start_block_range": start_block_range,
              "end_block_range": start_block_range + chunk_size - 1,
              "usdc_profit": 0,
              "usdt_profit": 0,
              "total_value": 0,
              "total_value_diff": 0
            })
          sim_per_block_data['earnings'][addr] = earnings_per_block




      lp_provider = lp_providers.get(addr, {
        "net_liquidity": 0,
        # "usdc_net": 0,
        # "usdt_net": 0,
        "usdc_profit": 0,
        "usdt_profit": 0
      })

      provided_liquidity = int(tick['positions'][addr]['liquidity'])
      usdc_profit = math.floor(usdc_fee * provided_liquidity / tick_liquidity)
      usdt_profit = math.floor(usdt_fee * provided_liquidity / tick_liquidity)

      lp_provider["usdc_profit"] += usdc_profit
      lp_provider["usdt_profit"] += usdt_profit

      if is_simulation_address:
        for idx, earning_chunk in enumerate(sim_per_block_data['earnings'][addr]):
          if earning_chunk['start_block_range'] < block_number and earning_chunk['end_block_range'] > block_number:
            # add the profits info
            earning_chunk["usdc_profit"] += usdc_profit
            earning_chunk["usdt_profit"] += usdt_profit

            # add the total_value info (it might be re-written multiple times but that is ok)
            data = lp_providers.get(addr.lower())
            if data is None:
              continue
            usdc_fee, usdt_fee, usdc_bal, usdt_bal, liquidity, usdc_for_liquidity, usdt_for_liquidity, net_usdc, net_usdt, net_fee, initial_usdc, initial_usdt = get_stats_from_data(data, addr)

            initial_deposit = math.floor((initial_usdc + initial_usdt) / 10**6)
            current_value = math.floor((net_usdc + net_usdt) / 10**6)
            earning_chunk["total_value_diff"] = current_value - initial_deposit
            earning_chunk["total_value"] = current_value

            sim_per_block_data['earnings'][addr][idx] = earning_chunk
              
            break;
        
      lp_providers[addr] = lp_provider

def handle_swap_event(event):
  global net_liquidity
  global net_usdc_fee
  global net_usdt_fee
  global last_tick
  global latest_price_x96
  global latest_price
  global amount_swapped

  curr_tick = int(event["arg__tick"])
  liquidity = int(event["arg__liquidity"])
  sqrtPriceX96 = int(event["arg__sqrtPriceX96"])
  amount0 = int(event["arg__amount0"])
  amount1 = int(event["arg__amount1"])

  first_swap = last_tick is None 
  is_multi_tick = last_tick != curr_tick and not first_swap

  usdc_fee = usdt_fee = 0
  if amount0 > 0:
    usdc_fee = abs(amount0) * pool_fee
    if is_multi_tick:
      amount_swapped['accross_ticks'] += amount0
    else:
      amount_swapped['within_tick'] += amount0
  else: 
    usdt_fee = abs(amount1) * pool_fee
    if is_multi_tick:
      amount_swapped['accross_ticks'] += amount1
    else:
      amount_swapped['within_tick'] += amount1
  
  net_usdc_fee += usdc_fee
  net_usdt_fee += usdt_fee

  if not is_multi_tick:
    distribute_fee_to_tick(curr_tick, usdc_fee, usdt_fee, event['block_number'])

  else:
    direction = last_tick < curr_tick # True for forward

    total_ticks = max(last_tick, curr_tick) - min(last_tick, curr_tick) + 1
    usdc_fee_per_tick = usdc_fee / total_ticks
    usdt_fee_per_tick = usdt_fee / total_ticks

    for tick in range(min(last_tick, curr_tick), max(last_tick, curr_tick) + 1):
      distribute_fee_to_tick(str(tick), usdc_fee_per_tick, usdt_fee_per_tick, event['block_number'])
        
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

def handle_simulation(block_number, scenario):
  global deposited_sims
  global withdrawn_sims
  global latest_price
  global last_tick

  if latest_price is None:
    return

  data_service.set_latest_block(block_number)
  data_service.set_latest_tick(last_tick)

  handle_rebalances()

  address = scenario["address"].lower()
  token_id = address

  withdraw_before = scenario.get("withdraw_before", 0)

  enable_rebalancer = scenario.get("enable_rebalancer", False)
  rebalance_frequency = scenario.get("rebalance_frequency", 0)
  target_tick_range = scenario.get("target_tick_range", 1)

  max_usdc_amount = math.floor(scenario["usdc_amount"] * 10**6)
  max_usdt_amount = math.floor(scenario["usdt_amount"] * 10**6)

  lower_tick = scenario["lower_tick"]
  upper_tick = scenario["upper_tick"]
  lower_tick_index = find_tick_index(lower_tick)
  upper_tick_index = find_tick_index(upper_tick)

  if enable_rebalancer and address in deposited_sims and address not in withdrawn_sims:
    rebalancer = rebalancer_map[address]
    rebalancer.run()

  if address not in deposited_sims and (deposit_after == 0 or deposit_after <= block_number):
    (usdc_amount, usdt_amount, liquidity) = find_token_split(max_usdc_amount, max_usdt_amount, lower_tick_index, upper_tick_index)

    print("Adding liquidity for simulated address {} at block {}:".format(address, block_number))
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

    #rebalancer = Rebalancer(data_service, address, target_tick_range, rebalance_frequency)
    rebalancer = CustomRebalancer(data_service, address, target_tick_range, rebalance_frequency)
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

def handle_rebalances():
  rebalance_requests = data_service.get_rebalance_requests()
  for [address, lower_tick, upper_tick] in rebalance_requests:
    address = address
    token_id = address
    provider = lp_providers.get(address)
    liquidity_to_remove = provider.get("net_liquidity")
    (usdc_received, usdt_received) = decrease_liquidity(token_id, liquidity_to_remove)
    
    max_usdc = sim_usdc_balances[address] + (usdc_received * (1 - pool_fee))
    max_usdt = sim_usdt_balances[address] + (usdt_received * (1 - pool_fee))

    net_gas_estimate = usd_gas_estimate * 10**6

    # if (max_usdc + max_usdt) < net_gas_estimate:
    #   # Lost all capital??
    #   sim_usdc_balances[address] = max_usdc
    #   sim_usdt_balances[address] = max_usdt
    #   data_service.pause_position(token_id)
    #   continue
    # elif (max_usdc >= net_gas_estimate / 2) and (max_usdt >= net_gas_estimate / 2):
    #   max_usdc -= (net_gas_estimate / 2)
    #   max_usdt -= (net_gas_estimate / 2)
    # elif max_usdc >= net_gas_estimate:
    #   max_usdc -= net_gas_estimate
    # elif max_usdt >= net_gas_estimate:
    #   max_usdt -= net_gas_estimate
    # else:
    #   new_bal = max_usdc + max_usdt - net_gas_estimate
    #   max_usdc = new_bal if max_usdc > max_usdt else 0
    #   max_usdt = new_bal if max_usdc <= max_usdt else 0

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
    if address not in rebalance_counter:
      rebalance_counter[address] = {'count': 0, 'cost' : 0}
    
    rebalance_counter[address]['count'] = (rebalance_counter.get(address).get('count')) + 1
    rebalance_counter[address]['cost'] = (rebalance_counter.get(address).get('cost')) + net_gas_estimate

# calculate how much strategy would earn if non active funds were deployed to Aave / Compound
def calculate_aave_profits(non_deployed_apy, sim_balance_ranges_w_time, sim_address):
  seconds_in_a_year = 86400 * 365.25
  profits = 0
  for token in ['USDT', 'USDC']:
    balances_with_time = sim_balance_ranges_w_time[token][sim_address]
    for balance_item in balances_with_time: 
      if balance_item['block_range_time_diff'] == 'false':
        continue

      profit = balance_item['balance'] * non_deployed_apy * balance_item['block_range_time_diff'] / seconds_in_a_year
      profits += profit

  return profits

def get_stats_from_data(data, address):
  scenario = False
  for scen in scenarios:
    if scen['address'] == address:
      scenario = scen
      break

  initial_usdc = scenario["usdc_amount"] * 10**6
  initial_usdt = scenario["usdt_amount"] * 10**6

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

  return [usdc_fee, usdt_fee, usdc_bal, usdt_bal, liquidity, usdc_for_liquidity, usdt_for_liquidity, net_usdc, net_usdt, net_fee, initial_usdc, initial_usdt]

def store_results(scenario, balance_changes_w_time, sim_balance_ranges_w_time):
  global table_data
  global apy_table_data
  global usdc_table_data
  global usdt_table_data
  global amount_swapped

  print("Total amount of funds swapped withing a tick: {} across ticks: {} ratio: {}".format(amount_swapped['within_tick'] / 1e6, amount_swapped['accross_ticks'] / 1e6, (amount_swapped['accross_ticks']/amount_swapped['within_tick'])))
  address = scenario["address"]
  non_deployed_apy = scenario["non_deployed_apy"]

  # how long were the funds active in the Uniswap
  simulation_active_time = sim_balance_ranges_w_time[address]['block_range_time_diff']
  seconds_in_a_year = 86400 * 365.25

  data = lp_providers.get(address.lower())
  if data is None:
    print("\tNOT FOUND")
    return

  usdc_fee, usdt_fee, usdc_bal, usdt_bal, liquidity, usdc_for_liquidity, usdt_for_liquidity, net_usdc, net_usdt, net_fee, initial_usdc, initial_usdt = get_stats_from_data(data, address)

  rebalance_cost = rebalance_counter.get(address, {}).get('cost', 0) / 1e6

  aave_profits = calculate_aave_profits(non_deployed_apy, balance_changes_w_time, address) / 10**6

  initial_deposit = math.floor((initial_usdc + initial_usdt) / 10**6)
  current_value = math.floor((net_usdc + net_usdt) / 10**6)
  diff = current_value - initial_deposit

  def calculate_apr_from_profit(profit):
    return (profit / initial_deposit) * seconds_in_a_year / simulation_active_time

  apr = calculate_apr_from_profit(diff)
  aave_apr = calculate_apr_from_profit(aave_profits)
  total_apr = calculate_apr_from_profit(aave_profits + diff)
  total_apr_w_rebalance_gas = calculate_apr_from_profit(aave_profits + diff - rebalance_cost)

  growth = math.floor(10000 * diff / initial_deposit) / 100

  apy = to_apy(apr)
  aave_apy = to_apy(aave_apr)
  total_apy = to_apy(total_apr)
  total_apy_w_rebalance_gas = to_apy(total_apr_w_rebalance_gas)

  scenario['results'] = {
    'apy': apy,
    'aave_apy': aave_apy,
    'total_apy': total_apy,
    'total_apy_w_rebalance_gas': total_apy_w_rebalance_gas
  }

  apy_table_data += [[
    address,
    str(round(apy * 100, 2)) + "%", #APY
    str(round(aave_apy * 100, 2)),
    str(round(total_apy * 100, 2)) + "%", #Total APY
    str(round(total_apy_w_rebalance_gas * 100, 2)) + "%", #total_apr_w_rebalance_gas
  ]]

  table_data += [[
    #str(round(apr * 100, 2)) + "%", #APY
    address,
    str(initial_deposit), # Initial Deposit Value
    str(current_value), # Current Deposit Value
    str(round(diff, 2)), # Diff in Deposit Value
    str(round(net_fee / 1e6, 2)), # Net Fee Earned
    str(round(aave_profits, 2)), # Aave profits
    str(rebalance_counter.get(address, {}).get('count')), # Total Re-balances
    str(round(liquidity, 2)), # Net Liquidity
    str(round(growth, 2)) + "%", # growth
    "$" + str(rebalance_cost), # Total Re-balances
    str(round(simulation_active_time / 86400, 2)) # Days active
  ]]

  usdc_table_data += [[
    address,
    str(round(net_usdc / 1e6, 2)), # Net USDC
    str(round(usdc_for_liquidity / 1e6, 2)), # Liquidity
    str(round(usdc_bal / 1e6, 2)), # Bal
    str(round(usdc_fee / 1e6, 2)), # Fee
  ]]

  usdt_table_data += [[
    address,
    str(round(net_usdt / 1e6, 2)), # Net USDT
    str(round(usdt_for_liquidity / 1e6, 2)), # Liquidity
    str(round(usdt_bal / 1e6, 2)), # Bal
    str(round(usdt_fee / 1e6, 2)), # Fee
  ]]
  
def print_results():
  print('')
  print('APY & performance')
  print_table([[
    "Simulation",
    "Uni3 Pool APY",
    "Aave APY",
    "Combined APY",
    "Combined APY (incl. gas cost)"]] + apy_table_data,
    double_hline = True)

  print('')
  print('Total Deposits/Balances')
  print_table([[
    "Simulation",
    "Initial Dep. Value",
    "Current Dep. Value",
    "Diff in Dep. Value",
    "Net Fee Earned", 
    "Aave profits",
    "Total Rebalances",
    "Net Liquidity",
    "Growth",
    "Rebalance Cost",
    "Sim. Length [Days]"]] + table_data,
    double_hline = True)

  print('')
  print('USDC')
  print_table([[
    "Simulation",
    "Net USDC",
    "Liquidity",
    "Bal",
    "Fee",
  ]] + usdc_table_data, double_hline = True)

  print('')
  print('USDT')
  print_table([[
    "Simulation",
    "Net USDT",
    "Liquidity",
    "Bal",
    "Fee"
  ]] + usdt_table_data, double_hline = True)

  #print_apy_chart()
  print_earnings_per_block(scenarios[0])

def print_earnings_per_block(scenario):
  earnings = sim_per_block_data['earnings'][scenario['address']];

  fig, ax1 = plt.subplots()
  ax2 = ax1.twinx()

  X = []
  Y = []
  Y2 = []

  for earning in earnings:
    X.append(earning['start_block_range'])
    Y.append(earning['usdc_profit'] + earning['usdt_profit'])
    Y2.append(earning['total_value_diff'])

  ax1.plot(X,Y, 'g-')
  ax1.grid()
  ax2.plot(X,Y2, 'b-')

  ax1.set_xlabel('Blocks')
  ax1.set_ylabel('Earnings', color='g')
  ax2.set_ylabel('Total Value Difference', color='b')

  plt.title("Earnings & Total Value Difference per block {}".format(scenario['address']))
  plt.show()

def print_apy_chart():
  fig = plt.figure()
  ax = fig.add_subplot(111)

  plt.xlabel('Funds Deployed [million]')
  plt.ylabel('Total APY [%]')

  X = []
  TOTAL_APY_W_GAS = []
  RAW_UNISWAP_POOL_APY = []
  TOTAL_APY_NO_GAS = []
  AAVE_APY = []
  for scenario in scenarios:
    X += [(scenario['usdc_amount'] + scenario['usdt_amount']) / 1e6]
    #Y += [round(scenario['results']['apy'] * 100, 2)]
    TOTAL_APY_W_GAS += [round(scenario['results']['total_apy_w_rebalance_gas'] * 100, 2)]
    RAW_UNISWAP_POOL_APY += [round(scenario['results']['total_apy'] * 100, 2)]
    TOTAL_APY_NO_GAS += [round(scenario['results']['apy'] * 100, 2)]
    AAVE_APY += [round(scenario['results']['aave_apy'] * 100, 2)]


  ax.plot(X,TOTAL_APY_W_GAS, label="APY w/ gas")
  ax.plot(X,TOTAL_APY_NO_GAS, label="APY no gas")
  ax.plot(X,RAW_UNISWAP_POOL_APY, label="Raw Uniswap pool APY")
  ax.plot(X,AAVE_APY, label="APY from Aave")

  # for index, xy in enumerate(zip(X, Y)):
  #   scenario = scenarios[index]
  #   #ax.annotate('(%s, %s)' % xy, xy=xy, textcoords='data') # <--
  #   #ax.annotate('{}'.format(scenario['address']), xy=xy, textcoords='data') # <--
  #   ax.annotate('{}'.format(round(scenario['results']['total_apy_w_rebalance_gas'] * 100, 2)), xy=xy, textcoords='data')

  ax.legend()
  ax.grid()

  plt.show()

def store_simulation_balances():
  # can not reassign copy to dictionary variable since that created a local variable
  # rather then accessing a global one
  sim_balances_temp['USDT'] = sim_usdt_balances.copy()
  sim_balances_temp['USDC'] = sim_usdc_balances.copy()

# in case amount of usdt/usdc balance of simulation changes record it
# use `forceRecord` to record the final block even when there are no changes
def record_token_balance_changes(block_number, forceRecord=False):
  temp_tokens = [sim_balances_temp['USDT'], sim_balances_temp['USDC']]
  stored_tokens = [sim_usdt_balances, sim_usdc_balances]

  # loop through stablecoins
  for index, sim_token_balance_temp in enumerate(temp_tokens):
    token = 'USDT' if index == 0 else 'USDC'
    stored_token_dictionary = stored_tokens[index]
    # loop through simulation addresses
    for sim_address in stored_token_dictionary.keys():
      if sim_address not in balance_changes[token]:
        balance_changes[token][sim_address] = []

      if sim_address not in sim_balance_ranges:
        sim_balance_ranges[sim_address] = {'first_block_number': False, 'last_block_number': False, 'block_range_time_diff': False}

      balance_change = balance_changes[token][sim_address]

      if sim_address not in sim_token_balance_temp:
        sim_token_balance_temp[sim_address] = 0

      # update first block when simulation has balance record
      if stored_token_dictionary[sim_address] > 0 and sim_balance_ranges[sim_address]['first_block_number'] == False:
        sim_balance_ranges[sim_address]['first_block_number'] = block_number
      # just update final / last block that simulation was active each time
      sim_balance_ranges[sim_address]['last_block_number'] = block_number

      # simulation balance has not changed... continue
      if sim_token_balance_temp[sim_address] == stored_token_dictionary[sim_address] and not forceRecord:
        continue

      balance_change_info = {
        'token': token,
        'balance': stored_token_dictionary[sim_address],
        'balance_diff': stored_token_dictionary[sim_address] - sim_token_balance_temp[sim_address],
        'block_number': block_number,
        'block_number_end': False, # until what block was this balance
        'block_range_time_diff': False # amount of seconds between block_number & block_number_end
      }

      balance_change.append(balance_change_info)

      # not the first balance change
      if len(balance_change) > 1:
        previous_balance_change_info = balance_change[-2]
        previous_balance_change_info['block_number_end'] = block_number - 1

async def add_block_range_times_to_balance_changes(balance_change, sim_balance_ranges):
  # There is a bug in CTC and we need to group block numbers together otherwise it hits the
  # limit of number of open SqlLite connections. So we do 2 passes. In first pass we fetch all 
  # the block numbers. In second pass we use the fetched blocks
  block_numbers = []
  blk_to_time = {}
  for first_pass in [True, False]:
    for token in balance_changes:
      for sim_address in balance_changes[token]:
        changes_array = balance_changes[token][sim_address]
        for index, change_item in enumerate(changes_array):
          # skip first item
          if index == 0:
            continue

          if first_pass:
            prev_change = balance_changes[token][sim_address][index - 1]
            block_numbers.append(prev_change['block_number'])
            block_numbers.append(change_item['block_number'])
          else:
            prev_change = balance_changes[token][sim_address][index - 1]
            prev_change['block_range_time_diff'] = blk_to_time[change_item['block_number']] - blk_to_time[prev_change['block_number']] - 1

    for sim_address in sim_balance_ranges:
      sim_range = sim_balance_ranges[sim_address]
      if first_pass:
        block_numbers.append(sim_range['first_block_number'])
        block_numbers.append(sim_range['last_block_number'])
      else:
        sim_range['block_range_time_diff'] = blk_to_time[sim_range['last_block_number']] - blk_to_time[sim_range['first_block_number']]

    if first_pass:
      blk_to_time = await blockNumberListToTimestamp(block_numbers)

  return [balance_changes, sim_balance_ranges]

def to_apy(apr, days=30.00):
    periods_per_year = Decimal(365.25 / days)
    return ((1 + Decimal(apr) / periods_per_year / 100) ** periods_per_year - 1) * 100


async def simulate(start_block, end_block, CONST_PREWARM_BLOCKS, EARNINGS_RESOLUTION):
  if (start_block > end_block):
    raise Exception("start_block needs to be larger than end_block")

  global deposit_after
  global prewarm_done
  deposit_after = int(start_block)
  sim_per_block_data['start_block'] = start_block
  sim_per_block_data['end_block'] = end_block
  sim_per_block_data['EARNINGS_RESOLUTION'] = EARNINGS_RESOLUTION

  print("Found {} scenarios to simulate".format(len(scenarios)))
  for scenario_index, scenario in enumerate(scenarios):
    _start_block = start_block

    if not prewarm_done and scenario_index == 0:
      _start_block = int(start_block) - CONST_PREWARM_BLOCKS
      print("Pre-warming the Uniswap pool starting at block {}".format(_start_block))
    elif scenario_index > 0:
      # start block already correct
      print("Starting on block {} with already pre-warmed snapshot".format(_start_block))
      load_snapshot(_start_block)

    data = await collect(_start_block, end_block)
    total = len(data)
    processed = 0
    pct5 = math.floor(5 * total / 100)
    print("Loaded {} events and processing them now".format(total))

    latest_block_number = 0
    for index, event in data.iterrows():
      block_number = int(event["block_number"])
      latest_block_number = block_number
      event_name = event["event_name"]
      
      if block_number >= int(start_block) - 1 and not prewarm_done and scenario_index == 0:
        prewarm_done = True
        print("Pre-warm done at block {}. Creating a snapshot".format(block_number))
        save_snapshot(block_number)

      store_simulation_balances()
      handle_simulation(block_number, scenario)
      record_token_balance_changes(block_number)

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
      
      # if processed % (pct5*4) == 0:
      #   break

    record_token_balance_changes(latest_block_number, True)
    balance_changes_w_time, sim_balance_ranges_w_time = await add_block_range_times_to_balance_changes(balance_changes, sim_balance_ranges)

    store_results(scenario, balance_changes_w_time, sim_balance_ranges_w_time)
  print_results()
