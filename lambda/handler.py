"""Lambda function that lists objects in an S3 bucket and publishes a summary to SNS."""

import json
import os
from datetime import datetime, timezone

import boto3

s3 = boto3.client("s3")
sns = boto3.client("sns")

BUCKET_NAME = os.environ["BUCKET_NAME"]
TOPIC_ARN = os.environ["TOPIC_ARN"]


def handler(event, context):
    """List all objects in the configured S3 bucket and publish details to SNS."""
    keys = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BUCKET_NAME):
        for obj in page.get("Contents", []):
            keys.append(obj["Key"])

    timestamp = datetime.now(timezone.utc).isoformat()
    message = (
        f"Lambda execution report ({timestamp})\n"
        f"Bucket: {BUCKET_NAME}\n"
        f"Object count: {len(keys)}\n"
        f"Objects:\n" + ("\n".join(f"  - {k}" for k in keys) if keys else "  (none)")
    )

    sns.publish(
        TopicArn=TOPIC_ARN,
        Subject="S3 Bucket Listing Report",
        Message=message,
    )

    return {
        "statusCode": 200,
        "body": json.dumps({"bucket": BUCKET_NAME, "object_count": len(keys), "objects": keys}),
    }
