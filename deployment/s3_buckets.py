# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# Licensed under the Apache License Version 2.0 (the "License"). You may not use this file except
# in compliance with the License. A copy of the License is located at http://www.apache.org/licenses/
# or in the "license" file accompanying this file. This file is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, express or implied. See the License for the
# specific language governing permissions and limitations under the License.

# This creates s3 buckets needed by other stacks or imports stack object from existing resources based on the input
from aws_cdk import (
    Stack,
    aws_s3 as s3,
    aws_s3_deployment as s3_deployment,
    RemovalPolicy,
    CfnOutput
)

from constructs import Construct
from deployment import constants

class s3Buckets(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        # if input is given use it, otherwise build the names
        if self.node.try_get_context('input-bucket-pfx'):
            input_bucket_pfx:str = self.node.try_get_context('input-bucket-pfx')
        else:
            input_bucket_pfx = constants.app_prefix

        self.input_bucket_name = f"{input_bucket_pfx}-data-{constants.acc}-{constants.region}"
        access_bucket_name = f"{input_bucket_pfx}-access-log-{constants.acc}-{constants.region}"
        # creating access log s3 bucket
        access_log_bucket=s3.Bucket(self, access_bucket_name,
                                    bucket_name= access_bucket_name, enforce_ssl=True,
                                    auto_delete_objects=True, removal_policy=RemovalPolicy.DESTROY)
        
        # create data s3 bucket
        self.input_bucket = s3.Bucket(self, self.input_bucket_name,
                                         bucket_name= self.input_bucket_name,
                                         enforce_ssl=True, auto_delete_objects=True, 
                                         removal_policy=RemovalPolicy.DESTROY,
                                         server_access_logs_bucket=access_log_bucket,
                                         event_bridge_enabled=True)
        
        # upload source code to the data bucket from source dir
        s3_deployment.BucketDeployment(self, f"{input_bucket_pfx}-source-deployment",
                                                                      destination_bucket=self.input_bucket,
                                                                      # destination_key_prefix="source",
                                                                      sources=[s3_deployment.Source.asset(constants.source_dir), 
                                                                               s3_deployment.Source.asset(constants.assets_dir)])

        # build output-bucket resource based on inputs
        if self.node.try_get_context('output-bucket-name'):
            out_bucket_name = self.node.try_get_context('output-bucket-name')
            self.output_bucket = s3.Bucket.from_bucket_name(self, out_bucket_name, bucket_name=out_bucket_name)
        else:
            self.output_bucket = self.input_bucket
        
        CfnOutput(self, "inut_bucket_url", value=self.input_bucket.s3_url_for_object())
        CfnOutput(self, "input_bucket_arn", value=self.input_bucket.bucket_arn)
        CfnOutput(self, "output_bucket_url", value=self.output_bucket.s3_url_for_object())
        CfnOutput(self, "output_bucket_arn", value=self.output_bucket.bucket_arn)
