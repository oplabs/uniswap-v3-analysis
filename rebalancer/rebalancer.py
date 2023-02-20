import time

class Rebalancer:
  def __init__(self, data_service, position_id, tick_range, rebalance_frequency):
    self.data_service = data_service # A service that interacts with blockchain/simulator to get data
    self.position_id = position_id # Position NFT ID
    self.tick_range = tick_range # When rebalancing, -n to n ticks are used as lower_tick and upper_tick
    self.rebalance_frequency = rebalance_frequency

    self.out_of_bounds_since = None
    self.last_tick = None

  def rebalance(self):
    if self.data_service.is_position_paused(self.position_id):
      return

    if self.data_service.has_pending_rebalance(self.position_id):
      return

    latest_tick = self.data_service.get_latest_tick()
    desired_lower_tick = latest_tick - self.tick_range
    desired_upper_tick = latest_tick + self.tick_range

    self.data_service.request_rebalance(self.position_id, desired_lower_tick, desired_upper_tick)

  def run(self):
    current_position = self.data_service.get_position_data(self.position_id)
    latest_block = self.data_service.get_latest_block()
    latest_tick = self.data_service.get_latest_tick()

    is_active = self.is_active_at(current_position, latest_tick)

    # Was it active until last block?
    was_active = self.out_of_bounds_since is None and self.last_tick is not None

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

      if self.rebalance_frequency == 0 or inactive_for >= self.rebalance_frequency:
        # Rebalance when needed
        self.rebalance()
    
    self.last_tick = latest_tick
  
  def is_active_at(self, position, tick):
    (lower_tick, upper_tick) = position
    return lower_tick <= tick and tick <= upper_tick
