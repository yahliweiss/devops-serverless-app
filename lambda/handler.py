"""Lambda function that lists objects in an S3 bucket and publishes a summary to SNS."""

import json
import logging
import os
from datetime import datetime, timezone

import boto3
from botocore.exceptions import BotoCoreError, ClientError

# Configure logging for CloudWatch
logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client("s3")
sns = boto3.client("sns")

# Validate environment variables at initialization
try:
    BUCKET_NAME = os.environ["BUCKET_NAME"]
    TOPIC_ARN = os.environ["TOPIC_ARN"]
    if not BUCKET_NAME:
        raise ValueError("BUCKET_NAME environment variable is empty")
    if not TOPIC_ARN:
        raise ValueError("TOPIC_ARN environment variable is empty")
except KeyError as e:
    logger.error(f"Missing required environment variable: {e}")
    raise
except ValueError as e:
    logger.error(f"Invalid environment variable: {e}")
    raise


def handler(event, context):
    """List all objects in the configured S3 bucket and publish details to SNS.

    Returns:
        dict: Lambda response with statusCode and body containing result or error details.
    """
    try:
        logger.info(f"Starting Lambda execution for bucket: {BUCKET_NAME}")

        # --- S3 Listing with Error Handling ---
        try:
            keys = []
            paginator = s3.get_paginator("list_objects_v2")
            page_count = 0

            for page in paginator.paginate(Bucket=BUCKET_NAME):
                page_count += 1
                for obj in page.get("Contents", []):
                    keys.append(obj["Key"])

            logger.info(
                f"Successfully listed {len(keys)} objects from {BUCKET_NAME} in {page_count} page(s)"
            )

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_msg = e.response.get("Error", {}).get("Message", str(e))

            if error_code == "NoSuchBucket":
                logger.error(f"Bucket does not exist: {BUCKET_NAME}")
                return error_response(404, f"Bucket not found: {BUCKET_NAME}")
            elif error_code == "AccessDenied":
                logger.error(
                    f"Access denied to bucket: {BUCKET_NAME}. Check IAM permissions."
                )
                return error_response(
                    403,
                    "Access denied to S3 bucket. Check Lambda IAM role permissions.",
                )
            else:
                logger.error(f"S3 API Error ({error_code}): {error_msg}")
                return error_response(500, f"S3 Error ({error_code}): {error_msg}")

        except BotoCoreError as e:
            logger.error(f"Boto3 connection error: {str(e)}")
            return error_response(500, f"AWS connection error: {str(e)}")

        # --- Generate Report Message ---
        try:
            timestamp = datetime.now(timezone.utc).isoformat()

            # Format object list safely
            object_list = ""
            if keys:
                # Truncate if too many objects to avoid SNS message size limits (256KB)
                max_objects = 100
                displayed_keys = keys[:max_objects]
                object_list = "\n".join(f"  - {k}" for k in displayed_keys)
                if len(keys) > max_objects:
                    object_list += f"\n  ... and {len(keys) - max_objects} more objects"
            else:
                object_list = "  (none)"

            message = (
                f"Lambda execution report ({timestamp})\n"
                f"Bucket: {BUCKET_NAME}\n"
                f"Object count: {len(keys)}\n"
                f"Objects:\n{object_list}"
            )
            logger.info(f"Generated message for SNS publish ({len(message)} bytes)")

        except Exception as e:
            logger.error(f"Error generating message: {str(e)}")
            return error_response(500, f"Error generating report message: {str(e)}")

        # --- SNS Publish with Error Handling ---
        try:
            response = sns.publish(
                TopicArn=TOPIC_ARN,
                Subject="S3 Bucket Listing Report",
                Message=message,
            )
            logger.info(
                f"Successfully published SNS message. MessageId: {response.get('MessageId')}"
            )

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_msg = e.response.get("Error", {}).get("Message", str(e))

            if error_code == "NotFound":
                logger.error(f"SNS topic does not exist: {TOPIC_ARN}")
                return error_response(
                    404, "SNS topic not found. Check TOPIC_ARN environment variable."
                )
            elif error_code == "AuthorizationError":
                logger.error(f"Permission denied to publish to SNS topic: {TOPIC_ARN}")
                return error_response(
                    403,
                    "Permission denied to SNS topic. Check Lambda IAM role permissions.",
                )
            else:
                logger.error(f"SNS API Error ({error_code}): {error_msg}")
                return error_response(500, f"SNS Error ({error_code}): {error_msg}")

        except BotoCoreError as e:
            logger.error(f"Boto3 SNS connection error: {str(e)}")
            return error_response(500, f"SNS connection error: {str(e)}")

        # --- Success Response ---
        logger.info("Lambda execution completed successfully")
        return success_response(
            bucket=BUCKET_NAME,
            object_count=len(keys),
            objects=keys,
            sns_message_id=response.get("MessageId"),
        )

    except Exception as e:
        # Catch-all for unexpected errors
        logger.error(
            f"Unexpected error in handler: {type(e).__name__}: {str(e)}", exc_info=True
        )
        return error_response(500, f"Unexpected error: {str(e)}")


def success_response(
    bucket: str, object_count: int, objects: list, sns_message_id: str
) -> dict:
    """Format successful Lambda response."""
    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "success": True,
                "bucket": bucket,
                "object_count": object_count,
                "objects": objects,
                "sns_message_id": sns_message_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ),
        "headers": {"Content-Type": "application/json"},
    }


def error_response(status_code: int, error_message: str) -> dict:
    """Format error Lambda response."""
    return {
        "statusCode": status_code,
        "body": json.dumps(
            {
                "success": False,
                "error": error_message,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ),
        "headers": {"Content-Type": "application/json"},
    }
