import os

from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    CfnOutput,
    aws_s3 as s3,
    aws_s3_deployment as s3deploy,
    aws_lambda as _lambda,
    aws_sns as sns,
    aws_sns_subscriptions as subs,
    aws_iam as iam,
)
from constructs import Construct

# Default email used for the SNS subscription. Override at deploy time with:
#   cdk deploy -c subscription_email=you@example.com
# The recipient must confirm the subscription via the email AWS sends after deploy.
DEFAULT_SUBSCRIPTION_EMAIL = "[INSERT_YOUR_EMAIL_HERE]"

# Paths are resolved relative to this file so `cdk synth` works from any cwd.
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
LAMBDA_DIR = os.path.join(_REPO_ROOT, "lambda")
SAMPLE_FILES_DIR = os.path.join(_REPO_ROOT, "sample_files")


class ServerlessAppStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # --- S3 bucket (section 3) ---
        bucket = s3.Bucket(
            self,
            "DataBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # Upload local sample_files/ to the bucket during deployment (section 3).
        s3deploy.BucketDeployment(
            self,
            "DeploySampleFiles",
            sources=[s3deploy.Source.asset(SAMPLE_FILES_DIR, exclude=[".DS_Store"])],
            destination_bucket=bucket,
        )

        # --- SNS topic + email subscription (section 6) ---
        # Email is a parameter: read from CDK context, falling back to the default.
        subscription_email = (
            self.node.try_get_context("subscription_email") or DEFAULT_SUBSCRIPTION_EMAIL
        )
        topic = sns.Topic(self, "NotificationTopic", display_name="Serverless App Notifications")
        topic.add_subscription(subs.EmailSubscription(subscription_email))

        # --- IAM role with least privilege (section 5) ---
        lambda_role = iam.Role(
            self,
            "LambdaExecutionRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
        )
        # Grant only S3 read on this bucket and SNS publish on this topic.
        bucket.grant_read(lambda_role)
        topic.grant_publish(lambda_role)

        # --- Lambda function (section 4) ---
        fn = _lambda.Function(
            self,
            "ListBucketFunction",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=_lambda.Code.from_asset(LAMBDA_DIR),
            role=lambda_role,
            timeout=Duration.seconds(30),
            environment={
                "BUCKET_NAME": bucket.bucket_name,
                "TOPIC_ARN": topic.topic_arn,
            },
        )

        CfnOutput(self, "BucketName", value=bucket.bucket_name)
        CfnOutput(self, "TopicArn", value=topic.topic_arn)
        CfnOutput(self, "FunctionName", value=fn.function_name)
