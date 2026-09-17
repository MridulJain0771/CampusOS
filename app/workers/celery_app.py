from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "campusos",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)
celery_app.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
)
celery_app.autodiscover_tasks(["app.workers"])
