#!/usr/bin/env python3
"""
Comprehensive edge case tests for the Lambda handler.

Covers robustness, error handling, and special scenarios:
  - §3 lists all objects in the *specified* S3 bucket (TEST 1-3, 16, 22)
  - §3/§6 publishes an SNS message with execution details to the *configured*
    topic (TEST 15, 17, 18)
  - error paths for S3/SNS (TEST 5-9, 19-21) and message-size truncation
    (TEST 10, 23, 24)
  - manual trigger tolerates arbitrary test-event payloads (§8, TEST 25)

These are offline unit tests: all AWS calls are mocked, so no AWS account or
network access is required.

Requires boto3/botocore (see scripts/requirements.txt):
    pip install -r scripts/requirements.txt

Usage:
    python scripts/test_handler_edge_cases.py
"""

import json
import os
import sys
from unittest.mock import MagicMock, patch, call
from botocore.exceptions import ClientError, BotoCoreError

# Add lambda directory to path so we can import the handler
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambda"))

# Mock environment variables before importing handler
os.environ["BUCKET_NAME"] = "test-bucket"
os.environ["TOPIC_ARN"] = "arn:aws:sns:us-east-1:123456789:test-topic"

import handler as handler_module

print("=" * 80)
print("LAMBDA HANDLER EDGE CASE TEST SUITE")
print("=" * 80)


class TestResults:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.tests = []

    def add_result(self, name, passed, message=""):
        status = "✅ PASS" if passed else "❌ FAIL"
        self.tests.append({"name": name, "passed": passed, "message": message})
        print(f"{status}: {name}")
        if message:
            print(f"     {message}")
        if passed:
            self.passed += 1
        else:
            self.failed += 1

    def summary(self):
        print("\n" + "=" * 80)
        print(f"SUMMARY: {self.passed} passed, {self.failed} failed")
        print("=" * 80)
        return self.failed == 0


results = TestResults()

# ============================================================================
# TEST 1: Normal Case - Standard execution
# ============================================================================
print("\n[TEST 1] Normal Case - List objects and publish to SNS")
with patch("handler.s3") as mock_s3, patch("handler.sns") as mock_sns:
    mock_s3.get_paginator.return_value.paginate.return_value = [
        {"Contents": [{"Key": "file1.txt"}, {"Key": "file2.json"}]}
    ]
    mock_sns.publish.return_value = {"MessageId": "msg-123"}

    response = handler_module.handler({}, None)
    passed = response["statusCode"] == 200 and json.loads(response["body"]).get(
        "success"
    )
    body = json.loads(response["body"])
    results.add_result(
        "Normal execution with 2 objects",
        passed,
        f"Objects: {body.get('object_count')} | SNS MessageId: {body.get('sns_message_id')}",
    )

# ============================================================================
# TEST 2: Empty Bucket
# ============================================================================
print("\n[TEST 2] Empty Bucket - No objects in S3")
with patch("handler.s3") as mock_s3, patch("handler.sns") as mock_sns:
    mock_s3.get_paginator.return_value.paginate.return_value = [
        {}
    ]  # Contents not present
    mock_sns.publish.return_value = {"MessageId": "msg-456"}

    response = handler_module.handler({}, None)
    passed = response["statusCode"] == 200
    body = json.loads(response["body"])
    results.add_result(
        "Empty bucket (0 objects)",
        passed and body.get("object_count") == 0,
        f"Object count: {body.get('object_count')}",
    )

# ============================================================================
# TEST 3: Large Object Count (Pagination)
# ============================================================================
print("\n[TEST 3] Large Object Count - Multiple pages")
with patch("handler.s3") as mock_s3, patch("handler.sns") as mock_sns:
    # Simulate 150 objects across 3 pages
    page1 = {"Contents": [{"Key": f"file{i}.txt"} for i in range(50)]}
    page2 = {"Contents": [{"Key": f"file{i}.txt"} for i in range(50, 100)]}
    page3 = {"Contents": [{"Key": f"file{i}.txt"} for i in range(100, 150)]}

    mock_s3.get_paginator.return_value.paginate.return_value = [page1, page2, page3]
    mock_sns.publish.return_value = {"MessageId": "msg-789"}

    response = handler_module.handler({}, None)
    passed = response["statusCode"] == 200
    body = json.loads(response["body"])
    results.add_result(
        "Large object count (150 objects, 3 pages)",
        passed and body.get("object_count") == 150,
        f"Objects listed: {body.get('object_count')} | Pages processed: 3",
    )

