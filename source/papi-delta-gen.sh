#!/bin/bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# Licensed under the Apache License Version 2.0 (the "License"). You may not use this file except
# in compliance with the License. A copy of the License is located at http://www.apache.org/licenses/
# or in the "license" file accompanying this file. This file is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, express or implied. See the License for the
# specific language governing permissions and limitations under the License.

# This script is used in the stepfunction workflow with Ec2 as compute option
# expects input s3 object url and output s3 prefix url as arguments
set -e
echo "Setting variables"

export HOME=/home/ec2-user

cd /home/ec2-user/data-cli
echo "${PWD}"
ls -ltr

echo "Copying input data file from s3 to local"
aws s3 cp ${1} "${PWD}/data.csv"

echo "Starting delta file generation"
docker run --rm \
    --volume=$PWD:$PWD \
    --user $(id -u ${USER}):$(id -g ${USER}) \
    --entrypoint=/tools/data_cli/data_cli \
    bazel/production/packaging/tools:tools_binaries_docker_image \
    format_data \
    --input_file="$PWD/data.csv" \
    --input_format=CSV \
    --output_file="$PWD/DELTA_0000000000000001" \
    --output_format=DELTA

ls -lrt
echo "Copying delta file from local to s3"
aws s3 cp "${PWD}/DELTA_0000000000000001" "${2}/DELTA_0000000000000001"
echo "Done"