import importlib
import ctc
import time

# fetches = 0
# async def getBlockTimestamp(block_number):
#   global fetches
#   attempts = 0
#   block_timestamp = False

#   while True:
#     try:
#       attempts += 1
#       #block_timestamp = w3.eth.get_block(block_number)
#       #async_get_block_timestamps
#       block_timestamp = await ctc.async_get_block(block_number)
#       fetches += 1
#       attempts = 0
#       if fetches % 100 == 0:
#         print("Fetches: ", fetches)
#     except:
#       importlib.reload(ctc)
#       print("Failed: ", attempts, fetches)
#       if attempts >= 10000:
#         print("FAILED!", attempts)
#         raise

#   return block_timestamp

# ctc has a bug where too many requests error out. Seems they are not
# cleaning up the Sqlite connection. So group requests together
async def blockNumberListToTimestamp(block_numbers):
  aggregator = {}
  chunk_size = 100
  for chunk in split(block_numbers, chunk_size):
    block_timestamps = await ctc.async_get_block_timestamps(chunk)
    # merge the dictionaries
    aggregator.update(dict(zip(chunk, block_timestamps)))

  return aggregator

def split(list_a, chunk_size):
  for i in range(0, len(list_a), chunk_size):
    yield list_a[i:i + chunk_size]


# get block diff in seconds
async def getBlockTimeDiff(start_block_number, end_block_number):
  start_block_timestamp = await getBlockTimestamp(start_block_number)
  end_block_timestamp = await getBlockTimestamp(end_block_number)

  return start_block_timestamp - end_block_timestamp