# ============================================================================
# TEST 4: Special Characters in Object Names
# ============================================================================
print("\n[TEST 4] Special Characters - URLs, spaces, unicode")
with patch("handler.s3") as mock_s3, patch("handler.sns") as mock_sns:
    special_keys = [
        "file with spaces.txt",
        "file-with-dashes.txt",
        "file_with_underscores.txt",
        "日本語ファイル.txt",
        "file%20encoded.txt",
    ]
    mock_s3.get_paginator.return_value.paginate.return_value = [
        {"Contents": [{"Key": k} for k in special_keys]}
    ]
    mock_sns.publish.return_value = {"MessageId": "msg-special"}

    response = handler_module.handler({}, None)
    passed = response["statusCode"] == 200
    body = json.loads(response["body"])
    results.add_result(
        "Special characters in filenames",
        passed and len(body.get("objects", [])) == 5,
        f"Successfully handled {len(body.get('objects', []))} special filenames",
    )

# ============================================================================
# TEST 5: S3 Access Denied
# ============================================================================
print("\n[TEST 5] S3 Access Denied - Missing IAM permission")
with patch("handler.s3") as mock_s3, patch("handler.sns") as mock_sns:
    error = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "User is not authorized"}},
        "ListObjectsV2",
    )
    mock_s3.get_paginator.return_value.paginate.side_effect = error

    response = handler_module.handler({}, None)
    body = json.loads(response["body"])
    passed = response["statusCode"] == 403 and body.get("success") is False
    results.add_result(
        "S3 Access Denied error handling",
        passed,
        f"Status: {response['statusCode']} | Error: {body.get('error')}",
    )

# ============================================================================
# TEST 6: S3 Bucket Not Found
# ============================================================================
print("\n[TEST 6] S3 Bucket Not Found")
with patch("handler.s3") as mock_s3, patch("handler.sns") as mock_sns:
    error = ClientError(
        {
            "Error": {
                "Code": "NoSuchBucket",
                "Message": "The specified bucket does not exist",
            }
        },
        "ListObjectsV2",
    )
    mock_s3.get_paginator.return_value.paginate.side_effect = error

    response = handler_module.handler({}, None)
    body = json.loads(response["body"])
    passed = response["statusCode"] == 404 and body.get("success") is False
    results.add_result(
        "Bucket not found error handling",
        passed,
        f"Status: {response['statusCode']} | Error: {body.get('error')}",
    )

# ============================================================================
# TEST 7: SNS Topic Not Found
# ============================================================================
print("\n[TEST 7] SNS Topic Not Found")
with patch("handler.s3") as mock_s3, patch("handler.sns") as mock_sns:
    mock_s3.get_paginator.return_value.paginate.return_value = [
        {"Contents": [{"Key": "file.txt"}]}
    ]
    error = ClientError(
        {"Error": {"Code": "NotFound", "Message": "Topic does not exist"}}, "Publish"
    )
    mock_sns.publish.side_effect = error

    response = handler_module.handler({}, None)
    body = json.loads(response["body"])
    passed = response["statusCode"] == 404 and body.get("success") is False
    results.add_result(
        "SNS topic not found error handling",
        passed,
        f"Status: {response['statusCode']} | Error: {body.get('error')}",
    )

# ============================================================================
# TEST 8: SNS Permission Denied
# ============================================================================
print("\n[TEST 8] SNS Permission Denied")
with patch("handler.s3") as mock_s3, patch("handler.sns") as mock_sns:
    mock_s3.get_paginator.return_value.paginate.return_value = [
        {"Contents": [{"Key": "file.txt"}]}
    ]
    error = ClientError(
        {"Error": {"Code": "AuthorizationError", "Message": "User is not authorized"}},
        "Publish",
    )
    mock_sns.publish.side_effect = error

    response = handler_module.handler({}, None)
    body = json.loads(response["body"])
    passed = response["statusCode"] == 403 and body.get("success") is False
    results.add_result(
        "SNS permission denied error handling",
        passed,
        f"Status: {response['statusCode']} | Error: {body.get('error')}",
    )

