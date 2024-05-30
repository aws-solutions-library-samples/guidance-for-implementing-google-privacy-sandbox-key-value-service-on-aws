# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# Licensed under the Apache License Version 2.0 (the "License"). You may not use this file except
# in compliance with the License. A copy of the License is located at http://www.apache.org/licenses/
# or in the "license" file accompanying this file. This file is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, express or implied. See the License for the
# specific language governing permissions and limitations under the License.

# Build a container with data cli and python SDK
# load the papi data tools image
ARG AWS_ACCOUNT_ID=""
ARG AWS_DEFAULT_REGION="us-west-2"
ARG ECR_REPO="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_DEFAULT_REGION}.amazonaws.com"
ARG IMAGE_REPO_NAME="papi-kv-ecr-repo"
ARG IMAGE_REPO_TAG="tools_binaries_docker_image"
ARG REPO_PATH="${ECR_REPO}/${IMAGE_REPO_NAME}:${IMAGE_REPO_TAG}"
FROM ${REPO_PATH} AS papi-cli
# create a python build image
FROM python:3.9-slim AS build-env
WORKDIR /app
COPY ./papi-delta-filegen-s3.py ./
COPY ./requirements.txt ./
RUN pip install --disable-pip-version-check -r requirements.txt --target /packages
# copy files from both above images to new combined image
FROM gcr.io/distroless/python3
COPY --from=papi-cli /tools /tools
WORKDIR /tools
COPY --from=build-env /packages /packages
COPY --from=build-env /app /app
ENV PYTHONPATH=/packages
CMD ["/app/papi-delta-filegen-s3.py"]