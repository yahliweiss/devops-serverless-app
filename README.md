# DevOps Serverless App

An automated serverless application on AWS, defined entirely as Infrastructure as Code
with the AWS CDK (Python). On invocation, a Lambda function lists every object in an S3
bucket and publishes an execution report to an SNS topic, which fans the message out to a
confirmed email subscriber.

## Architecture

```
                         ┌──────────────────────────┐
   cdk deploy  ─────────▶│  S3 bucket                │
   (uploads sample_files)│  (sample_files/ contents) │
                         └────────────┬──────────────┘
                                      │ s3:ListBucket / GetObject (read-only)
                                      ▼
   manual invoke ───────▶┌──────────────────────────┐   sns:Publish   ┌──────────────┐
   (CLI / boto3 script)  │  Lambda (Python 3.12)    │ ───────────────▶│  SNS topic   │
                         │  lists objects, publishes│                 └──────┬───────┘
                         └──────────────────────────┘                        │ email
                                                                             ▼
                                                                     subscribed inbox
```

The Lambda runs with a least-privilege IAM role: basic execution (CloudWatch Logs),
read-only access to **this** bucket, and publish access to **this** topic only.

## Repository Layout

| Path | Purpose |
|------|---------|
| `infrastructure/` | AWS CDK (Python) app defining all resources |
| `infrastructure/serverless_app/serverless_app_stack.py` | The stack: S3, Lambda, IAM, SNS |
| `lambda/handler.py` | Lambda function code |
| `sample_files/` | Files uploaded to S3 during deployment |
| `scripts/invoke_lambda.py` | Manual test script (invokes the Lambda) |
| `.github/workflows/deploy.yml` | GitHub Actions workflow (manual deploy) |

## Tools & Frameworks

- **AWS CDK v2 (Python)** — Infrastructure as Code
- **AWS Lambda (Python 3.12)** — compute
- **Amazon S3** — object storage
- **Amazon SNS** — email notifications
- **AWS IAM** — least-privilege role
- **boto3** — AWS SDK used by the Lambda and the test script
- **GitHub Actions** — CI/CD (manual `workflow_dispatch` trigger)
- **Node.js** — required only to run the CDK CLI

## Prerequisites

- An AWS account with credentials configured (`aws configure`)
- Python 3.12+ and Node.js 20+
- AWS CDK CLI: `npm install -g aws-cdk` (or use `npx aws-cdk`)

## Setup & Deployment

All CDK commands run from the `infrastructure/` directory.

```bash
cd infrastructure

# 1. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Bootstrap the environment (first time per account/region only)
cdk bootstrap

# 4. Deploy — pass your email for the SNS subscription
cdk deploy -c subscription_email=you@example.com
```

The email is a parameter. If you omit `-c subscription_email=...`, the stack falls back to
the placeholder `[INSERT_YOUR_EMAIL_HERE]`, which AWS will reject — so always pass a real
address.

On success, the stack outputs the bucket name, function name, and topic ARN.

### Deploying via GitHub Actions

The workflow in `.github/workflows/deploy.yml` is **manually triggered**
(`workflow_dispatch`). Before using it, add these repository secrets:

- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`

Then go to **Actions → Deploy Infrastructure → Run workflow**, enter the
`subscription_email` input, and run it.

## ⚠️ Important: Confirm the SNS Email Subscription

After the **first** deployment, AWS SNS sends a confirmation email to the subscribed
address with the subject *"AWS Notification - Subscription Confirmation"*. **You must click
the "Confirm subscription" link in that email.** Until you do, the subscription stays in
`PendingConfirmation` and **no notifications will be delivered**.

Check the current status with:

```bash
aws sns list-subscriptions --query 'Subscriptions[].[Endpoint,SubscriptionArn]' --output text
```

## Running the Manual Test

With the stack deployed and your virtualenv active:

```bash
# The script depends on boto3 (first time only)
pip install -r scripts/requirements.txt

# From the repo root — auto-discovers the function name from the stack outputs
python scripts/invoke_lambda.py

# Optional overrides
python scripts/invoke_lambda.py --stack ServerlessAppStack --region us-east-1
```

The script invokes the Lambda, prints the `StatusCode` and JSON payload (the bucket name
and the list of objects), and the function publishes a report to SNS — which arrives in the
confirmed inbox.

You can also invoke it directly with the AWS CLI:

```bash
aws lambda invoke --function-name <FunctionName> response.json && cat response.json
```

(`<FunctionName>` is the `FunctionName` value from the `cdk deploy` outputs.)

## Cleanup

To remove all resources:

```bash
cd infrastructure
cdk destroy
```

The S3 bucket is configured with `auto_delete_objects`, so its contents are removed
automatically on destroy.
