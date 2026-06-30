import asyncio
import sys
import os

# Add the current directory to sys.path to allow imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from rag_project.query_microservice.dto.Query_dto import NewQueryRequest
from rag_project.query_microservice.services.worker import start_workers, task_queue

async def test_flow():
    # 1. Start workers
    print("--- Starting workers ---")
    start_workers(num_workers=2)

    # 2. Simulate a query request
    payload = NewQueryRequest(
        text="What is this document about?",
        tenant_id=1,
    )

    print("--- Queueing job ---")
    await task_queue.put({
        "job_id": "job_123",
        "payload": payload
    })

    # 3. Wait for a bit to let the worker process
    print("--- Waiting for processing ---")
    await asyncio.sleep(5)

    print("--- Test finished ---")
    print("Check the console output above for worker logs.")

if __name__ == "__main__":
    try:
        asyncio.run(test_flow())
    except KeyboardInterrupt:
        pass
