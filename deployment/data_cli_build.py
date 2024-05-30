# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# Licensed under the Apache License Version 2.0 (the "License"). You may not use this file except
# in compliance with the License. A copy of the License is located at http://www.apache.org/licenses/
# or in the "license" file accompanying this file. This file is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, express or implied. See the License for the
# specific language governing permissions and limitations under the License.

# This builds stack needed to automate the build of binaries, AMI and Container images
from aws_cdk import (
    Stack,
    aws_cloud9 as cloud9,
    aws_ec2 as ec2,
    aws_ssm as ssm,
    CfnOutput,
    aws_iam as iam,
    aws_logs as logs,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as sfn_tasks,
    RemovalPolicy,
    Duration,
    aws_ecr as ecr,
    aws_imagebuilder as imagebuilder,
)

from constructs import Construct
from deployment import constants
import json

class dataCliBuild(Stack):

    def __init__(self, scope: Construct, construct_id: str, vpc: ec2.Vpc, s3_bucket_arn: str, s3_bucket_url: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        # read build_type as input from cdk context
        self.build_infra = self.node.try_get_context("build-infra")
        self.build_instance_type = self.node.try_get_context("build-instance-type")

        # create s3 url from the s3_bucket_arn
        self.s3_url = s3_bucket_url
        # print(self.s3_url)
        self.s3_bucket_arn = s3_bucket_arn
        # create cloudwatch log group
        self.log_group = logs.LogGroup(self, f"{constants.app_prefix}-data-cli-build-log-group",
                                            log_group_name=f"{constants.app_prefix}-data-cli-build-log-group",
                                            removal_policy=RemovalPolicy.DESTROY,retention=logs.RetentionDays.ONE_WEEK)
        
        self.create_ecr_repo()
        if self.build_infra == "stepfunction":
            self.create_build_instance(vpc, s3_bucket_arn)
            self.create_build_sfn_workflow()
        elif self.build_infra == "imagebuilder":
            self.create_imagebuilder_pipeline()
        elif self.build_infra == "all":
            self.create_build_instance(vpc, s3_bucket_arn)
            self.create_build_sfn_workflow()
            self.create_imagebuilder_pipeline()
        else:
            raise ValueError("Invalid compute type")

    # create ecr repo
    def create_ecr_repo(self) -> None:
        self.ecr_repo = ecr.Repository(self, f"{constants.app_prefix}-ecr-repo",
                                        repository_name=f"{constants.app_prefix}-ecr-repo",
                                        # on destroy the images are not removed by cfn. Either retain the repo
                                        # or delete the images manually
                                        removal_policy=RemovalPolicy.RETAIN_ON_UPDATE_OR_DELETE)
        CfnOutput(self, "ecr_repo_url", value=self.ecr_repo.repository_uri)

    # create an ec2 instance that can download the repo and run build commands
    def create_build_instance(self, vpc: ec2.Vpc, s3_bucket_arn: str) -> None:

        # create EC2 instance
        self.build_instance = ec2.Instance(self, f"{constants.app_prefix}-data-cli-build-instance",
                                            instance_type=ec2.InstanceType(self.build_instance_type),
                                            machine_image=ec2.AmazonLinuxImage(
                                                generation=ec2.AmazonLinuxGeneration.AMAZON_LINUX_2023,
                                            ),
                                            vpc=vpc,
                                            ssm_session_permissions=True,
                                            detailed_monitoring=True,
                                            block_devices=[ec2.BlockDevice(device_name="/dev/xvda",
                                                            volume=ec2.BlockDeviceVolume.ebs(
                                                                volume_size=30,
                                                                delete_on_termination=True,
                                                                encrypted=True
                                                                )
                                                            )
                                                        ],
        )
        self.build_instance_arn = f"arn:aws:ec2:{constants.region}:{constants.acc}:instance/{self.build_instance.instance_id}"
                                                        
        
        # cloudwatch log group S3 and ECR permissions
        self.log_group_policy = iam.PolicyStatement(effect=iam.Effect.ALLOW, actions=["logs:*"], resources=[self.log_group.log_group_arn])
        self.s3_policy = iam.PolicyStatement(effect=iam.Effect.ALLOW, actions=["s3:*"], resources=[s3_bucket_arn,f"{s3_bucket_arn}/*"])
        self.ecr_policy = iam.PolicyStatement(effect=iam.Effect.ALLOW, actions=["ecr:*"],resources=["*"])
        self.build_instance.add_to_role_policy(self.log_group_policy)
        self.build_instance.add_to_role_policy(self.s3_policy)
        self.build_instance.add_to_role_policy(self.ecr_policy)
        CfnOutput(self, "build_instance_id", value=self.build_instance.instance_id)
        
    # Create a stepfunction statemachine that starts the build ec2 instance and runs a ssm run command and finally stops the server
    def create_build_sfn_workflow(self) -> None:

        succeed_nothing_to_job = sfn.Succeed(
            self, "Success",
            comment='Job succeeded'
        )
        # check ec2 instance state
        check_ec2_state_task = sfn_tasks.CallAwsService(self, "CheckEC2State",
                                                            service="ec2",
                                                            action="describeInstanceStatus",
                                                            parameters={
                                                                "InstanceIds": [self.build_instance.instance_id],
                                                                "IncludeAllInstances": True
                                                            },
                                                            iam_resources=["*"]
        )

        # wait 30 seconds
        wait_task=sfn.Wait(self,"Wait 30 Seconds for Ec2",
            time=sfn.WaitTime.duration(Duration.seconds(30)))
        
        wait_task2=sfn.Wait(self,"Wait 30 Seconds for S3 copy SSM Command",
            time=sfn.WaitTime.duration(Duration.seconds(30)))
        
        wait_task3=sfn.Wait(self,"Wait 30 Seconds for build SSM Command",
            time=sfn.WaitTime.duration(Duration.seconds(30)))

        # start ec2 instance
        start_ec2_task = sfn_tasks.CallAwsService(self, "StartEC2Instance",
                                                    service="ec2",
                                                    action="startInstances",
                                                    parameters={
                                                        "InstanceIds": [self.build_instance.instance_id]
                                                    },
                                                    iam_resources=[self.build_instance_arn]
                                                )
        # run s3 copy to load shell scripts in to VM
        run_s3_copy_task = sfn_tasks.CallAwsService(self, "RunSSMCommandS3Copy",
                                                            service="ssm",
                                                            action="sendCommand",
                                                            parameters={
                                                                "InstanceIds": [self.build_instance.instance_id],
                                                                "DocumentName": "AWS-RunShellScript",
                                                                "Parameters": {
                                                                    "commands": [f"aws s3 cp {self.s3_url}/papi-data-cli-build.sh /home/ec2-user/data-cli/", 
                                                                                 f"aws s3 cp {self.s3_url}/papi-delta-gen.sh /home/ec2-user/data-cli/",
                                                                                 f"aws s3 cp {self.s3_url}/datacli-w-awscli-docker/Dockerfile /home/ec2-user/data-cli/", 
                                                                                 f"aws s3 cp {self.s3_url}/datacli-w-awscli-docker/papi-delta-filegen-s3.sh /home/ec2-user/data-cli/",
                                                                                 "chmod 755 /home/ec2-user/data-cli/papi-data-cli-build.sh",
                                                                                 "chmod 755 /home/ec2-user/data-cli/papi-delta-gen.sh", 
                                                                                 "sudo yum update", "sudo yum -y install git docker", 
                                                                                 "sudo service docker start"]
                                                                }
                                                            },
                                                            iam_resources=[f"arn:aws:ssm:{constants.region}::document/AWS-RunShellScript", self.build_instance_arn],
                                                            output_path="$.Command"
                                                        )
        
        # check s3 copy status
        get_s3_copy_status_task = sfn_tasks.CallAwsService(self, "GetS3CopyStatus",
                                                                service="ssm",
                                                                action="getCommandInvocation",
                                                                parameters={
                                                                        "CommandId": sfn.JsonPath.string_at("$.CommandId"),
                                                                        "InstanceId": self.build_instance.instance_id
                                                                },
                                                                iam_resources=["*"],
        )

        # run build command
        run_build_task = sfn_tasks.CallAwsService(self, "RunSSMCommandBuild",
                                                            service="ssm",
                                                            action="sendCommand",
                                                            parameters={
                                                                "InstanceIds": [self.build_instance.instance_id],
                                                                "DocumentName": "AWS-RunShellScript",
                                                                "Parameters": {
                                                                    "commands": [f"/home/ec2-user/data-cli/papi-data-cli-build.sh {constants.acc} {constants.region}"]
                                                                }
                                                            },
                                                            iam_resources=[f"arn:aws:ssm:{constants.region}::document/AWS-RunShellScript", self.build_instance_arn],
                                                            output_path="$.Command",
                                                            task_timeout=sfn.Timeout.duration(Duration.minutes(120))
                                                        )
        
        # check s3 copy status
        get_build_status_task = sfn_tasks.CallAwsService(self, "GetBuildStatus",
                                                                service="ssm",
                                                                action="getCommandInvocation",
                                                                parameters={
                                                                        "CommandId": sfn.JsonPath.string_at("$.CommandId"),
                                                                        "InstanceId": self.build_instance.instance_id
                                                                },
                                                                iam_resources=["*"],
        )

        # stop ec2 instance
        stop_ec2_task = sfn_tasks.CallAwsService(self, "StopEC2Instance",
                                                    service="ec2",
                                                    action="stopInstances",
                                                    parameters={
                                                        "InstanceIds": [self.build_instance.instance_id]
                                                    },
                                                    iam_resources=[self.build_instance_arn]
                                                )
        
        catch_job_error = sfn.Pass(
            self,
            "Catch an Error",
            result_path=sfn.JsonPath.DISCARD
        )

        job_failed = sfn.Fail(self, "Job Failed",
            cause="Job Failed",
            error="JOB FAILED"
        )

        # catch error and retry
        check_ec2_state_task.add_catch(catch_job_error, errors=['States.ALL'],result_path='$.error')
        check_ec2_state_task.add_retry(max_attempts=2,backoff_rate=1.05,interval=Duration.seconds(60),errors=["checkInstanceRetry"])
        start_ec2_task.add_catch(catch_job_error, errors=['States.ALL'],result_path='$.error')
        start_ec2_task.add_retry(max_attempts=2,backoff_rate=1.05,interval=Duration.seconds(60),errors=["startInstanceRetry"])
        run_s3_copy_task.add_catch(catch_job_error, errors=['States.ALL'],result_path='$.error')
        run_s3_copy_task.add_retry(max_attempts=2,backoff_rate=1.05,interval=Duration.seconds(60),errors=["s3CopyRetry"])
        stop_ec2_task.add_catch(catch_job_error, errors=['States.ALL'],result_path='$.error')
        stop_ec2_task.add_retry(max_attempts=2,backoff_rate=1.05,interval=Duration.seconds(60),errors=["stopInstanceRetry"])
        get_s3_copy_status_task.add_catch(catch_job_error, errors=['States.ALL'],result_path='$.error')
        get_s3_copy_status_task.add_retry(max_attempts=2,backoff_rate=1.05,interval=Duration.seconds(60),errors=["s3StatusRetry"])
        run_build_task.add_catch(catch_job_error, errors=['States.ALL'],result_path='$.error')
        run_build_task.add_retry(max_attempts=2,backoff_rate=1.05,interval=Duration.seconds(60),errors=["buildTaskRetry"])
        get_build_status_task.add_catch(catch_job_error, errors=['States.ALL'],result_path='$.error')
        get_build_status_task.add_retry(max_attempts=2,backoff_rate=1.05,interval=Duration.seconds(60),errors=["buildStatusRetry"])
        
        catch_job_error.next(job_failed)

        # check instance status and which path to take
        ec2_start_or_ssm_command_choice = sfn.Choice(self, 'Is instance running?')
        instance_running_condition = sfn.Condition.string_equals("$.InstanceStatuses[0].InstanceState.Name", "running")

        # check s3 execution status and which path to take
        s3_status_choice = sfn.Choice(self, 'Is S3 copy done?')
        s3_running_condition1 = sfn.Condition.string_equals("$.Status", "Pending")
        s3_running_condition2 = sfn.Condition.string_equals("$.Status", "Inprogress")
        s3_running_condition = sfn.Condition.or_(s3_running_condition1, s3_running_condition2)
        s3_failed_condition = sfn.Condition.string_equals("$.Status", "Failed")

        # check s3 execution status and which path to take
        build_status_choice = sfn.Choice(self, 'Is build done?')
        build_running_condition1 = sfn.Condition.string_equals("$.Status", "Inprogress")
        build_running_condition2 = sfn.Condition.string_equals("$.Status", "Pending")
        build_running_condition = sfn.Condition.or_(build_running_condition1, build_running_condition2)
        build_failed_condition = sfn.Condition.string_equals("$.Status", "Failed")

        # chain the steps togther
        start_ec2_task.next(wait_task).next(check_ec2_state_task)
        
        run_s3_copy_task.next(wait_task2).next(get_s3_copy_status_task)
        get_s3_copy_status_task.next(s3_status_choice.when(s3_running_condition, wait_task2).when(s3_failed_condition, catch_job_error).otherwise(run_build_task))

        run_build_task.next(wait_task3).next(get_build_status_task)
        get_build_status_task.next(build_status_choice.when(build_running_condition, wait_task3).when(build_failed_condition, catch_job_error).otherwise(stop_ec2_task))
        
        stop_ec2_task.next(succeed_nothing_to_job)

        definition = check_ec2_state_task.next(ec2_start_or_ssm_command_choice.when(instance_running_condition, run_s3_copy_task).otherwise(start_ec2_task)) 

        
        # Create state machine
        self.state_machine = sfn.StateMachine(
            self, "data-cli-build-workflow",
            state_machine_name ="data-cli-build-workflow",
            logs=sfn.LogOptions(
                destination=logs.LogGroup(self, "UnfurlStateMachineLogGroup"),
                level=sfn.LogLevel.ALL,
            ),
            timeout=Duration.minutes(120),
            tracing_enabled=True,
            definition_body=sfn.DefinitionBody.from_chainable(definition),
        )
        
        # add ecr repo as a dependency for sfn state machine
        self.state_machine.node.add_dependency(self.ecr_repo)
        self.state_machine.node.add_dependency(self.build_instance)

        CfnOutput(self, "State Machine Arn", value=self.state_machine.state_machine_arn)

    def create_imagebuilder_pipeline(self) -> None:
        """
        Creates the image builder pipeline for data cli build
        """
        # create custom IAM role based on EC2InstanceProfileForImageBuilder
        # give S3 bucket read and write access to execution role policy
        s3_res_list = [self.s3_bucket_arn,
                       f"{self.s3_bucket_arn}/*"]
        inline_policy_doc = iam.PolicyDocument(statements=[iam.PolicyStatement(
                                                effect=iam.Effect.ALLOW,
                                                actions=["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
                                                resources= s3_res_list
                                            )])
        # iam role
        self.image_builder_role = iam.Role(self, f"{constants.app_prefix}-data-cli-build-role",
                                           role_name=f"{constants.app_prefix}-data-cli-build-role",
                                            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
                                            managed_policies=[iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore"),
                                                                iam.ManagedPolicy.from_aws_managed_policy_name("EC2InstanceProfileForImageBuilder"),
                                                                iam.ManagedPolicy.from_aws_managed_policy_name("EC2InstanceProfileForImageBuilderECRContainerBuilds")],
                                            inline_policies={"s3accesspolicy": inline_policy_doc},)
        
        self.instance_profile = iam.InstanceProfile(self, f"{constants.app_prefix}-data-cli-build-inst-prof",
                                                role=self.image_builder_role,
                                                instance_profile_name=f"{constants.app_prefix}-data-cli-build-inst-prof",
                                            )
        # create image builder component data cli
        # this creates an ami and a container image that will be used by the next component
        self.component_data_cli_build = imagebuilder.CfnComponent(self, f"{constants.app_prefix}-data-cli-build-cmp",
                                                                name=f"{constants.app_prefix}-data-cli-build-cmp",
                                                                platform="Linux",
                                                                version="1.0.0",
                                                                description="Automates the build of data cli container image",
                                                                supported_os_versions=["Ubuntu 20","Ubuntu 22"],
                                                                uri=f"{self.s3_url}/imagebuilder/{constants.app_prefix}-data-cli-build-cmp.yml"
                                                                )
        # create image builder component for aws+data cli
        # splitting this out as a separate component to decouple the long running data cli build component from this
        # this allows faster iteration and testing of the build process when changes are needed
        # Create a new recipe and pipeline using this component to iterate different container configurations
        self.component_aws_data_cli_build = imagebuilder.CfnComponent(self, f"{constants.app_prefix}-aws-data-cli-build-cmp",
                                                                name=f"{constants.app_prefix}-aws-data-cli-build-cmp",
                                                                platform="Linux",
                                                                version="1.0.0",
                                                                description="Automates the build of aws + data cli container image",
                                                                supported_os_versions=["Ubuntu 20","Ubuntu 22"],
                                                                uri=f"{self.s3_url}/imagebuilder/{constants.app_prefix}-aws-data-cli-build-cmp.yml"
                                                                )
        self.component_python_data_cli_build = imagebuilder.CfnComponent(self, f"{constants.app_prefix}-python-data-cli-build-cmp",
                                                                name=f"{constants.app_prefix}-python-data-cli-build-cmp",
                                                                platform="Linux",
                                                                version="1.0.0",
                                                                description="Automates the build of Python sdk + data cli container image",
                                                                supported_os_versions=["Ubuntu 20","Ubuntu 22"],
                                                                uri=f"{self.s3_url}/imagebuilder/{constants.app_prefix}-python-data-cli-build-cmp.yml"
                                                                )
        
        self.component_data_cli_test = imagebuilder.CfnComponent(self, f"{constants.app_prefix}-data-cli-test-cmp",
                                                        name=f"{constants.app_prefix}-data-cli-test-cmp",
                                                        platform="Linux",
                                                        version="1.0.0",
                                                        description="Automates the test of data cli container image",
                                                        supported_os_versions=["Ubuntu 20","Ubuntu 22"],
                                                        uri=f"{self.s3_url}/imagebuilder/{constants.app_prefix}-data-cli-test-cmp.yml"
                                                        )

        # create image builder infrastructure configuration - Customize this to do build in specific subnets and security group associations
        self.infra_config = imagebuilder.CfnInfrastructureConfiguration(self, f"{constants.app_prefix}-data-cli-build-infra",
                                                                    name=f"{constants.app_prefix}-data-cli-build-infra",
                                                                    instance_profile_name=self.instance_profile.instance_profile_name,
                                                                    # giving instance type may result in cpu architecture conflict with the 
                                                                    # parent_image option in image_recipe
                                                                    # instance_types=[self.build_instance_type]
                                                                    )
        
        # create image builder distribution configuration
        self.dist_config = imagebuilder.CfnDistributionConfiguration(self, f"{constants.app_prefix}-data-cli-build-dist",
                                                                        name=f"{constants.app_prefix}-data-cli-build-dist",
                                                                        distributions=[imagebuilder.CfnDistributionConfiguration.DistributionProperty(
                                                                                        region=constants.region,
                                                                                        ami_distribution_configuration={"description": "AMI Distribution Config for PAPI KV data cli build"})]
                                                                    )
        
        aws_cli_cmp_arn = f"arn:aws:imagebuilder:{self.region}:aws:component/aws-cli-version-2-linux/1.0.4/1"
        dcr_cmp_arn = f"arn:aws:imagebuilder:{self.region}:aws:component/docker-ce-ubuntu/1.0.0/1"
        # create image builder image recipe for data cli
        self.data_cli_image_recipe = imagebuilder.CfnImageRecipe(self, f"{constants.app_prefix}-data-cli-build-recipe",
                                                        name=f"{constants.app_prefix}-data-cli-build-recipe",
                                                        parent_image=f"arn:aws:imagebuilder:{constants.region}:aws:image/ubuntu-server-22-lts-arm64/x.x.x",
                                                        version="1.0.0",
                                                        components=[{"componentArn": aws_cli_cmp_arn},
                                                                    {"componentArn": dcr_cmp_arn},
                                                                    # dynamically pass the s3 urls when recipe is created
                                                                    {"componentArn": self.component_data_cli_build.attr_arn,
                                                                        "parameters":[
                                                                                    {"name":"awsAccountID",
                                                                                    "value":[constants.acc]},
                                                                                    {"name":"awsRegion",
                                                                                    "value":[constants.region]}
                                                                                ]},
                                                                    {"componentArn": self.component_aws_data_cli_build.attr_arn,
                                                                        "parameters":[{"name":"s3UrlDockerFile",
                                                                                    "value":[f"{self.s3_url}/datacli-w-awscli-docker/Dockerfile"]},
                                                                                    {"name":"s3UrlEntryPointScript",
                                                                                    "value":[f"{self.s3_url}/datacli-w-awscli-docker/papi-delta-filegen-s3.sh"]},
                                                                                    {"name":"awsAccountID",
                                                                                    "value":[constants.acc]},
                                                                                    {"name":"awsRegion",
                                                                                    "value":[constants.region]}
                                                                                ]},
                                                                    {"componentArn": self.component_python_data_cli_build.attr_arn,
                                                                        "parameters":[{"name":"s3UrlDockerFile",
                                                                                    "value":[f"{self.s3_url}/datacli-w-python-docker/Dockerfile"]},
                                                                                    {"name":"s3UrlEntryPointScript",
                                                                                    "value":[f"{self.s3_url}/datacli-w-python-docker/papi-delta-filegen-s3.py"]},
                                                                                    {"name":"s3UrlRequirements",
                                                                                    "value":[f"{self.s3_url}/datacli-w-python-docker/requirements.txt"]},
                                                                                    {"name":"awsAccountID",
                                                                                    "value":[constants.acc]},
                                                                                    {"name":"awsRegion",
                                                                                    "value":[constants.region]}
                                                                                ]},
                                                                    {"componentArn": self.component_data_cli_test.attr_arn}
                                                                ],
                                                                block_device_mappings=[imagebuilder.CfnImageRecipe.InstanceBlockDeviceMappingProperty(
                                                                    device_name="/dev/sda1",
                                                                    ebs=imagebuilder.CfnImageRecipe.EbsInstanceBlockDeviceSpecificationProperty(
                                                                        delete_on_termination=True,
                                                                        encrypted=True,
                                                                        kms_key_id=f"arn:aws:kms:{constants.region}:{constants.acc}:alias/aws/ebs",
                                                                        # need atleast 30GB for build
                                                                        volume_size=30,
                                                                        # this could be tuned for better build performance - gp3,io1,io2
                                                                        volume_type="gp2",
                                                                        # this could be tuned for better build performance, for gp3,io1, io2
                                                                        # iops=100
                                                                        ),
                                                                    )
                                                                ],
                                                            )
        
        # create image builder pipeline
        self.image_pipeline = imagebuilder.CfnImagePipeline(self, f"{constants.app_prefix}-data-cli-build-pipeln",
                                                        name=f"{constants.app_prefix}-data-cli-build-pipeln",
                                                        description="Pipeline to build the google chrome privacy sandbox papi data loader instance AMI and container image",
                                                        image_recipe_arn=self.data_cli_image_recipe.attr_arn,
                                                        infrastructure_configuration_arn=self.infra_config.attr_arn,
                                                        distribution_configuration_arn=self.dist_config.attr_arn,
                                                        )
    # this is for testing purposes only, not deployed by stack by default
    def create_cloud9_env(self, subnet_id: str):
        # owner arn
        owner_arn = f"arn:aws:iam::{constants.acc}:root"

        # create a cloud9 instance
        c9_env = cloud9.CfnEnvironmentEC2(self, 
                                                    f"{constants.app_prefix}-data-cli-build",
                                                    image_id="amazonlinux-2023-x86_64",
                                                    instance_type=self.build_instance_type, # Need more storage for build artifact storage
                                                    name=f"{constants.app_prefix}-data-cli-build",
                                                    description="Builds the data cli container image",
                                                    automatic_stop_time_minutes=45,
                                                    connection_type="CONNECT_SSM",
                                                    subnet_id=subnet_id,
                                                    owner_arn=owner_arn)
        
        c9_arn_list = c9_env.attr_arn.split(":")
        c9_env_id = c9_arn_list[len(c9_arn_list)-1]
        c9_instance_name = f"aws-cloud9-{c9_env.name}-{c9_env_id}"

        # cfn output
        CfnOutput(self, "c9_instance_name", value=c9_instance_name)

        # create ssm document that runs a shell command on the cloud9 instance
        ssm_doc = ssm.CfnDocument(self, f"{constants.app_prefix}-data-cli-build-ssm-doc",
                                    name=f"{constants.app_prefix}-data-cli-build-ssm-doc",
                                    document_type="Command",
                                    content={
                                        "schemaVersion": "1.2",
                                        "description": "Builds the data cli container image",
                                        "runtimeConfig": {
                                            "aws:runShellScript": {
                                                "properties": [
                                                    {
                                                        "id": "0.aws:runShellScript",
                                                        "runCommand": [
                                                            f"git clone {constants.papi_repo_url}"
                                                        ]
                                                    }
                                                ]
                                            }
                                        }
                                    }
        )
