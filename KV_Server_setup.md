# Building and deployment of Key/Value Server on AWS

[Key/Value Server setup on AWS instructions](https://github.com/privacysandbox/protected-auction-key-value-service/blob/main/docs/deployment/deploying_on_aws.md) from Privacy Sandbox.
- Note: The instructions written in this document are for running a test Key/Value server that does not yet have full privacy protection. The goal is for interested users to gain familiarity with the functionality and high level user experience. As more privacy protection mechanisms are added to the system, this document will be updated accordingly

## Pre-requisites
- For the initial deployment and testing of the Key/Value server, you must [have or create an Amazon Web Services (AWS) account](https://portal.aws.amazon.com/billing/signup/iam).     
    You'll need API access, as well as your key ID and secret key.
- You will need a  public [AWS ACM](https://docs.aws.amazon.com/acm/latest/userguide/acm-overview.html) certificate   
    Follow these steps to [request a public certificate](https://docs.aws.amazon.com/acm/latest/userguide/gs-acm-request-public.html). If you want to import an existing public certificate into ACM, follow these steps to [import the certificate](https://docs.aws.amazon.com/acm/latest/userguide/import-certificate.html).

## Outline of steps
- Set up your AWS account
    - Setup AWS CLI
    - Setup S3 bucket for Terraform states
- Build the Key/Value server artifacts from the repository
    - Before starting the build process, install Docker.
    - Get the source code from GitHub
    - Build the Amazon Machine Image (AMI)
- Deploy on AWS using Terraform.
    - Push artifacts into your AWS Elastic Container Registry
    - Run `dist/aws/push_sqs` to push the SQS cleanup lambda image to AWS ECR.
    - Update Terraform configuration. The description of each variable is described in [AWS Terraform Vars](https://github.com/privacysandbox/protected-auction-key-value-service/blob/main/docs/AWS_Terraform_vars.md) document.
    - Confirm resource generation    
    Atleast 2 EC2 instances. 1 SSH instance and at least one or more Key/Value server depending on the autoscaling capacity you have specified.     
    The S3 bucket should be associated with an SNS topic.      
    SNS with SQS subscribed to it
    - Take note of the [ARN](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference-arns.html) of the Application Load Balancer(ALB) created as part of the Terraform installation.  
    This ARN will be needed while installing the data loader stack in [README.md](./README.md)
- Loading data into the server      
    - Refer to [README.md](./README.md) and the GitHub [documentation](https://github.com/privacysandbox/protected-auction-key-value-service/blob/main/docs/data_loading/loading_data.md#loading-data-into-the-keyvalue-server) to populate data in the server.     
    A [sample delta file](./assets/sample_delta_file.zip) is provided for testing [Riegeli](https://github.com/google/riegeli) format

## FAQ, known issues, additional considerations, and limitations

**Known issues**
- Failures when building images with newer versions of the docker API. 
```
Docker error: PullError [ E50 ] Docker image pull error. Such error appears when trying to build an EIF file, but pulling the corresponding docker image fails. In this case, the error backtrace provides detailed informatino on the failure reason
```
Issue can be addressed by downgrading to Docker 24. [See](https://github.com/aws/aws-nitro-enclaves-cli/issues/537)

**Additional considerations**
- Building the Amazon Machine Image (AMI) from the repository may take a while depending on the build machine. It is recommended to use [c7xlarge or similar](https://aws.amazon.com/ec2/instance-types/) to cut down the build times to reasonable values (in minutes)
- OS: The build process can also be run on [Amazon Linux 2023](https://aws.amazon.com/linux/amazon-linux-2023/) in addition to Debian mentioned in the GitHub documentation. 

