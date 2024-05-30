#!/bin/bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# Licensed under the Apache License Version 2.0 (the "License"). You may not use this file except
# in compliance with the License. A copy of the License is located at http://www.apache.org/licenses/
# or in the "license" file accompanying this file. This file is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, express or implied. See the License for the
# specific language governing permissions and limitations under the License.

# This is th entry point script of the docker image
set -e
echo "Starting"
echo "${PWD}"
echo "$INP_BUCKET $INP_KEY $OUT_BUCKET $OUT_KEY"

INP_S3_URL="s3://$INP_BUCKET/$INP_KEY"
INP_LCL_FILE="/tools/$INP_KEY"
# extract file name form the key path
INP_FILE_NAME=${INP_KEY##*/}
# set the name of delta file
OUT_FILE_NAME="${INP_FILE_NAME}_DELTA"
OUT_LCL_FILE="/tools/$OUT_FILE_NAME"
OUT_S3_URL="s3://$OUT_BUCKET/$OUT_KEY/$OUT_FILE_NAME"

echo "Downloading from $INP_S3_URL to $INP_LCL_FILE"
aws s3 cp $INP_S3_URL $INP_LCL_FILE

echo "Generating Delta file for the downloaded CSV"
/tools/data_cli/data_cli \
    format_data \
    --input_file=$INP_LCL_FILE \
    --input_format=CSV \
    --output_file=$OUT_LCL_FILE \
    --output_format=DELTA

ls -l $OUT_LCL_FILE
echo "Uploading $OUT_LCL_FILE to $OUT_S3_URL"
aws s3 cp $OUT_LCL_FILE $OUT_S3_URL
echo "Done"