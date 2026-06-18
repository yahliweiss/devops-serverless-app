# Project Guidelines

## Architecture Overview
- **IaC Framework:** AWS CDK (Python) located in `/infrastructure`
- **Lambda Code:** Python 3.x located in `/lambda`
- **CI/CD:** GitHub Actions located in `/.github/workflows`

## Build & Deploy Commands
- Install dependencies: `pip install -r requirements.txt`
- Synthesize CDK: `cdk synth`
- Deploy CDK: `cdk deploy`
- Test Lambda manually: `aws lambda invoke --function-name <Function_Name> response.json`

## Agent Guidelines
- **Token Efficiency:** Keep file modifications concise. Do not rewrite entire files if only a few lines need changing.
- **Single Source of Truth:** Always refer to `REQUIREMENTS.md` before adding new features.
- **Verification:** Do not assume AWS resources are created without checking. Provide CLI commands to verify deployments when requested.
- **Style:** Maintain clean, PEP-8 compliant Python code.