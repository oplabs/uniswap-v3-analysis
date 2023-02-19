import math

def find_tick_index(price):
  return round(math.log(price, 1.0001))

def get_sqrt_ratio_at_tick(tick_index):
  return math.sqrt(1.0001 ** tick_index) # * 2**96
