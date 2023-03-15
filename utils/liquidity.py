import math

def get_liquidity_for_amount0(ratio_a, ratio_b, amount0):
  if ratio_a > ratio_b: 
    (ratio_a, ratio_b) = (ratio_b, ratio_a)

  return math.floor((amount0 * ratio_a * ratio_b) / (ratio_b - ratio_a))

def get_liquidity_for_amount1(ratio_a, ratio_b, amount1):
  if ratio_a > ratio_b: 
    (ratio_a, ratio_b) = (ratio_b, ratio_a)

  return math.floor(amount1 / (ratio_b - ratio_a))

def get_amount0_for_liquidity(ratio_a, ratio_b, liquidity):
  if ratio_a > ratio_b: 
    (ratio_a, ratio_b) = (ratio_b, ratio_a)

  return math.floor(
    liquidity * (ratio_b - ratio_a) / ratio_b / ratio_a
  )

def get_amount1_for_liquidity(ratio_a, ratio_b, liquidity):
  if ratio_a > ratio_b: 
    (ratio_a, ratio_b) = (ratio_b, ratio_a)

  return math.floor(liquidity * (ratio_b - ratio_a))

def get_liquidity_amounts(sqrt_ratio_curr, ratio_a, ratio_b, amount0, amount1):
  if ratio_a > ratio_b:
    (ratio_a, ratio_b) = (ratio_b, ratio_a)

  liquidity = 0

  if sqrt_ratio_curr <= ratio_a:
    liquidity = get_liquidity_for_amount0(ratio_a, ratio_b, amount0)
  elif sqrt_ratio_curr < ratio_b:
    liquidity0 = get_liquidity_for_amount0(sqrt_ratio_curr, ratio_b, amount0)
    liquidity1 = get_liquidity_for_amount1(ratio_a, sqrt_ratio_curr, amount1)
    liquidity = liquidity0 if liquidity0 < liquidity1 else liquidity1
  else:
    liquidity = get_liquidity_for_amount1(ratio_a, ratio_b, amount1)
  
  return liquidity

def get_amounts_for_liquidity(ratio, ratio_a, ratio_b, liquidity):
  if ratio_a > ratio_b: 
    (ratio_a, ratio_b) = (ratio_b, ratio_a)

  amount0 = 0
  amount1 = 0

  if ratio <= ratio_a:
    amount0 = get_amount0_for_liquidity(ratio_a, ratio_b, liquidity)
  elif ratio < ratio_b:
    amount0 = get_amount0_for_liquidity(ratio, ratio_b, liquidity)
    amount1 = get_amount1_for_liquidity(ratio_a, ratio, liquidity)
  else:
    amount1 = get_amount0_for_liquidity(ratio_a, ratio_b, liquidity)
    
  return (amount0, amount1)

