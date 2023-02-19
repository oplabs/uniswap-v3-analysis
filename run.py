import asyncio

from simulator import simulate

# TODO: Make these CLI args
start_block = "13609065"
end_block = "16642500"

async def main():
  await simulate(start_block, end_block)

asyncio.run(main())
