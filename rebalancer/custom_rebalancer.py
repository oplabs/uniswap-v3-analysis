import time
from utils.tick import find_tick_index

class CustomRebalancer:
  def __init__(self, data_service, position_id, tick_range, rebalance_frequency, lp_providers, sim_usdc_balances, sim_usdt_balances, address, pool_fee):
    self.data_service = data_service # A service that interacts with blockchain/simulator to get data
    self.position_id = position_id # Position NFT ID
    self.tick_range = tick_range # When rebalancing, -n to n ticks are used as lower_tick and upper_tick
    self.rebalance_frequency = rebalance_frequency
    self.lp_providers = lp_providers
    self.sim_usdc_balances = sim_usdc_balances
    self.sim_usdt_balances = sim_usdt_balances
    self.address = address
    self.pool_fee = pool_fee

    self.out_of_bounds_since = None
    self.last_tick = None

  def is_active_at(self, position, tick):
    (lower_tick, upper_tick) = position
    return lower_tick <= tick and tick <= upper_tick

  def run(self):
    current_position = self.data_service.get_position_data(self.position_id)
    latest_block = self.data_service.get_latest_block()
    latest_tick = self.data_service.get_latest_tick()

    is_active = self.is_active_at(current_position, latest_tick)

    # Was it active until last block?
    was_active = self.out_of_bounds_since is None and self.last_tick is not None
    inactive_for = False

    if is_active:
      # Tick is currently active
      # if not was_active:
      #   print("Position {} is active again".format(self.position_id))
      self.out_of_bounds_since = None # Reset pointer
    else: 
      # Tick is inactive
      if was_active:
        # If yes, Note down the current block number
        # print("Position {} is inactive now".format(self.position_id))
        self.out_of_bounds_since = latest_block
      
      inactive_for = latest_block - (self.out_of_bounds_since or 0)

      # if self.rebalance_frequency == 0 or inactive_for >= self.rebalance_frequency:
      #   # Rebalance when needed
      #   self.rebalance()
    
    self.last_tick = latest_tick

    position_paused = self.data_service.is_position_paused(self.position_id)
    rebalance_pending = self.data_service.has_pending_rebalance(self.position_id)
    can_rebalance = not position_paused and not rebalance_pending


    #self.simpleRebalanceStrategy(current_position, latest_block, latest_tick, is_active, self.out_of_bounds_since, position_paused, rebalance_pending, can_rebalance, inactive_for)
    #self.simpleRebalanceStrategyV2(current_position, latest_block, latest_tick, is_active, self.out_of_bounds_since, position_paused, rebalance_pending, can_rebalance, inactive_for)
    self.simpleRebalanceStrategyV3(current_position, latest_block, latest_tick, is_active, self.out_of_bounds_since, position_paused, rebalance_pending, can_rebalance, inactive_for)

  # just rebalance if tick is not active and has been inactive for #rebalance_frequency block range
  def simpleRebalanceStrategy(
    self,
    current_position,
    latest_block,
    latest_tick,
    is_active,
    out_of_bounds_since,
    position_paused,
    rebalance_pending,
    can_rebalance,
    inactive_for
  ):

    if can_rebalance and inactive_for >= self.rebalance_frequency:
      desired_lower_tick = latest_tick - self.tick_range
      desired_upper_tick = latest_tick + self.tick_range
      self.data_service.request_rebalance(self.address, desired_lower_tick, desired_upper_tick, False)


  # same as basic rebalance strategy, but we stay within 0.995 - 1.005 swapping range
  def simpleRebalanceStrategyV2(
    self,
    current_position,
    latest_block,
    latest_tick,
    is_active,
    out_of_bounds_since,
    position_paused,
    rebalance_pending,
    can_rebalance,
    inactive_for
  ):
    upper_tick_limit = find_tick_index(1.01)
    lower_tick_limit = find_tick_index(0.99)
    inactivity_blocks = 40

    # wait for 20 blocks before rebalancing
    if can_rebalance and latest_tick < upper_tick_limit and latest_tick > lower_tick_limit and inactive_for >= inactivity_blocks:
      desired_lower_tick = latest_tick - self.tick_range
      desired_upper_tick = latest_tick + self.tick_range
      self.data_service.request_rebalance(self.address, desired_lower_tick, desired_upper_tick, False)

  # same as V2 and we also swap tokens when we have more than threshold of one  
  def simpleRebalanceStrategyV3(
    self,
    current_position,
    latest_block,
    latest_tick,
    is_active,
    out_of_bounds_since,
    position_paused,
    rebalance_pending,
    can_rebalance,
    inactive_for
  ):
    upper_tick_limit = find_tick_index(1.01)
    lower_tick_limit = find_tick_index(0.99)
    inactivity_blocks = 40
    swap_threshold = 0.99

    usdc_balance = self.sim_usdc_balances[self.address]
    usdt_balance = self.sim_usdt_balances[self.address]
    total = usdc_balance + usdt_balance

    do_a_swap = False
    if (usdc_balance / total > swap_threshold) or (usdt_balance / total > swap_threshold):
      do_a_swap = True

    if (can_rebalance and latest_tick < upper_tick_limit and latest_tick > lower_tick_limit and inactive_for >= inactivity_blocks):
      desired_lower_tick = latest_tick - self.tick_range
      desired_upper_tick = latest_tick + self.tick_range
      self.data_service.request_rebalance(self.address, desired_lower_tick, desired_upper_tick, do_a_swap)





