# Architecture and failure behavior

The browser calls FastAPI with bearer JWT auth. FastAPI validates input and ownership, stores source objects in S3, records jobs in PostgreSQL, and sends UUID messages to SQS. A separate worker runs Pillow transformations and updates the job. PostgreSQL stores structured metadata; S3 stores binaries.

One uploaded file creates one job. The API returns 202 after storage, row creation, and enqueue. The worker writes output to a deterministic key and commits COMPLETED before deleting the message. If it dies before deletion, SQS redelivers after the visibility timeout. Completed jobs are acknowledged without repeating work. If output upload succeeds but the DB commit fails, the next delivery overwrites the same output key.

S3, PostgreSQL, and SQS are not one transaction. The API tries to delete an uploaded source if DB persistence fails. A queue send failure becomes a visible FAILED job for user retry. Worker failures are persisted where possible and leave the message undeleted. Standard SQS queues are at-least-once and unordered; the configured redrive count sends repeatedly failing jobs to the DLQ.

React handles upload and polling. FastAPI handles auth, ownership, validation, and download signing. PostgreSQL is the job source of truth. S3 stays private. SQS buffers requests away from the worker. CloudWatch receives EC2 container logs. EC2 runs Compose and uses an IAM instance role.

Current limits: single EC2 host, database volume on that host, no HA/autoscaling or push updates. Later improvements could include RDS, worker scaling, metrics, rate limits, S3 lifecycle rules, and infrastructure as code.
