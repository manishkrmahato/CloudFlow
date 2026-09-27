# AWS setup and deployment (ap-south-1)

Create resources in the Mumbai region. Use a non-root IAM identity. Never put credentials in source files. Local development uses CLI profile `default`; EC2 uses an instance role with no long-lived keys.

## 1. Verify CLI identity and choose a bucket name

PowerShell:
```powershell
aws sts get-caller-identity --profile default
$Region = "ap-south-1"
$AccountId = (aws sts get-caller-identity --profile default --output json | ConvertFrom-Json).Account
$Bucket = "cloudflow-$AccountId-manis"
```
If that name is already taken, append a unique suffix. S3 bucket creation outside us-east-1 needs the chosen `LocationConstraint`. [AWS CLI create-bucket reference](https://docs.aws.amazon.com/cli/latest/reference/s3api/create-bucket.html).

## 2. Create a private S3 bucket

```powershell
aws s3api create-bucket --bucket $Bucket --region $Region --create-bucket-configuration LocationConstraint=$Region --profile default
aws s3api put-public-access-block --bucket $Bucket --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true --profile default
aws s3api put-bucket-encryption --bucket $Bucket --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}' --profile default
```

## 3. Create SQS queue and DLQ

Create the DLQ first. This example sets a 180-second visibility timeout, 20-second long polling, and redrives after four receives. Keep the worker setting and queue timeout aligned. SQS moves messages to the DLQ when receive count exceeds the redrive policy threshold; it does not promise exponential backoff. [SQS redrive policy reference](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html).

```powershell
$DlqUrl = aws sqs create-queue --queue-name cloudflow-jobs-dlq --region $Region --profile default --query QueueUrl --output text
$DlqArn = aws sqs get-queue-attributes --queue-url $DlqUrl --attribute-names QueueArn --region $Region --profile default --query Attributes.QueueArn --output text
$Redrive = @{ deadLetterTargetArn = $DlqArn; maxReceiveCount = "4" } | ConvertTo-Json -Compress
$QueueAttributes = @{ VisibilityTimeout = "180"; ReceiveMessageWaitTimeSeconds = "20"; RedrivePolicy = $Redrive } | ConvertTo-Json -Compress
$QueueUrl = aws sqs create-queue --queue-name cloudflow-jobs --attributes $QueueAttributes --region $Region --profile default --query QueueUrl --output text
$QueueUrl
```

Set `AWS_S3_BUCKET` and `AWS_SQS_QUEUE_URL` in `.env`. The queue URL is returned by the script; use it exactly.

## 4. IAM role for EC2 and CloudWatch

Replace the bucket and account placeholders in `docs/iam-policy.json`. Create a role whose trust policy is `docs/ec2-trust-policy.json`, attach the application policy as an inline policy, then add the role to an instance profile and associate that profile to EC2. The role only grants object operations on the named bucket, message operations on the project queue, and CloudWatch log writing.

Example commands from repository root after editing the policy:
```powershell
aws iam create-role --role-name CloudFlowEc2Role --assume-role-policy-document file://docs/ec2-trust-policy.json --profile default
aws iam put-role-policy --role-name CloudFlowEc2Role --policy-name CloudFlowRuntime --policy-document file://docs/iam-policy.json --profile default
aws iam create-instance-profile --instance-profile-name CloudFlowEc2Profile --profile default
aws iam add-role-to-instance-profile --instance-profile-name CloudFlowEc2Profile --role-name CloudFlowEc2Role --profile default
```
Attach the instance profile during launch or using the EC2 console. Allow several seconds for IAM propagation.

## 5. Run locally on Windows

Use Docker Desktop with Compose and AWS CLI v2. Ensure `%USERPROFILE%\.aws\credentials` and config contain profile `default`. Copy `.env.example` to `.env`, set the bucket/queue URL, and replace the sample local PostgreSQL password and JWT key. The DB password should be alphanumeric because Compose builds a URL from it.

Generate a JWT secret:
```powershell
[Convert]::ToBase64String([Security.Cryptography.RandomNumberGenerator]::GetBytes(48))
docker compose up --build
```
Open http://localhost:8080. API health: http://localhost:8080/health. Nginx proxies API paths to FastAPI. API startup applies Alembic migrations. The app mounts AWS CLI files read-only.

## 6. EC2 deployment

Launch an Ubuntu EC2 instance in ap-south-1 and attach the instance profile above. Permit SSH only from your IP and HTTP 8080 only for initial testing; keep PostgreSQL private. Install Docker Engine and Compose plugin using the current official Ubuntu instructions. Clone your GitHub repository and copy `.env.example` to `.env`. Set bucket/queue values and a strong JWT secret, set a strong alphanumeric `POSTGRES_PASSWORD`, and leave `AWS_PROFILE=` blank so boto3 uses the instance role.

Start using the EC2 override. It removes local AWS credential mounts and sends API/worker/frontend container logs to CloudWatch:
```bash
docker compose -f docker-compose.yml -f compose.ec2.yml up -d --build
docker compose -f docker-compose.yml -f compose.ec2.yml ps
docker compose -f docker-compose.yml -f compose.ec2.yml logs -f api worker
```
Set up DNS/TLS and a reverse proxy before making the prototype public. Change the published port/security group if needed.

## 7. CloudWatch and verification

The EC2 override creates `/cloudflow/api`, `/cloudflow/worker`, and `/cloudflow/frontend` log groups via Docker's awslogs driver. Inspect CloudWatch Logs in ap-south-1. Worker logs include job IDs and failure details, not file contents.

```powershell
aws sts get-caller-identity --profile default
aws s3api head-bucket --bucket $Bucket --profile default
aws sqs get-queue-attributes --queue-url $QueueUrl --attribute-names ApproximateNumberOfMessages --region $Region --profile default
docker compose logs -f worker
```
Upload a test image; expect QUEUED/PROCESSING then COMPLETED and a working download. Messages that fail repeatedly move to the DLQ. Inspect it with `aws sqs receive-message --queue-url $DlqUrl --region $Region --profile default`.

## 8. Cleanup and troubleshooting

Stop containers with `docker compose down`; `-v` removes local PostgreSQL data. Stop EC2 when idle or terminate it when done. S3 data and queues are separate resources: delete test objects, then queues, then empty and delete the bucket. Check current AWS charges.

- **Credentials unavailable:** run `aws sts get-caller-identity --profile default`; verify the local AWS folder mount/profile.
- **SQS AccessDenied:** check region, URL and role/profile send/receive/delete permissions.
- **S3 access denied:** verify bucket, region and object ARN.
- **Stuck jobs:** inspect DB status, API/worker logs, queue counts and DLQ; verify both processes use the same queue URL.
- **DB startup errors:** `docker compose logs db`; wait for health check.
- **Port conflict:** change frontend host port and adjust CORS if making cross-origin requests.
