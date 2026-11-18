#!/usr/bin/env bash
set -euo pipefail

: "${AWS_REGION:?Set AWS_REGION, for example ap-south-1}"

AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-$(aws sts get-caller-identity --query Account --output text)}"
REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
TARGET_PLATFORM="${TARGET_PLATFORM:-linux/amd64}"

for repository in recruiter-api recruiter-ui; do
  if ! aws ecr describe-repositories \
    --region "${AWS_REGION}" \
    --repository-names "${repository}" >/dev/null 2>&1; then
    aws ecr create-repository \
      --region "${AWS_REGION}" \
      --repository-name "${repository}" \
      --image-scanning-configuration scanOnPush=true \
      --encryption-configuration encryptionType=AES256 >/dev/null
  fi
done

aws ecr get-login-password --region "${AWS_REGION}" \
  | docker login --username AWS --password-stdin "${REGISTRY}"

docker build --platform "${TARGET_PLATFORM}" -f Dockerfile.api -t recruiter-api:latest .
docker tag recruiter-api:latest "${REGISTRY}/recruiter-api:latest"
docker push "${REGISTRY}/recruiter-api:latest"

docker build --platform "${TARGET_PLATFORM}" -f Dockerfile.ui -t recruiter-ui:latest .
docker tag recruiter-ui:latest "${REGISTRY}/recruiter-ui:latest"
docker push "${REGISTRY}/recruiter-ui:latest"

printf 'Pushed images to %s\n' "${REGISTRY}"

