from rag_project.query_microservice.services.celery_app import celery_app

if __name__ == "__main__":
    celery_app.worker_main()