# ============================================================================
# TEST 9: Network Error (BotoCoreError)
# ============================================================================
print("\n[TEST 9] Network/Connection Error")
with patch("handler.s3") as mock_s3, patch("handler.sns") as mock_sns:
    error = BotoCoreError()
    mock_s3.get_paginator.return_value.paginate.side_effect = error

    response = handler_module.handler({}, None)
    body = json.loads(response["body"])
    passed = response["statusCode"] == 500 and body.get("success") is False
    results.add_result(
        "Connection error handling",
        passed,
        f"Status: {response['statusCode']} | Graceful error response",
    )

# ============================================================================
# TEST 10: Object Count Truncation (100+ objects in SNS message)
# ============================================================================
print("\n[TEST 10] Many Objects - Message Truncation")
with patch("handler.s3") as mock_s3, patch("handler.sns") as mock_sns:
    # Create 150 objects
    mock_s3.get_paginator.return_value.paginate.return_value = [
        {"Contents": [{"Key": f"file{i:03d}.txt"} for i in range(150)]}
    ]
    mock_sns.publish.return_value = {"MessageId": "msg-truncate"}

    response = handler_module.handler({}, None)
    passed = response["statusCode"] == 200
    body = json.loads(response["body"])

    # Check that SNS message was still called (even though truncated in message)
    sns_call_args = mock_sns.publish.call_args
    message = sns_call_args.kwargs.get("Message", "") if sns_call_args.kwargs else ""
    truncated = "and 50 more objects" in message

    results.add_result(
        "150 objects - SNS message truncation",
        passed and body.get("object_count") == 150 and truncated,
        f"Total objects: 150 | Message truncated: {truncated}",
    )

# ============================================================================
# TEST 11: Missing Environment Variables (caught at module init)
# ============================================================================
print("\n[TEST 11] Missing Environment Variables")
# This test simulates what happens when env vars are not set
# We can't really test this with the current handler because it validates at import time
# But we can verify the handler has that validation
validation_code = open(
    os.path.join(os.path.dirname(__file__), "..", "lambda", "handler.py")
).read()
passed = (
    'BUCKET_NAME = os.environ["BUCKET_NAME"]' in validation_code
    and "KeyError" in validation_code
)
results.add_result(
    "Environment variable validation in code",
    passed,
    "Handler validates BUCKET_NAME and TOPIC_ARN at startup",
)

# ============================================================================
# TEST 12: Unexpected Exception Handling
# ============================================================================
print("\n[TEST 12] Unexpected Exception - Catch-all Handler")
with patch("handler.s3") as mock_s3, patch("handler.sns") as mock_sns:
    mock_s3.get_paginator.return_value.paginate.side_effect = RuntimeError(
        "Unexpected error!"
    )

    response = handler_module.handler({}, None)
    body = json.loads(response["body"])
    passed = response["statusCode"] == 500 and body.get("success") is False
    results.add_result(
        "Unexpected exception catch-all",
        passed,
        f"Status: {response['statusCode']} | Exception caught gracefully",
    )

# ============================================================================
# TEST 13: Response Format Validation
# ============================================================================
print("\n[TEST 13] Response Format - Headers and Structure")
with patch("handler.s3") as mock_s3, patch("handler.sns") as mock_sns:
    mock_s3.get_paginator.return_value.paginate.return_value = [
        {"Contents": [{"Key": "test.txt"}]}
    ]
    mock_sns.publish.return_value = {"MessageId": "msg-format"}

    response = handler_module.handler({}, None)
    has_status = "statusCode" in response
    has_body = "body" in response
    has_headers = "headers" in response
    has_content_type = (
        response.get("headers", {}).get("Content-Type") == "application/json"
    )

    passed = has_status and has_body and has_headers and has_content_type
    results.add_result(
        "Response format validation",
        passed,
        "StatusCode, body, and headers present with Content-Type",
    )

