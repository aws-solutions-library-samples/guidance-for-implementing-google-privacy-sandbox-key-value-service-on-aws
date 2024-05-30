#!/bin/bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# Licensed under the Apache License Version 2.0 (the "License"). You may not use this file except
# in compliance with the License. A copy of the License is located at http://www.apache.org/licenses/
# or in the "license" file accompanying this file. This file is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, express or implied. See the License for the
# specific language governing permissions and limitations under the License.

# This script builds the docker image and pushes it to ECR. Use it for local testing.
# The stack builds a imagebuilder pipeline that has these steps configured in the service through the yml files
set -e
echo "Setting variables"
# check if the first argument is not empty
if [ -z "$1" ]; then
  echo "AWS_ACCOUNT_ID is empty"
  echo "Usage: $0 <AWS_ACCOUNT_ID> <AWS_DEFAULT_REGION> <PROFILE_NAME>"
  exit 1
    # check if the second argument is not empty
    if [ -z "$2" ]; then
      echo "AWS_DEFAULT_REGION is empty"
      echo "Usage: $0 <AWS_ACCOUNT_ID> <AWS_DEFAULT_REGION> <PROFILE_NAME>"
      exit 1
    fi
fi
if [ -z "$3" ]; then
  echo "PROFILE_NAME is empty"
  echo "Usage: $0 <AWS_ACCOUNT_ID> <AWS_DEFAULT_REGION> <PROFILE_NAME>"
  echo "Using default profile"
  AWS_PROFILE="default"
else
  AWS_PROFILE=${3}
  echo "Using profile $AWS_PROFILE"
fi
AWS_ACCOUNT_ID=${1}
AWS_DEFAULT_REGION=${2}
ECR_REPO="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_DEFAULT_REGION}.amazonaws.com"
IMAGE_REPO_NAME="papi-kv-ecr-repo"
IMAGE_REPO_TAG="papi-datacli-with-awscli"
REPO_PATH="${ECR_REPO}/${IMAGE_REPO_NAME}:${IMAGE_REPO_TAG}"
echo "REPO_PATH: ${REPO_PATH}"
echo "Logging into ECR"
aws ecr get-login-password --region ${AWS_DEFAULT_REGION} --profile ${AWS_PROFILE} | docker login --username AWS --password-stdin ${ECR_REPO}
docker build -t $REPO_PATH --build-arg AWS_ACCOUNT_ID=$AWS_ACCOUNT_ID --build-arg AWS_DEFAULT_REGION=$AWS_DEFAULT_REGION .
echo "Pushing docker image to ECR"
docker push $REPO_PATH
echo "Done"
# use below for local testing
AWS_ACCESS_KEY_ID=$(aws configure get $AWS_PROFILE.aws_access_key_id)
AWS_SECRET_ACCESS_KEY=$(aws configure get $AWS_PROFILE.aws_secret_access_key)
docker run -e INP_BUCKET="papi-kv-data-$AWS_ACCOUNT_ID-$AWS_DEFAULT_REGION" -e INP_KEY="input/data.csv" -e OUT_BUCKET="papi-kv-data-$AWS_ACCOUNT_ID-$AWS_DEFAULT_REGION" -e OUT_KEY="output" -e AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID -e AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY $REPO_PATH
