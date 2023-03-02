import ctc

async def getBlock(block_number):
  block = await ctc.async_get_block(block_number)
  return block

# get block diff in seconds
async def getBlockTimeDiff(start_block_number, end_block_number):
	start_block = await getBlock(start_block_number)
	end_block = await getBlock(end_block_number)

	return end_block['timestamp'] - start_block['timestamp']