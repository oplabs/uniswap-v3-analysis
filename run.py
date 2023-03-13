import asyncio

from simulator import simulate

# TODO: Make these CLI args
#start_block = "13609065"
#end_block = "16642500"

# last month from 7.3.2023
#start_block = "16567020"
#end_block = "16777020"

# 2 weeks
#start_block = "16677020"
#end_block = "16777020"

# 10 days
# start_block = "16706020"
# end_block = "16777020"

# ~3 days
start_block = "16799063" # 13th Mar
end_block = "16819063" # 10th Mar

async def main():
  await simulate(start_block, end_block)

asyncio.run(main())
