import asyncio
from typing import List
from rag_project.query.services.query import run_query
from rag_project.query.services.prompt import prompt_builder
from rag_project.config.db_config import SessionLocal

# Global queue for background tasks
task_queue: asyncio.Queue = asyncio.Queue()

async def worker(worker_id: int):
    """
    Background worker that processes tasks from the queue.
    """
    print(f"[*] Worker-{worker_id} started and waiting for tasks...")
    while True:
        task = await task_queue.get()
        try:
            job_id = task['job_id']
            payload = task['payload']

            print(f"[!] Worker-{worker_id} processing job: {job_id}")

            prompt = prompt_builder(query=payload.text)

            with SessionLocal() as db:
                result_data = await run_query(
                    tenant_id=payload.tenant_id,
                    user_query=payload.text,
                    prompt=prompt,
                    db=db,
                )

            print(f"[+] Worker-{worker_id} completed job {job_id}: {result_data['answer']}")

        except Exception as e:
            print(f"[X] Worker-{worker_id} error processing job {task.get('job_id')}: {e}")
        finally:
            task_queue.task_done()

# List to keep track of worker tasks
worker_tasks: List[asyncio.Task] = []

def start_workers(num_workers: int = 3):
    """
    Starts the background workers.
    """
    global worker_tasks
    if worker_tasks:
        print("[!] Workers are already running.")
        return

    for i in range(num_workers):
        t = asyncio.create_task(worker(i))
        worker_tasks.append(t)
    print(f"[*] Started {num_workers} background workers.")
