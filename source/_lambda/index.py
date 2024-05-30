# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# Licensed under the Apache License Version 2.0 (the "License"). You may not use this file except
# in compliance with the License. A copy of the License is located at http://www.apache.org/licenses/
# or in the "license" file accompanying this file. This file is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, express or implied. See the License for the
# specific language governing permissions and limitations under the License.

# take the s3 lambda file create event as input and return the s3 bucket and key
# NOTE: This is experimental
def get_s3_bucket_and_key(event: dict) -> tuple:
    """
    Gets the s3 bucket and key from the s3 lambda file create event
    """
    bucket = event['detail']['bucket']['name']
    folder_path = event['detail']['object']['key']
    full_file_uri = f's3://{bucket}/{folder_path}'
    return(bucket, folder_path, full_file_uri)


def lambda_handler(event, context):

    bucket,key, full_uri = get_s3_bucket_and_key(event)
    print(f"bucket: {bucket}, key: {key}, full_uri: {full_uri}")