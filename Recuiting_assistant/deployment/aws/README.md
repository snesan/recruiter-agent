# AWS Deployment Guide: Cost-Effective ECS Fargate

This guide deploys the FastAPI API and Streamlit UI as two containers in one Amazon ECS Fargate task. Containers in the same Fargate task communicate through `localhost`, so the UI calls `http://localhost:8000/api`. Only Streamlit port `8501` is public.

This direct-public-IP design is intended for controlled testing. Restrict port `8501` to your public IP. It has no stable hostname, TLS certificate, or application login.

> **Cost note:** Fargate is serverless, but a service with one running task is billed continuously. A public IPv4 address, ECR images, CloudWatch logs, and Secrets Manager also have charges. Set the service desired count to `0` when unused.

## Architecture

```text
Browser -> Fargate task public IP:8501 -> Streamlit UI
                                            |
                                            v
                                      localhost:8000
                                            |
                                         FastAPI
                                      /           \
                                OpenAI API    Google Drive API
```

The task template uses the smallest valid Linux Fargate size: `0.25 vCPU` and `512 MiB`. Local idle use is well below this limit, but increase task memory to `1024` if ECS reports an out-of-memory stop during large batches.

## Step 0: Prerequisites

Install and configure:

- AWS CLI v2 with an IAM identity allowed to use ECR, ECS, IAM, CloudWatch Logs, Secrets Manager, EC2 networking, and `iam:PassRole`.
- Docker Desktop or Docker Engine.
- A VPC with a public subnet whose route table reaches an internet gateway.
- A current OpenAI API key.
- A Google service-account JSON key with Google Drive API access.

AWS CLI is not currently installed on this development machine. On macOS, install the official current-user AWS CLI v2 package with:

```bash
curl -fsSL https://awscli.amazonaws.com/v2/install.sh | bash
export PATH="$HOME/.local/bin:$PATH"
aws --version
```

Add the PATH export to `~/.zshrc` if a new terminal cannot find `aws`.

Authenticate with your organization's preferred method. IAM Identity Center is recommended:

```bash
aws configure sso
aws sso login --profile YOUR_PROFILE
export AWS_PROFILE=YOUR_PROFILE
```

For a personal account without IAM Identity Center, configure a dedicated IAM user's access keys with `aws configure`. Never use AWS root-user access keys.

From the project directory, verify the tools and identity:

```bash
cd /Users/vidyasagar/recruiter-agent/Recuiting_assistant
aws --version
docker version
aws sts get-caller-identity
```

Set the deployment Region and account ID. Keep all resources in this Region:

```bash
export AWS_REGION=ap-south-1
export AWS_ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
```

## Step 1: Prepare Google Drive for ECS

The local `credentials.json` OAuth flow is not suitable for an unattended Fargate task. Use a service account:

1. Open the Google Cloud project that has the Drive API enabled.
2. Create a service account under **IAM & Admin → Service Accounts**.
3. Create and download a JSON key for that service account.
4. Copy the service account email from the JSON or Google Cloud console.
5. Share the Google Drive resume folder with that email as **Viewer**.
6. Keep the downloaded JSON outside the project and do not commit it.

## Step 2: Create AWS Secrets Manager secrets

