
class SimulatorDataService:
  def __init__(self):
    self._positions = {}
    self._latest_tick = None
    self._latest_block = None
    self._scheduled_rebalances = []
    self._scheduled_swaps = []
    self._paused_positions = set()

  def request_rebalance(self, position_id, desired_lower_tick, desired_upper_tick, swap_tokens):
    self._scheduled_rebalances.append(
      [position_id, desired_lower_tick, desired_upper_tick, swap_tokens]
    )

  def get_position_data(self, position_id):
    return self._positions.get(position_id)

  def get_latest_block(self):
    return self._latest_block

  def get_latest_tick(self):
    return self._latest_tick

  def has_pending_rebalance(self, position_id):
    for [position_id, lt, ut] in self._scheduled_rebalances:
      if position_id == position_id:
        return True
    return False

  def pause_position(self, position_id):
    print("Position {} is paused".format(position_id))
    self._paused_positions = self._paused_positions | set([position_id])

  def is_position_paused(self, position_id):
    return position_id in self._paused_positions

  def set_position_data(self, position_id, data):
    self._positions[position_id] = data

  def set_latest_block(self, latest_block):
    self._latest_block = latest_block

  def set_latest_tick(self, latest_tick):
    self._latest_tick = latest_tick

  def get_rebalance_requests(self):
    requests = self._scheduled_rebalances
    self._scheduled_rebalances = []
    return requests
