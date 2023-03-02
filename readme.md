## Prerequisite
```
pip3 install ctc && ctc config && ctc setup
```

## Simulation
Update `simulator/data/scenarios.py` and then run:

```
python3 run.py
```

## Plan
```
Mint/IncreaseLiquidity:
  - Identify number of ticks between amount0 and amount1 (N)
  - Note liquidity (L)
  - Split liquidity over the ticks (L/N)

Burn/DecreaseLiquidity:
  - Identify number of ticks between amount0 and amount1 (N)
  - Note liquidity (L)
  - Split liquidity over the ticks (L/N)

Swap:
  - Find USDC/USDT split
    - L = sqrt(xy)
    - sqrt(P) = sqrt(y/x)

    - x = L / sqrt(P)
    - y = L * sqrt(P)
  - Find total fee
    - Single tick:
      - amount * fee
      - L(t) = (L(t) - amount)
    - Multiple ticks:
      - For all ticks fully crossed, L(t) * fee
      - For first tick, L(tick1) * fee
      - For last/current tick, (amount - sum(L[1 to n-1])) * fee
      - L(t[2 to n-1]) = -L(t[2 to n-1])
  - Get the current tick
  - Figure out profits for each LP provider
```