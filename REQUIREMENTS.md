# Project Requirements: DevOps Serverless App

## 1. Project Overview & Deliverables
- Goal: Design and deploy an automated serverless application on AWS using IaC.
- Repository: Must be a public GitHub repository.
- Codebase Structure: Must include IaC code, Lambda function code, a `sample_files/` folder, a GitHub Actions workflow, and a manual test script.

## 2. Infrastructure as Code (IaC)
- Tool: Use AWS CDK with Python.
- Scope: Define and deploy all AWS resources (S3, Lambda, SNS, IAM Role) entirely through code.

## 3. S3 Bucket & Data
- Create the S3 bucket using IaC.
- Deployment Task: Upload files from the local `sample_files/` folder to the S3 bucket automatically during the deployment process.

## 4. Lambda Function
- Language: Python.
- Core Logic: 
  1. List all objects within the designated S3 bucket.
  2. Publish a message to the SNS topic containing details of this execution.

## 5. IAM Role (Security)
- Define via IaC using the principle of least privilege.
- Permissions needed: S3 read access, SNS publish access, Lambda execution.
- Attach this role to the Lambda function in the CDK code.

## 6. SNS Topic & Notifications
- Create an SNS topic via IaC.
- Add an email subscription to receive notifications upon Lambda execution.

## 7. CI/CD Pipeline
- Tool: GitHub Actions.
- Trigger: Manual trigger using `workflow_dispatch`.
- Action: Deploy all infrastructure to AWS.

## 8. Manual Testing
- Create a test script (e.g., using AWS CLI `aws lambda invoke` or a `boto3` python script) to manually trigger the Lambda function for testing purposes.

## 9. README.md Documentation
- Must include a project overview.
- Setup and deployment steps.
- Instructions on how to run the manual Lambda test script.
- List of tools/frameworks used.
- Crucial Note: Explicitly mention that the email recipient must manually confirm the SNS email subscription after the first deployment.