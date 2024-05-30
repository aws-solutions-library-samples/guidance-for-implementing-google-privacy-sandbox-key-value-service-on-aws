# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# Licensed under the Apache License Version 2.0 (the "License"). You may not use this file except
# in compliance with the License. A copy of the License is located at http://www.apache.org/licenses/
# or in the "license" file accompanying this file. This file is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, express or implied. See the License for the
# specific language governing permissions and limitations under the License.

# This builds the data formatter app and gives you choice of compute (EC2, ECS) and integration code (AWS CLI, AWS Python SDK)
from aws_cdk import (
    Stack,
    aws_ssm as ssm,
    CfnOutput,
    aws_iam as iam,
    aws_logs as logs,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as sfn_tasks,
    RemovalPolicy,
    Duration,
    aws_ecr as ecr,
    aws_lambda as _lambda,
    aws_ec2 as ec2,
    aws_events as events,
    aws_events_targets as targets,
    aws_sqs as sqs,
    aws_s3 as s3,
)
from aws_solutions_constructs.aws_s3_lambda import S3ToLambda
from aws_solutions_constructs.aws_lambda_stepfunctions import LambdaToStepfunctions

from constructs import Construct
from deployment import constants
from aws_cdk import aws_ecs as ecs

class dataLoader(Stack):

    def __init__(self, scope: Construct, construct_id: str, vpc: ec2.Vpc, ecr_repo: ecr.Repository, ec2_instance: ec2.Instance, input_bucket_name: str, output_bucket_name: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # read cli-compute option from cdk context
        compute = self.node.try_get_context("cli-compute")
        self.inp_bucket_name = input_bucket_name
        self.output_bucket_name = output_bucket_name
        # print(self.inp_bucket_name)
        # print(self.output_bucket_name)

        if self.node.try_get_context('output-key'):
            self.output_key = self.node.try_get_context('output-key')
        else:
            self.output_key = "output"
        if self.node.try_get_context('input-key'):
            self.input_key = self.node.try_get_context('input-key')
        else:
            self.input_key = "input"
        # print(f"output key: {self.output_key}")

        self.s3_bucket_url = f"s3://{self.inp_bucket_name}"
        # this is default values, actual file name will be picked up from the s3 object create event
        self.s3_object_url = f"{self.s3_bucket_url}/{self.input_key}/data.csv"
        # CfnOutput(self, "S3 Input Object URL", value=self.s3_object_url)
        self.vpc = vpc
        self.ecr_repo = ecr_repo
        self.ec2_instance = ec2_instance
        if compute == "ec2":
            self.create_s3_lambda_sfn()
        elif compute == "ecs":
        # google is using restrictive distroless container for data cli
        # An approach would be to build an aws cli/sdk app that does the aws integration and calls the data cli binaries eiifccnteuebulejbifhlirufvunlflbvrbbfdnghnlh
        # as a multistep build
            self.create_ecs_compute()
            self.create_event_framework()
        elif compute == "lambda":
            self.create_lambda_only_stack()
        elif compute == "all":
            self.create_all_compute_options()
        else:
            raise ValueError("Invalid compute type")
    
    def create_all_compute_options(self) -> None:
        """
        Creates all compute options for data cli
        """
        self.create_s3_lambda_sfn()
        self.create_ecs_compute()
        self.create_event_framework()
        self.create_lambda_only_stack()

    def get_deny_non_ssl_policy(self, queue_arn):
        """
        Helper method that returns a IAM policy statement that denies non SSL calls to SQS queue
        To be used in SSL queue creation
        """
        return iam.PolicyStatement(
            sid='Enforce TLS for all principals',
            effect=iam.Effect.DENY,
            principals=[
                iam.AnyPrincipal(),
            ],
            actions=[
                'sqs:*',
            ],
            resources=[queue_arn],
            conditions={
                'Bool': {'aws:SecureTransport': 'false'},
            },
        )
    
    # create eventbridge notification for upload of object in to input bucket
    def create_event_framework(self) -> None:
        """
        Creates AWS eventbridge components to route and archive events and DLQ
        Change event pattern json as needed
        """
        # create DLQ
        self.dead_letter_queue = sqs.Queue(
            self, 
            f"{constants.app_prefix}-eb-dlq",
            queue_name=f"{constants.app_prefix}-eb-dlq",
            retention_period=Duration.days(7),
            encryption=sqs.QueueEncryption.SQS_MANAGED,
            )
        # Deny non SSL traffic
        self.dead_letter_queue.add_to_resource_policy(self.get_deny_non_ssl_policy(self.dead_letter_queue.queue_arn))
        # assumes that the files will have .csv extension
        event_pattern_detail = {
                            "bucket": {
                                "name": [self.inp_bucket_name]
                                },
                            "object": {
                                "key": [ { "wildcard": f"{self.input_key}*.csv" } ]
                                }
                            }
        self.eb_rule = events.Rule(self, f"{constants.app_prefix}-s3-eb-rule",
                    rule_name=f"{constants.app_prefix}-s3-eb-rule",
                    event_pattern=events.EventPattern(
                        source=["aws.s3"],
                        detail_type=["Object Created"],
                        detail=event_pattern_detail
                    ),
                )
        
        self.eb_rule.add_target(targets.EcsTask(cluster=self.cluster,
                                    # change here to switch between awscli and python
                                    task_definition=self.python_task_definition, 
                                    launch_type=ecs.LaunchType.FARGATE,
                                    dead_letter_queue=self.dead_letter_queue,
                                    container_overrides=[targets.ContainerOverride(
                                        # change here to switch between awscli and python
                                        container_name=f"{constants.app_prefix}-python-cnt",
                                        # script uses environment variables passed from eventbridge
                                        environment=[
                                            {"name": "INP_BUCKET", "value": events.EventField.from_path("$.detail.bucket.name")},
                                            {"name": "INP_KEY", "value": events.EventField.from_path("$.detail.object.key")},
                                            {"name": "OUT_BUCKET", "value": self.output_bucket_name},
                                            {"name": "OUT_KEY", "value": self.output_key},
                                            ],
                                        )],
                                    )
                                )
        
        CfnOutput(self, "Event_Bridge_Rule", value=self.eb_rule.rule_arn)

    def create_ecs_compute(self) -> None:
        # log driver
        self.data_loader_log_group = logs.LogGroup(self, f"{constants.app_prefix}-data-loader-ecs-lg",removal_policy=RemovalPolicy.DESTROY, log_group_name=f"{constants.app_prefix}-data-loader-ecs-lg")
        self.data_loader_log_driver = ecs.AwsLogDriver(stream_prefix=f"{constants.app_prefix}-data-loader-ecs-ld", log_group=self.data_loader_log_group)

        self.cluster = ecs.Cluster(self, "cluster", vpc=self.vpc)
        self.create_awscli_container()
        self.create_python_container()
    
    def create_awscli_container(self):
        # create ecs container definition, task definition and cluster
        self.awscli_task_definition = ecs.FargateTaskDefinition(self, f"{constants.app_prefix}-awscli-tsk-def",
                                                    cpu=1024,
                                                    memory_limit_mib=2048,
                                                    runtime_platform=ecs.RuntimePlatform(
                                                        cpu_architecture=ecs.CpuArchitecture.ARM64,
                                                        operating_system_family=ecs.OperatingSystemFamily.LINUX
                                                    ),
                                                    family=f"{constants.app_prefix}-awscli-tsk-def-family"
                                                    )
        # give S3 bucket read and write access to execution role policy
        # NOTE: Below construct will include the task definition version on the role.
        # when you change task definition, verify that the event bridge is pointing to the new version and the iam role is updated
        s3_res_list = [f"arn:aws:s3:::{self.inp_bucket_name}",
                       f"arn:aws:s3:::{self.inp_bucket_name}/*",
                       f"arn:aws:s3:::{self.output_bucket_name}",
                       f"arn:aws:s3:::{self.output_bucket_name}/*"]
        self.awscli_task_definition.add_to_execution_role_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
            resources= s3_res_list
        ))
        self.awscli_task_definition.add_to_task_role_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
            resources=s3_res_list
        ))
        self.awscli_container_definition = ecs.ContainerDefinition(self, f"{constants.app_prefix}-awscli-cnt-def",
                                                              image=ecs.ContainerImage.from_ecr_repository(repository=self.ecr_repo, tag=constants.awscli_cntr_tag),
                                                              task_definition=self.awscli_task_definition,
                                                              cpu=1024,
                                                              memory_limit_mib=2048,
                                                              logging=self.data_loader_log_driver,
                                                              container_name=f"{constants.app_prefix}-awscli-cnt"
                                                            )
    
    def create_python_container(self):
        # create ecs container definition, task definition and cluster
        self.python_task_definition = ecs.FargateTaskDefinition(self, f"{constants.app_prefix}-python-tsk-def",
                                                    cpu=1024,
                                                    memory_limit_mib=2048,
                                                    runtime_platform=ecs.RuntimePlatform(
                                                        cpu_architecture=ecs.CpuArchitecture.ARM64,
                                                        operating_system_family=ecs.OperatingSystemFamily.LINUX
                                                    ),
                                                    family=f"{constants.app_prefix}-python-tsk-def-family"
                                                    )
        # give S3 bucket read and write access to execution role policy
        # NOTE: Below construct will include the task definition version on the role.
        # when you change task definition, verify that the event bridge is pointing to the new version and the iam role is updated
        s3_res_list = [f"arn:aws:s3:::{self.inp_bucket_name}",
                       f"arn:aws:s3:::{self.inp_bucket_name}/*",
                       f"arn:aws:s3:::{self.output_bucket_name}",
                       f"arn:aws:s3:::{self.output_bucket_name}/*"]
        self.python_task_definition.add_to_execution_role_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
            resources= s3_res_list
        ))
        self.python_task_definition.add_to_task_role_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
            resources=s3_res_list
        ))
        self.python_container_definition = ecs.ContainerDefinition(self, f"{constants.app_prefix}-python-cnt-def",
                                                              image=ecs.ContainerImage.from_ecr_repository(repository=self.ecr_repo, tag=constants.python_cntr_tag),
                                                              task_definition=self.python_task_definition,
                                                              cpu=1024,
                                                              memory_limit_mib=2048,
                                                              logging=self.data_loader_log_driver,
                                                              container_name=f"{constants.app_prefix}-python-cnt"
                                                            )
    
    def create_ecs_sm_def(self) -> None:
    # stepfunction task to run ECS task
    # creating a function to keep it flexible to go back and forth between ecs and ec2 based compute
        self.ecs_sfn_task = sfn_tasks.EcsRunTask(self, "Run ECS Data Loader",
                                        launch_target=sfn_tasks.EcsFargateLaunchTarget(platform_version=ecs.FargatePlatformVersion.LATEST),
                                        integration_pattern=sfn.IntegrationPattern.RUN_JOB,
                                        cluster=self.cluster,
                                        task_definition=self.python_task_definition,
                                    )
        start_state = sfn.Pass(self, "StartState")
        self.ecs_sm_definition = start_state.next(self.ecs_sfn_task)
    
    def create_ec2_sm_def(self) -> None:

        self.ec2_instance_arn = f"arn:aws:ec2:{constants.region}:{constants.acc}:instance/{self.ec2_instance.instance_id}"
        succeed_nothing_to_job = sfn.Succeed(
            self, "Success",
            comment='Job succeeded'
        )
        # check ec2 instance state
        check_ec2_state_task = sfn_tasks.CallAwsService(self, "CheckEC2State",
                                                            service="ec2",
                                                            action="describeInstanceStatus",
                                                            parameters={
                                                                "InstanceIds": [self.ec2_instance.instance_id],
                                                                "IncludeAllInstances": True
                                                            },
                                                            iam_resources=["*"]
        )

        # wait 30 seconds
        wait_task=sfn.Wait(self,"Wait 30 Seconds for Ec2",
            time=sfn.WaitTime.duration(Duration.seconds(30)))
        
        wait_task2=sfn.Wait(self,"Wait 30 Seconds for SSM command",
            time=sfn.WaitTime.duration(Duration.seconds(30)))
        

        # start ec2 instance
        start_ec2_task = sfn_tasks.CallAwsService(self, "StartEC2Instance",
                                                    service="ec2",
                                                    action="startInstances",
                                                    parameters={
                                                        "InstanceIds": [self.ec2_instance.instance_id]
                                                    },
                                                    iam_resources=[self.ec2_instance_arn]
                                                )
       
        # run deltagen command
        run_delta_gen_task = sfn_tasks.CallAwsService(self, "RunSSMCommandDeltaGen",
                                                            service="ssm",
                                                            action="sendCommand",
                                                            parameters={
                                                                "InstanceIds": [self.ec2_instance.instance_id],
                                                                "DocumentName": "AWS-RunShellScript",
                                                                # TODO change this to dynamic input from sfn
                                                                "Parameters": {
                                                                    "commands": [f"/home/ec2-user/data-cli/papi-delta-gen.sh {self.s3_object_url} {self.s3_bucket_url}/output"]
                                                                }
                                                            },
                                                            iam_resources=[f"arn:aws:ssm:{constants.region}::document/AWS-RunShellScript", self.ec2_instance_arn],
                                                            output_path="$.Command",
                                                            task_timeout=sfn.Timeout.duration(Duration.minutes(120))
                                                        )
        
        # check s3 copy status
        get_delta_gen_status_task = sfn_tasks.CallAwsService(self, "GetDeltaGenStatus",
                                                                service="ssm",
                                                                action="getCommandInvocation",
                                                                parameters={
                                                                        "CommandId": sfn.JsonPath.string_at("$.CommandId"),
                                                                        "InstanceId": self.ec2_instance.instance_id
                                                                },
                                                                iam_resources=["*"],
        )

        # stop ec2 instance
        stop_ec2_task = sfn_tasks.CallAwsService(self, "StopEC2Instance",
                                                    service="ec2",
                                                    action="stopInstances",
                                                    parameters={
                                                        "InstanceIds": [self.ec2_instance.instance_id]
                                                    },
                                                    iam_resources=[self.ec2_instance_arn]
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
        stop_ec2_task.add_catch(catch_job_error, errors=['States.ALL'],result_path='$.error')
        stop_ec2_task.add_retry(max_attempts=2,backoff_rate=1.05,interval=Duration.seconds(60),errors=["stopInstanceRetry"])
        run_delta_gen_task.add_catch(catch_job_error, errors=['States.ALL'],result_path='$.error')
        run_delta_gen_task.add_retry(max_attempts=2,backoff_rate=1.05,interval=Duration.seconds(60),errors=["deltaGenTaskRetry"])
        get_delta_gen_status_task.add_catch(catch_job_error, errors=['States.ALL'],result_path='$.error')
        get_delta_gen_status_task.add_retry(max_attempts=2,backoff_rate=1.05,interval=Duration.seconds(60),errors=["deltaGenStatusRetry"])
        
        catch_job_error.next(job_failed)

        # check instance status and which path to take
        ec2_start_or_ssm_command_choice = sfn.Choice(self, 'Is instance running?')
        instance_running_condition = sfn.Condition.string_equals("$.InstanceStatuses[0].InstanceState.Name", "running")

        # check s3 execution status and which path to take
        deltagen_status_choice = sfn.Choice(self, 'Is DeltaGen done?')
        deltagen_running_condition1 = sfn.Condition.string_equals("$.Status", "Inprogress")
        deltagen_running_condition2 = sfn.Condition.string_equals("$.Status", "Pending")
        deltagen_running_condition = sfn.Condition.or_(deltagen_running_condition1, deltagen_running_condition2)
        deltagen_failed_condition = sfn.Condition.string_equals("$.Status", "Failed")

        # chain the steps togther
        start_ec2_task.next(wait_task).next(check_ec2_state_task)
        
        run_delta_gen_task.next(wait_task2).next(get_delta_gen_status_task)
        get_delta_gen_status_task.next(deltagen_status_choice.when(deltagen_running_condition, wait_task2).when(deltagen_failed_condition, catch_job_error).otherwise(stop_ec2_task))
        
        stop_ec2_task.next(succeed_nothing_to_job)

        self.ec2_sm_definition = check_ec2_state_task.next(ec2_start_or_ssm_command_choice.when(instance_running_condition, run_delta_gen_task).otherwise(start_ec2_task)) 
        
    def create_s3_lambda_sfn(self) -> None:
    # while lambda could run the data cli container and process the input file
    # putting the processing in to a step function gives additional observability options
    # and rerunning of the workflow etc
    # NOTE to be enhanced in the future
        print("WARNING: EC2 based data format conversion is not available in this version. This is a placeholder option for customers to consider and build on")
        pass

    def create_lambda_only_stack(self) -> None:
        print("WARNING: Lambda based data format conversion is not available in this version. This is a placeholder option for customers to consider and build on")
        pass
