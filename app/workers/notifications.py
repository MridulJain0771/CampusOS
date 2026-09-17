import logging

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def dispatch_notification(self, channel: str, destination: str, title: str, message: str) -> dict:
    """Portfolio-safe notification delivery stub.

    Real deployments would connect this task to email/SMS/push providers. The queue,
    retry and acknowledgement semantics are real and testable without external credentials.
    """
    logger.info("notification_dispatch", extra={"channel": channel, "destination": destination, "title": title})
    return {"channel": channel, "destination": destination, "title": title, "message": message, "status": "dispatched"}
