#!/usr/bin/env python3
"""Manual test script (section 8).

Discovers the deployed Lambda function name from the CloudFormation stack
outputs, invokes it synchronously, and prints the response payload.

Usage:
    python scripts/invoke_lambda.py
    python scripts/invoke_lambda.py --stack ServerlessAppStack --region us-east-1
"""

import argparse
import json
import sys

import boto3


def get_function_name(stack_name: str, region: str) -> str:
    """Read the FunctionName output from the CloudFormation stack."""
    cfn = boto3.client("cloudformation", region_name=region)
    stack = cfn.describe_stacks(StackName=stack_name)["Stacks"][0]
    for output in stack.get("Outputs", []):
        if output["OutputKey"] == "FunctionName":
            return output["OutputValue"]
    sys.exit(f"FunctionName output not found on stack {stack_name!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Manually invoke the deployed Lambda.")
    parser.add_argument("--stack", default="ServerlessAppStack", help="CloudFormation stack name")
    parser.add_argument("--region", default="us-east-1", help="AWS region")
    parser.add_argument(
        "--function-name",
        default=None,
        help="Override: invoke this function name instead of reading the stack output",
    )
    args = parser.parse_args()

    function_name = args.function_name or get_function_name(args.stack, args.region)
    print(f"Invoking {function_name} ...")

    lambda_client = boto3.client("lambda", region_name=args.region)
    response = lambda_client.invoke(
        FunctionName=function_name,
        InvocationType="RequestResponse",
    )

    status = response["StatusCode"]
    payload = response["Payload"].read().decode("utf-8")
    print(f"StatusCode: {status}")
    try:
        print("Payload:")
        print(json.dumps(json.loads(payload), indent=2))
    except json.JSONDecodeError:
        print(payload)

    if response.get("FunctionError"):
        sys.exit(f"Function returned an error: {response['FunctionError']}")
    print("\nDone. Check the subscribed email inbox for the SNS notification.")


if __name__ == "__main__":
    main()
