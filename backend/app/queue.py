from uuid import UUID
from .aws import sqs
from .config import settings


def send_job(job_id: UUID) -> None:
    if not settings.aws_sqs_queue_url:
        raise RuntimeError("AWS_SQS_QUEUE_URL is not configured")
    sqs().send_message(QueueUrl=settings.aws_sqs_queue_url, MessageBody=str(job_id))
