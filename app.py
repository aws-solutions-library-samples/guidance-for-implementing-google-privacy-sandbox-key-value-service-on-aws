#!/usr/bin/env python3
import os

import aws_cdk as cdk

from deployment.vpc_stack import vpcStack
from deployment.s3_buckets import s3Buckets
from deployment.data_cli_build import dataCliBuild
from deployment.data_loader import dataLoader
from deployment.waf import Waf
from cdk_nag import AwsSolutionsChecks, NagSuppressions
import deployment.constants as constants

app = cdk.App()

papi_vpc = vpcStack(app, f"{constants.app_prefix}-vpc-stack",

    env=cdk.Environment(
        account=constants.acc,
        region=constants.region
        ),
    description= f"{constants.stack_desc}-vpc-stack"
)


s3_stack = s3Buckets(app, f"{constants.app_prefix}-s3-stack",

    env=cdk.Environment(
        account=constants.acc,
        region=constants.region
        ),
    description= f"{constants.stack_desc}-s3-stack"
)
input_bucket_arn = s3_stack.input_bucket.bucket_arn
input_bucket_url = s3_stack.input_bucket.s3_url_for_object()
# below variable is coming back as a tuple instead of string
input_bucket_name = s3_stack.input_bucket_name
output_bucket_name = s3_stack.output_bucket.bucket_name

data_cli_build_stack = dataCliBuild(app, f"{constants.app_prefix}-data-cli-build-stack",

    env=cdk.Environment(
        account=constants.acc,
        region=constants.region
        ),
    description= f"{constants.stack_desc}-data-cli-build-stack",
    vpc = papi_vpc.vpc,
    s3_bucket_arn= input_bucket_arn,
    s3_bucket_url= input_bucket_url
)
data_cli_build_stack.add_dependency(papi_vpc)
data_cli_build_stack.add_dependency(s3_stack)

# pull in ec2_instance from data_cli_build_stack only if the build-infra context variable is all or stepfunction otherwise none
ec2_instance = data_cli_build_stack.build_instance if data_cli_build_stack.build_infra == "all" or data_cli_build_stack.build_infra == "stepfunction" else None

data_loader_stack= dataLoader(app, f"{constants.app_prefix}-data-loader-stack",

    env=cdk.Environment(
        account=constants.acc,
        region=constants.region
        ),
    description= f"{constants.stack_desc}-data-loader-stack",
    vpc = papi_vpc.vpc,
    ecr_repo = data_cli_build_stack.ecr_repo,
    ec2_instance=ec2_instance,
    input_bucket_name=input_bucket_name,
    output_bucket_name=output_bucket_name
)
# data_loader_stack.add_dependency(data_cli_build_stack)

waf_stack = Waf(app, f"{constants.app_prefix}-waf-stack",

    env=cdk.Environment(
        account=constants.acc,
        region=constants.region
        ),
    description= f"{constants.stack_desc}-waf-stack"
)

nag_suppressions = [
        {
            "id": "AwsSolutions-IAM5",
            "reason": "AWS managed policies are allowed which sometimes uses * in the resources like - AWSGlueServiceRole has aws-glue-* . AWS Managed IAM policies have been allowed to maintain secured access with the ease of operational maintenance - however for more granular control the custom IAM policies can be used instead of AWS managed policies",
        },
        {
            "id": "AwsSolutions-IAM4",
            "reason": "AWS Managed IAM policies have been allowed to maintain secured access with the ease of operational maintenance - however for more granular control the custom IAM policies can be used instead of AWS managed policies",
        },
        {
            "id": "AwsSolutions-SQS3",
            "reason": "SQS queue used in the stack itself is a DLQ for ecs task execution.",
        },
        {
            'id': 'AwsSolutions-L1',
            'reason': 'Key properties are not accessible from cdk',
        },
        {
            'id': 'AwsSolutions-EC29',
            'reason': 'Stack is creating a build server, that can be terminated and recreated without impact. Only one server is needed, ASG not required',
        },
        {
            'id': 'AwsSolutions-VPC7',
            'reason': 'This is sample code, flow log enablement decision is left to customers, considering that this stack needs to support adtech network scale',
        },
        {
            'id': 'AwsSolutions-ECS4',
            'reason': 'The ECS Cluster has CloudWatch Container Insights disabled. This decision is left to customers',
        },
        {
            'id': 'AwsSolutions-SF2',
            'reason': 'The Step Function does not have X-Ray tracing enabled. This decision is left to customers'
        }
        
    ]

NagSuppressions.add_stack_suppressions(
    papi_vpc,
    nag_suppressions,
    apply_to_nested_stacks=True
)

NagSuppressions.add_stack_suppressions(
    s3_stack,
    nag_suppressions,
    apply_to_nested_stacks=True
)

NagSuppressions.add_stack_suppressions(
    data_cli_build_stack,
    nag_suppressions,
    apply_to_nested_stacks=True
)

NagSuppressions.add_stack_suppressions(
    data_loader_stack,
    nag_suppressions,
    apply_to_nested_stacks=True
)

cdk.Aspects.of(app).add(AwsSolutionsChecks())

app.synth()