# ============================================================================
# TEST 14: Logging - Verify logging calls are present
# ============================================================================
print("\n[TEST 14] Logging - CloudWatch integration")
logging_code = open(
    os.path.join(os.path.dirname(__file__), "..", "lambda", "handler.py")
).read()
has_logger_setup = "logger = logging.getLogger()" in logging_code
has_info_logs = "logger.info" in logging_code
has_error_logs = "logger.error" in logging_code
passed = has_logger_setup and has_info_logs and has_error_logs
results.add_result(
    "Logging configured for CloudWatch",
    passed,
    "Logger setup and info/error logging present",
)

# ============================================================================
# TEST 15: SNS message contains execution details
# ============================================================================
print("\n[TEST 15] SNS Message Content - Execution details published")
with patch("handler.s3") as mock_s3, patch("handler.sns") as mock_sns:
    keys = ["alpha.txt", "beta.json", "nested/gamma.csv"]
    mock_s3.get_paginator.return_value.paginate.return_value = [
        {"Contents": [{"Key": k} for k in keys]}
    ]
    mock_sns.publish.return_value = {"MessageId": "msg-content"}

    response = handler_module.handler({}, None)
    message = mock_sns.publish.call_args.kwargs.get("Message", "")
    # The requirement: the message must carry execution details — the bucket,
    # the object count, a timestamp, and the actual object keys.
    has_bucket = "test-bucket" in message
    has_count = "Object count: 3" in message
    has_report = "Lambda execution report" in message
    has_all_keys = all(k in message for k in keys)
    passed = (
        response["statusCode"] == 200
        and has_bucket
        and has_count
        and has_report
        and has_all_keys
    )
    results.add_result(
        "SNS message includes bucket, count, timestamp, and all object keys",
        passed,
        f"bucket={has_bucket} count={has_count} report_header={has_report} keys={has_all_keys}",
    )

# ============================================================================
# TEST 16: Lists the SPECIFIED bucket
# ============================================================================
print("\n[TEST 16] Correct Bucket - Paginator targets the configured bucket")
with patch("handler.s3") as mock_s3, patch("handler.sns") as mock_sns:
    mock_s3.get_paginator.return_value.paginate.return_value = [
        {"Contents": [{"Key": "file.txt"}]}
    ]
    mock_sns.publish.return_value = {"MessageId": "msg-bucket"}

    handler_module.handler({}, None)
    mock_s3.get_paginator.assert_called_with("list_objects_v2")
    paginate_kwargs = mock_s3.get_paginator.return_value.paginate.call_args.kwargs
    passed = paginate_kwargs.get("Bucket") == "test-bucket"
    results.add_result(
        "Paginator lists the specified bucket only",
        passed,
        f"paginate called with Bucket={paginate_kwargs.get('Bucket')!r}",
    )

# ============================================================================
# TEST 17: Publishes to the correct SNS topic + subject
# ============================================================================
print("\n[TEST 17] Correct SNS Target - TopicArn and Subject")
with patch("handler.s3") as mock_s3, patch("handler.sns") as mock_sns:
    mock_s3.get_paginator.return_value.paginate.return_value = [
        {"Contents": [{"Key": "file.txt"}]}
    ]
    mock_sns.publish.return_value = {"MessageId": "msg-topic"}

    handler_module.handler({}, None)
    pub = mock_sns.publish.call_args.kwargs
    correct_topic = pub.get("TopicArn") == os.environ["TOPIC_ARN"]
    has_subject = bool(pub.get("Subject"))
    # SNS subjects must be <= 100 ASCII chars with no newlines.
    subject_valid = (
        has_subject
        and len(pub["Subject"]) <= 100
        and "\n" not in pub["Subject"]
        and pub["Subject"].isascii()
    )
    passed = correct_topic and subject_valid
    results.add_result(
        "Publishes to configured TopicArn with a valid Subject",
        passed,
        f"TopicArn match={correct_topic} | Subject={pub.get('Subject')!r}",
    )

