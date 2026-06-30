# import asyncio
# import sys
# import os

# # Add the current directory to sys.path to allow imports
# sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# # from dto.Query_dto import NewQueryRequest
# # from services.worker import start_workers, task_queue
# # from services.pubsub import pubsub

# async def test_flow():
#     # 1. Start workers
#     print("--- Starting workers ---")
#     start_workers(num_workers=2)

#     # 2. Simulate a query request
#     payload = NewQueryRequest(
#         text="What is this document about?",
#         history="[]",
#         tenant_id="test_tenant",
#         job_id="job_123"
#     )

#     print(f"--- Queueing job: {payload.job_id} ---")
#     await task_queue.put({
#         "job_id": payload.job_id,
#         "payload": payload
#     })

#     # 3. Wait for a bit to let the worker process
#     # Note: In a real test, you'd wait for the pubsub output or a task completion event
#     print("--- Waiting for processing ---")
#     await asyncio.sleep(5) 
    
#     print("--- Test finished ---")
#     print("Check the console output above for [DEMO PUB/SUB] and Worker logs.")

# if __name__ == "__main__":
#     try:
#         asyncio.run(test_flow())
#     except KeyboardInterrupt:
#         pass
