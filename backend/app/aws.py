import boto3
from boto3.s3.transfer import TransferConfig
from botocore.config import Config
from .config import settings


def client(service: str):
    kwargs = {
        "region_name": settings.aws_region,
        "config": Config(
            retries={
                "max_attempts": 4,
                "mode": "standard",
            }
        ),
    }

    if settings.aws_endpoint_url:
        kwargs["endpoint_url"] = settings.aws_endpoint_url

    session = (
        boto3.Session(
            profile_name=settings.aws_profile,
            region_name=settings.aws_region,
        )
        if settings.aws_profile
        else boto3.Session(region_name=settings.aws_region)
    )

    return session.client(service, **kwargs)


def s3():
    return client("s3")


def sqs():
    return client("sqs")


def s3_transfer_config():
    return TransferConfig(
        multipart_threshold=1024 * 1024,
        multipart_chunksize=1024 * 1024,
        max_concurrency=4,
        use_threads=True,
    )