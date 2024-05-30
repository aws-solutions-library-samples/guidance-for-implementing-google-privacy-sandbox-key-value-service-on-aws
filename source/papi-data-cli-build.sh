#!/bin/bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# Licensed under the Apache License Version 2.0 (the "License"). You may not use this file except
# in compliance with the License. A copy of the License is located at http://www.apache.org/licenses/
# or in the "license" file accompanying this file. This file is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, express or implied. See the License for the
# specific language governing permissions and limitations under the License.

# This script is used in the stepfunction workflow with Ec2 as compute option
set -e
echo "Setting variables"

export HOME=/home/ec2-user
# scripts expects files to be in this folder
# the previous build step of s3 copy does this
cd /home/ec2-user/data-cli
echo "${PWD}"
ls -ltr

# if the folder protected-auction-key-value-service exists continue else run git clone
if [ -d "protected-auction-key-value-service" ]
then
    echo "protected-auction-key-value-service directory exists.Skipping git clone"
else
    echo "Cloning git repo"
    git clone "https://github.com/privacysandbox/protected-auction-key-value-service"
    git config --global --add safe.directory /home/ec2-user/data-cli/protected-auction-key-value-service
fi
cd protected-auction-key-value-service
# echo "Starting test riegeli data. This step takes longer on first execution"
# ./tools/serving_data_generator/generate_test_riegeli_data

echo "Starting docker image build"
builders/tools/bazel-debian run //production/packaging/tools:copy_to_dist --//:instance=local --//:platform=local

# read the two input parameters and assign them to account and region variables
echo "Pushing docker image to ECR"
export AWS_ACCOUNT_ID=${1}
export AWS_DEFAULT_REGION=${2}
ECR_REPO="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_DEFAULT_REGION}.amazonaws.com"
IMAGE_REPO_NAME="papi-kv-ecr-repo"
IMAGE_REPO_TAG="tools_binaries_docker_image"
REPO_PATH="${ECR_REPO}/${IMAGE_REPO_NAME}:${IMAGE_REPO_TAG}"
echo "REPO_PATH: ${REPO_PATH}"
echo "Pushing docker image to ECR"
aws ecr get-login-password --region ${AWS_DEFAULT_REGION} | docker login --username AWS --password-stdin ${ECR_REPO}
docker load -i dist/tools_binaries_docker_image.tar
docker tag bazel/production/packaging/tools:tools_binaries_docker_image $REPO_PATH
docker push $REPO_PATH
echo "data cli container build done"

# build and publish docker image with data cli and aws cli
echo "Building the data cli + aws cli"
IMAGE_REPO_NAME="papi-kv-ecr-repo"
IMAGE_REPO_TAG="papi-datacli-with-awscli"
docker build -t $IMAGE_REPO_NAME:$IMAGE_REPO_TAG .
ECR_REPO="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_DEFAULT_REGION}.amazonaws.com"
REPO_PATH="${ECR_REPO}/${IMAGE_REPO_NAME}:${IMAGE_REPO_TAG}"
echo "REPO_PATH: ${REPO_PATH}"
echo "Pushing data cli + aws cli docker image to ECR"
aws ecr get-login-password --region ${AWS_DEFAULT_REGION} | docker login --username AWS --password-stdin ${ECR_REPO}
docker tag $IMAGE_REPO_NAME:$IMAGE_REPO_TAG $REPO_PATH
docker push $REPO_PATH
echo "Done"