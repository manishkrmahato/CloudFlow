# Interview discussion

- SQS decouples upload latency from CPU work; a queue buffers bursty traffic.
- S3 stores binaries while PostgreSQL stores relationships and state.
- SQS standard delivery is at-least-once. Worker checks COMPLETED and writes deterministic keys for idempotency.
- A visibility timeout temporarily hides a message. If the worker does not delete it, it becomes visible again. Redrive policy moves repeated receives to a DLQ.
- SQS redrive is receive-count based, not exponential backoff. The user retry endpoint deliberately enqueues a fresh attempt.
- API and worker are separate so upload requests do not wait on image manipulation. Workers can later scale independently.
- S3 upload, DB commit, and SQS send cannot be atomic together. The app cleans up source objects on initial DB failure and exposes SQS send failure as a retryable FAILED row.
- Current scaling limit is the single EC2 instance and local PostgreSQL. A next step could move DB to RDS and add worker instances, metrics, and deployment automation.
- Debug a stuck job by checking DB status, API/worker logs, queue visible/in-flight counts, and DLQ contents.
