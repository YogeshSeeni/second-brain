#!/usr/bin/env bash
# Build brain-worker:vN for linux/arm64 and push to ECR.
# Requires: docker buildx enabled, AWS_PROFILE=brain, ECR repo already created.
set -euo pipefail

VERSION="${1:-v1}"
REGION="${AWS_REGION:-us-west-2}"
PROFILE="${AWS_PROFILE:-brain}"

ACCOUNT=$(AWS_PROFILE="$PROFILE" aws sts get-caller-identity --query Account --output text)
REPO="${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com/brain/brain-worker"
TAG="${REPO}:${VERSION}"

echo "=> Authenticating with ECR"
AWS_PROFILE="$PROFILE" aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin "${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com"

echo "=> Building brain-worker:${VERSION} for linux/arm64"
cd "$(dirname "$0")"
docker buildx create --use --name brain-builder >/dev/null 2>&1 || docker buildx use brain-builder
docker buildx build \
  --platform linux/arm64 \
  --tag "$TAG" \
  --push \
  .

echo "=> Verifying image in ECR"
AWS_PROFILE="$PROFILE" aws ecr describe-images \
  --repository-name brain/brain-worker \
  --image-ids imageTag="$VERSION" \
  --query 'imageDetails[0].imagePushedAt' --output text

echo "=> Pushed: $TAG"