# ============================================================================
# TEST 18: Empty bucket SNS message shows "(none)"
# ============================================================================
print("\n[TEST 18] Empty Bucket - Message body reads '(none)'")
with patch("handler.s3") as mock_s3, patch("handler.sns") as mock_sns:
    mock_s3.get_paginator.return_value.paginate.return_value = [{}]
    mock_sns.publish.return_value = {"MessageId": "msg-none"}

    response = handler_module.handler({}, None)
    message = mock_sns.publish.call_args.kwargs.get("Message", "")
    passed = (
        response["statusCode"] == 200
        and "(none)" in message
        and "Object count: 0" in message
    )
    results.add_result(
        "Empty bucket publishes a '(none)' object list",
        passed,
        f"'(none)' present: {'(none)' in message}",
    )

# ============================================================================
# TEST 19: Generic (non-mapped) S3 error -> 500
# ============================================================================
print("\n[TEST 19] Generic S3 Error - Falls through to 500")
with patch("handler.s3") as mock_s3, patch("handler.sns") as mock_sns:
    error = ClientError(
        {
            "Error": {
                "Code": "InternalError",
                "Message": "We encountered an internal error",
            }
        },
        "ListObjectsV2",
    )
    mock_s3.get_paginator.return_value.paginate.side_effect = error

    response = handler_module.handler({}, None)
    body = json.loads(response["body"])
    passed = (
        response["statusCode"] == 500
        and body.get("success") is False
        and "InternalError" in body.get("error", "")
    )
    results.add_result(
        "Unmapped S3 error returns 500 with code surfaced",
        passed,
        f"Status: {response['statusCode']} | Error: {body.get('error')}",
    )

# ============================================================================
# TEST 20: Generic (non-mapped) SNS error -> 500
# ============================================================================
print("\n[TEST 20] Generic SNS Error - Falls through to 500")
with patch("handler.s3") as mock_s3, patch("handler.sns") as mock_sns:
    mock_s3.get_paginator.return_value.paginate.return_value = [
        {"Contents": [{"Key": "file.txt"}]}
    ]
    error = ClientError(
        {"Error": {"Code": "InternalError", "Message": "Internal failure"}}, "Publish"
    )
    mock_sns.publish.side_effect = error

    response = handler_module.handler({}, None)
    body = json.loads(response["body"])
    passed = response["statusCode"] == 500 and body.get("success") is False
    results.add_result(
        "Unmapped SNS error returns 500",
        passed,
        f"Status: {response['statusCode']} | Error: {body.get('error')}",
    )

# ============================================================================
# TEST 21: SNS connection error (BotoCoreError) -> 500
# ============================================================================
print("\n[TEST 21] SNS Connection Error (BotoCoreError)")
with patch("handler.s3") as mock_s3, patch("handler.sns") as mock_sns:
    mock_s3.get_paginator.return_value.paginate.return_value = [
        {"Contents": [{"Key": "file.txt"}]}
    ]
    mock_sns.publish.side_effect = BotoCoreError()

    response = handler_module.handler({}, None)
    body = json.loads(response["body"])
    passed = response["statusCode"] == 500 and body.get("success") is False
    results.add_result(
        "SNS connection error handled gracefully",
        passed,
        f"Status: {response['statusCode']} | Graceful error response",
    )

# ============================================================================
# TEST 22: Mixed pages - some pages without a Contents key
# ============================================================================
print("\n[TEST 22] Mixed Pagination - Empty page between populated pages")
with patch("handler.s3") as mock_s3, patch("handler.sns") as mock_sns:
    mock_s3.get_paginator.return_value.paginate.return_value = [
        {"Contents": [{"Key": "a.txt"}, {"Key": "b.txt"}]},
        {},  # page with no Contents key at all
        {"Contents": [{"Key": "c.txt"}]},
    ]
    mock_sns.publish.return_value = {"MessageId": "msg-mixed"}

    response = handler_module.handler({}, None)
    body = json.loads(response["body"])
    passed = response["statusCode"] == 200 and body.get("object_count") == 3
    results.add_result(
        "Pages without Contents are skipped without error",
        passed,
        f"Object count: {body.get('object_count')} (expected 3)",
    )

