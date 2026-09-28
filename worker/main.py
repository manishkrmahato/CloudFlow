import json
import logging
import time
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select

from app.aws import s3, sqs
from app.config import settings
from app.database import SessionLocal
from app.models import Job, JobStatus
from app.operations import InvalidImage, process_image


logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

logger = logging.getLogger("cloudflow.worker")


def process_message(message: dict) -> bool:
    receipt = message["ReceiptHandle"]

    try:
        job_id = UUID(message["Body"])
    except (ValueError, KeyError):
        logger.error("Discarding malformed queue message")
        sqs().delete_message(
            QueueUrl=settings.aws_sqs_queue_url,
            ReceiptHandle=receipt,
        )
        return True

    with SessionLocal() as db:
        job = db.scalar(select(Job).where(Job.id == job_id))

        if job is None:
            logger.warning("Job %s no longer exists; acknowledging message", job_id)
            sqs().delete_message(
                QueueUrl=settings.aws_sqs_queue_url,
                ReceiptHandle=receipt,
            )
            return True

        if job.status == JobStatus.COMPLETED:
            sqs().delete_message(
                QueueUrl=settings.aws_sqs_queue_url,
                ReceiptHandle=receipt,
            )
            return True

        job.status = JobStatus.PROCESSING
        job.attempt_count += 1
        job.started_at = datetime.now(timezone.utc)
        job.error_message = None
        db.commit()

        input_key = job.input_s3_key
        user_id = job.user_id
        operation_json = job.options_json
        filename = job.filename

    try:
        source = s3().get_object(
            Bucket=settings.aws_s3_bucket,
            Key=input_key,
        )["Body"].read()

        output, extension, content_type = process_image(
            source,
            json.loads(operation_json),
        )

        output_key = f"results/{user_id}/{job_id}/result.{extension}"

        s3().put_object(
            Bucket=settings.aws_s3_bucket,
            Key=output_key,
            Body=output,
            ContentType=content_type,
        )

        with SessionLocal() as db:
            job = db.scalar(select(Job).where(Job.id == job_id))

            if job and job.status != JobStatus.COMPLETED:
                job.output_s3_key = output_key
                job.status = JobStatus.COMPLETED
                job.error_message = None
                job.completed_at = datetime.now(timezone.utc)
                db.commit()

        sqs().delete_message(
            QueueUrl=settings.aws_sqs_queue_url,
            ReceiptHandle=receipt,
        )

        logger.info("Completed job %s (%s)", job_id, filename)
        return True

    except InvalidImage as exc:
        logger.warning("Job %s rejected: %s", job_id, exc)

        try:
            with SessionLocal() as db:
                job = db.scalar(select(Job).where(Job.id == job_id))

                if job and job.status != JobStatus.COMPLETED:
                    job.status = JobStatus.FAILED
                    job.error_message = str(exc)[:1000]
                    db.commit()

            sqs().delete_message(
                QueueUrl=settings.aws_sqs_queue_url,
                ReceiptHandle=receipt,
            )

            return True

        except Exception:
            logger.exception("Could not finalize invalid job %s", job_id)
            return False

    except Exception as exc:
        logger.exception("Job %s failed; SQS will redeliver it", job_id)

        try:
            with SessionLocal() as db:
                job = db.scalar(select(Job).where(Job.id == job_id))

                if job and job.status != JobStatus.COMPLETED:
                    job.status = JobStatus.FAILED
                    job.error_message = str(exc)[:1000]
                    db.commit()

        except Exception:
            logger.exception("Could not persist failure for job %s", job_id)

        return False


def run():
    if not settings.aws_sqs_queue_url:
        raise RuntimeError("AWS_SQS_QUEUE_URL must be configured")

    logger.info("Worker polling SQS in %s", settings.aws_region)

    while True:
        try:
            result = sqs().receive_message(
                QueueUrl=settings.aws_sqs_queue_url,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=20,
                VisibilityTimeout=settings.aws_sqs_visibility_timeout,
                AttributeNames=["ApproximateReceiveCount"],
            )

            for message in result.get("Messages", []):
                process_message(message)

        except Exception:
            logger.exception("Queue poll failed")
            time.sleep(5)


if __name__ == "__main__":
    run()
