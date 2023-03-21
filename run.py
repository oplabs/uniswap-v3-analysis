import asyncio

from simulator import simulate

# Testing has demonstrated that we need to preload 2.7 mio of blocks before starting the simulation
# to `pre-warm` the Uniswap pool with balances in a way that the simulation can be ran on a close
# to mainnet state

CONST_PREWARM_BLOCKS = 2700000 # full pool pre-warm
#CONST_PREWARM_BLOCKS = 1000000 # close to full pool pre-warm
#CONST_PREWARM_BLOCKS =  270000 # quick prewarm -> not accurate data

# in how many brackets per simulation to split the fee earnings to
EARNINGS_RESOLUTION = 100

# TODO: Make these CLI args
#start_block = "13609065"
#end_block = "16642500"

# last month from 7.3.2023
#start_block = "16567020"
#end_block = "16819063"

# 2 weeks
#start_block = "16617020"
#end_block = "16707020"

# 10 days
start_block = "16706020"
end_block = "16777020"

#1 Day
#start_block = "16706020"
#end_block = "16714020"

# ~6 days including the USDC de-peg
#start_block = "16792063" # 9th Mar
#end_block = "16832021" # 15th Mar

async def main():
  await simulate(start_block, end_block, CONST_PREWARM_BLOCKS, EARNINGS_RESOLUTION)

asyncio.run(main())