Open [AWS Secrets Manager](https://console.aws.amazon.com/secretsmanager/) in `AWS_REGION` and create two **Other type of secret** entries using the **Plaintext** editor:

1. Name: `recuiting-assistant/openai-api-key`
   - Value: the OpenAI API key only.
2. Name: `recuiting-assistant/google-service-account-json`
   - Value: the complete Google service-account JSON document.

Copy both secret ARNs, then set:

```bash
export OPENAI_SECRET_ARN="arn:aws:secretsmanager:REGION:ACCOUNT:secret:recuiting-assistant/openai-api-key-XXXXXX"
export GOOGLE_SECRET_ARN="arn:aws:secretsmanager:REGION:ACCOUNT:secret:recuiting-assistant/google-service-account-json-XXXXXX"
```

Using ECS secret references keeps these values out of the task definition. Never put either secret under the task definition's plain-text environment variables.

## Step 3: Build and push images to Amazon ECR

The included script creates `recruiter-api` and `recruiter-ui`, signs Docker into ECR, builds Linux AMD64 images, and pushes them:

```bash
./scripts/push-to-ecr.sh
```

The equivalent ECR login is:

```bash
aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin \
    "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"
```

ECR authentication tokens are Region-specific and valid for 12 hours.

## Step 4: Create the ECS task execution role

Create this role once:

```bash
aws iam create-role \
  --role-name recuiting-assistant-ecs-execution \
  --assume-role-policy-document file://deployment/aws/ecs-task-execution-role-trust-policy.json

aws iam attach-role-policy \
  --role-name recuiting-assistant-ecs-execution \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy

export EXECUTION_ROLE_ARN="arn:aws:iam::$AWS_ACCOUNT_ID:role/recuiting-assistant-ecs-execution"
```

Render the account-specific task definition and least-privilege secret policy:

```bash
python3 scripts/render-aws-files.py \
  --account-id "$AWS_ACCOUNT_ID" \
  --region "$AWS_REGION" \
  --execution-role-arn "$EXECUTION_ROLE_ARN" \
  --openai-secret-arn "$OPENAI_SECRET_ARN" \
  --google-secret-arn "$GOOGLE_SECRET_ARN"
```

Allow the execution role to read only those two secrets:

```bash
aws iam put-role-policy \
  --role-name recuiting-assistant-ecs-execution \
  --policy-name ReadRecruitingAssistantSecrets \
  --policy-document file://deployment/aws/secrets-policy.json
```

If either secret uses a customer-managed KMS key, also grant this role `kms:Decrypt` for that key.

## Step 5: Create log groups, task definition, and cluster

```bash
aws logs create-log-group \
  --region "$AWS_REGION" \
  --log-group-name /ecs/recuiting-assistant/api 2>/dev/null || true

aws logs create-log-group \
  --region "$AWS_REGION" \
  --log-group-name /ecs/recuiting-assistant/ui 2>/dev/null || true

aws ecs register-task-definition \
  --region "$AWS_REGION" \
  --cli-input-json file://deployment/aws/task-definition.json

aws ecs create-cluster \
  --region "$AWS_REGION" \
  --cluster-name recruiter-cluster
```

The generated `task-definition.json` and `secrets-policy.json` are ignored by Git because they contain account-specific ARNs.

## Step 6: Create the security group

In **EC2 → Security Groups**, create `recuiting-assistant-ui` in the deployment VPC:

- Inbound: custom TCP port `8501`, source **My IP** (`your-public-ip/32`).
- Do not add inbound port `8000`; only the UI needs it through task-local `localhost`.
- Outbound: keep the default allow-all rule so the task can reach ECR, OpenAI, Google Drive, Secrets Manager, and CloudWatch Logs.

If your internet provider changes your public IP, update the inbound source before reconnecting.

## Step 7: Create the Fargate service

Open [Amazon ECS](https://console.aws.amazon.com/ecs/v2) and follow these steps:

1. Open **Clusters → recruiter-cluster → Services → Create**.
2. Under **Compute options**, choose **Launch type**, then **FARGATE**.
3. Choose task definition family `recuiting-assistant` and its latest revision.
4. Enter service name `recruiter-service`.
5. Set **Desired tasks** to `1`.
6. Select the deployment VPC and one public subnet.
7. Select the `recuiting-assistant-ui` security group.
8. Turn on **Public IP** / **Assign public IP**.
9. Do not configure a load balancer for this low-cost test deployment.
10. Create the service and wait for the task to show **Running** and healthy.

The public subnet and assigned public IP give the task outbound internet access. The two containers communicate internally over `localhost`.

## Step 8: Open and verify the application

1. In ECS, open **Clusters → recruiter-cluster → recruiter-service → Tasks**.
2. Open the running task.
3. Copy its **Public IP** from the networking section.
4. Open `http://PUBLIC_IP:8501`.
5. Test one uploaded PDF.
6. Test the shared Google Drive folder. The folder must be shared with the deployed service-account email.

If the task stops or remains unhealthy, check:

- **ECS task → Stopped reason**.
- CloudWatch log groups `/ecs/recuiting-assistant/api` and `/ecs/recuiting-assistant/ui`.
- Public subnet internet-gateway route and **Assign public IP**.
- Execution-role permission for both secret ARNs.
- The Google service account's access to the Drive folder.

## Step 9: Deploy application updates

Push the updated `latest` images and replace the running task:

```bash
./scripts/push-to-ecr.sh

aws ecs update-service \
  --region "$AWS_REGION" \
  --cluster recruiter-cluster \
  --service recruiter-service \
  --force-new-deployment
```

If the task-definition template changed, render and register it again, then update the service to the newest task-definition revision.

## Step 10: Stop costs when idle

Stop Fargate compute and release the task public IP:

```bash
aws ecs update-service \
  --region "$AWS_REGION" \
  --cluster recruiter-cluster \
  --service recruiter-service \
  --desired-count 0
```

Start it again later with `--desired-count 1`. A restarted task normally receives a different public IP.

For permanent cleanup, delete the ECS service and cluster, ECR repositories/images, CloudWatch log groups, Secrets Manager secrets, IAM role, and security group. Review each resource before deletion.

## Production upgrade path

For a stable HTTPS URL, place an Application Load Balancer in front of port `8501`, use an ACM certificate and Route 53 domain, run tasks in private subnets, and add an authentication layer. These improve security and reliability but add monthly cost.

## Official AWS references

- [ECS Fargate task networking](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-task-networking.html)
- [Valid Fargate CPU and memory combinations](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-tasks-services.html)
- [Install or update AWS CLI v2](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)
- [Configure AWS CLI with IAM Identity Center](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sso.html)
- [ECR private registry authentication](https://docs.aws.amazon.com/AmazonECR/latest/userguide/registry_auth.html)
- [Pass Secrets Manager secrets to ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/secrets-envvar-secrets-manager.html)
- [Create an ECS service with the AWS CLI](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ECS_AWSCLI_Fargate.html)
- [AWS Fargate pricing](https://aws.amazon.com/fargate/pricing/)
