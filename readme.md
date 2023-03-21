## Prerequisite
Create new virtual environment
```
// run below code only once to create virtual environment
python3 -m venv env-uniswap

// run below code each time you want environment activated
source env-uniswap/bin/activate
```


```
// run below code once to install requirements in virtual environment
pip install -r requirements.txt
pip3 install ctc && ctc config && ctc setup
```

## Simulation
Update `simulator/data/scenarios.py` and then run:

```
python3 run.py
```

- It is suggested that one tick range, one deposit liquidity and one rebase frequency is used.
- in run.py select the CONST_PREWARM_BLOCKS required. It is suggested to pick a smaller block range for when new functionality is tested out. And full pool prewarm when exact data is required
- pick start_block -> end_block range of the simulation
- open custom_rebalancer.py and create a more efficient rebalancing strategy

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