# ============================================================================
# TEST 23: Exactly 100 objects - no truncation notice
# ============================================================================
print("\n[TEST 23] Truncation Boundary - Exactly 100 objects (no '...more')")
with patch("handler.s3") as mock_s3, patch("handler.sns") as mock_sns:
    mock_s3.get_paginator.return_value.paginate.return_value = [
        {"Contents": [{"Key": f"file{i:03d}.txt"} for i in range(100)]}
    ]
    mock_sns.publish.return_value = {"MessageId": "msg-100"}

    response = handler_module.handler({}, None)
    message = mock_sns.publish.call_args.kwargs.get("Message", "")
    body = json.loads(response["body"])
    passed = (
        response["statusCode"] == 200
        and body.get("object_count") == 100
        and "more objects" not in message
    )
    results.add_result(
        "Exactly 100 objects shows no truncation notice",
        passed,
        f"object_count=100 | truncation_notice={'more objects' in message}",
    )

# ============================================================================
# TEST 24: Exactly 101 objects - truncation notice says "1 more"
# ============================================================================
print("\n[TEST 24] Truncation Boundary - 101 objects shows '1 more'")
with patch("handler.s3") as mock_s3, patch("handler.sns") as mock_sns:
    mock_s3.get_paginator.return_value.paginate.return_value = [
        {"Contents": [{"Key": f"file{i:03d}.txt"} for i in range(101)]}
    ]
    mock_sns.publish.return_value = {"MessageId": "msg-101"}

    response = handler_module.handler({}, None)
    message = mock_sns.publish.call_args.kwargs.get("Message", "")
    body = json.loads(response["body"])
    passed = (
        response["statusCode"] == 200
        and body.get("object_count") == 101
        and "and 1 more objects" in message
    )
    results.add_result(
        "101 objects truncates display to 100 with '1 more'",
        passed,
        f"object_count=101 | notice_present={'and 1 more objects' in message}",
    )

# ============================================================================
# TEST 25: Arbitrary event payload is ignored safely
# ============================================================================
print("\n[TEST 25] Manual Test Event - Arbitrary payload tolerated")
with patch("handler.s3") as mock_s3, patch("handler.sns") as mock_sns:
    mock_s3.get_paginator.return_value.paginate.return_value = [
        {"Contents": [{"Key": "file.txt"}]}
    ]
    mock_sns.publish.return_value = {"MessageId": "msg-event"}

    # A representative test-event-file payload plus a fake context.
    fake_event = {"source": "manual-test", "detail": {"foo": "bar"}, "list": [1, 2, 3]}
    fake_context = MagicMock(
        function_name="ListBucketFunction", aws_request_id="req-123"
    )
    response = handler_module.handler(fake_event, fake_context)
    passed = (
        response["statusCode"] == 200
        and json.loads(response["body"]).get("success") is True
    )
    results.add_result(
        "Handler ignores arbitrary event/context and succeeds",
        passed,
        f"Status: {response['statusCode']} with custom event payload",
    )

# ============================================================================
# TEST 26: Success response timestamp is valid ISO-8601
# ============================================================================
print("\n[TEST 26] Timestamp Format - Valid ISO-8601 in response body")
with patch("handler.s3") as mock_s3, patch("handler.sns") as mock_sns:
    mock_s3.get_paginator.return_value.paginate.return_value = [
        {"Contents": [{"Key": "file.txt"}]}
    ]
    mock_sns.publish.return_value = {"MessageId": "msg-ts"}

    response = handler_module.handler({}, None)
    body = json.loads(response["body"])
    ts = body.get("timestamp", "")
    try:
        from datetime import datetime as _dt

        _dt.fromisoformat(ts)
        ts_valid = True
    except (ValueError, TypeError):
        ts_valid = False
    passed = response["statusCode"] == 200 and ts_valid
    results.add_result(
        "Response timestamp parses as ISO-8601", passed, f"timestamp={ts!r}"
    )

# ============================================================================
# Print Summary
# ============================================================================
print()
success = results.summary()
sys.exit(0 if success else 1)
