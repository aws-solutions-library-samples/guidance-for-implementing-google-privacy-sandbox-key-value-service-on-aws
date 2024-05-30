# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# Licensed under the Apache License Version 2.0 (the "License"). You may not use this file except
# in compliance with the License. A copy of the License is located at http://www.apache.org/licenses/
# or in the "license" file accompanying this file. This file is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, express or implied. See the License for the
# specific language governing permissions and limitations under the License.

# This builds VPC stack or imports existing vpc resource as a stack object based on input
from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    CfnOutput
)

from constructs import Construct
from deployment import constants

class vpcStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        # get vpc id from context
        vpc_id = self.node.try_get_context("vpc_id")
        if vpc_id:
            self.vpc = ec2.Vpc.from_lookup(self, f"{constants.app_prefix}-vpc", vpc_id=vpc_id)
        else:
        # Create VPC
            self.vpc = ec2.Vpc(
                self,
                f"{constants.app_prefix}-vpc",
                ip_addresses=ec2.IpAddresses.cidr("10.0.0.0/16"),
                max_azs=2,
                nat_gateways=1,
                subnet_configuration=[
                    ec2.SubnetConfiguration(
                        subnet_type=ec2.SubnetType.PUBLIC,
                        name=f"{constants.app_prefix}-Public-subnet",
                        cidr_mask=24
                        ),
                        ec2.SubnetConfiguration(
                            subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                            name=f"{constants.app_prefix}-Private-subnet",
                            cidr_mask=24
                            )],
                vpc_name=f"{constants.app_prefix}-vpc"
                )
            # add vpc endpoint for S3
            subnet_sel = ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS)
            self.vpc.add_gateway_endpoint(
                id=f"{constants.app_prefix}-s3-vpc-endpoint",
                service=ec2.GatewayVpcEndpointAwsService.S3,
                subnets=[subnet_sel]
            )
            # add vpc endpoint for ECR
            
            self.vpc.add_interface_endpoint(
                id=f"{constants.app_prefix}-ecr-vpc-endpoint",
                service=ec2.InterfaceVpcEndpointAwsService.ECR_DOCKER,
                subnets=subnet_sel
            )
            # add vpc endpoint for eventbridge
            self.vpc.add_interface_endpoint(
                id=f"{constants.app_prefix}-events-vpc-endpoint",
                service=ec2.InterfaceVpcEndpointAwsService.EVENTBRIDGE,
                subnets=subnet_sel
            )
            # add vpc endpoint for imagebuilder
            self.vpc.add_interface_endpoint(
                id=f"{constants.app_prefix}-imagebuilder-vpc-endpoint",
                service=ec2.InterfaceVpcEndpointAwsService.IMAGE_BUILDER,
                subnets=subnet_sel
            )
            # add vpc endpoint for ssm
            self.vpc.add_interface_endpoint(
                id=f"{constants.app_prefix}-ssm-vpc-endpoint",
                service=ec2.InterfaceVpcEndpointAwsService.SSM,
                subnets=subnet_sel
            )
            # add vpc endpoint for stepfunctions
            self.vpc.add_interface_endpoint(
                id=f"{constants.app_prefix}-states-vpc-endpoint",
                service=ec2.InterfaceVpcEndpointAwsService.STEP_FUNCTIONS,
                subnets=subnet_sel
            )
        CfnOutput(self, "vpc_id", value=self.vpc.vpc_id)