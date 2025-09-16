#!/usr/bin/env python3
"""
AWS Data Platform CDK Application
Main entry point for deploying the complete data platform infrastructure
"""

import os
from aws_cdk import App, Environment, Tags
from infrastructure.stacks.streaming.kinesis_stack import KinesisStreamingStack
from infrastructure.stacks.streaming.lambda_processor_stack import LambdaProcessorStack
from infrastructure.stacks.storage.s3_data_lake_stack import S3DataLakeStack
from infrastructure.stacks.storage.dynamodb_stack import DynamoDBStack
from infrastructure.stacks.storage.redshift_stack import RedshiftStack
from infrastructure.stacks.batch.emr_stack import EMRStack
from infrastructure.stacks.batch.glue_stack import GlueETLStack
from infrastructure.stacks.batch.athena_stack import AthenaStack
from infrastructure.stacks.ml.sagemaker_stack import SageMakerStack
from infrastructure.stacks.ml.feature_store_stack import FeatureStoreStack
from infrastructure.stacks.monitoring.cloudwatch_stack import CloudWatchStack
from infrastructure.stacks.analytics.quicksight_stack import QuickSightStack
from infrastructure.stacks.governance.lake_formation_stack import LakeFormationStack
from infrastructure.stacks.networking.vpc_stack import VPCStack

# Load environment variables
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
AWS_ACCOUNT = os.environ.get('AWS_ACCOUNT_ID', '123456789012')
AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')

app = App()

# Define environment
env = Environment(account=AWS_ACCOUNT, region=AWS_REGION)

# Create VPC Stack (foundation for other resources)
vpc_stack = VPCStack(
    app,
    f"DataPlatform-{ENVIRONMENT}-VPC",
    env=env,
    environment=ENVIRONMENT
)

# Create Storage Layer
s3_stack = S3DataLakeStack(
    app,
    f"DataPlatform-{ENVIRONMENT}-S3",
    env=env,
    environment=ENVIRONMENT
)

dynamodb_stack = DynamoDBStack(
    app,
    f"DataPlatform-{ENVIRONMENT}-DynamoDB",
    env=env,
    environment=ENVIRONMENT
)

redshift_stack = RedshiftStack(
    app,
    f"DataPlatform-{ENVIRONMENT}-Redshift",
    env=env,
    vpc=vpc_stack.vpc,
    environment=ENVIRONMENT
)
redshift_stack.add_dependency(vpc_stack)
redshift_stack.add_dependency(s3_stack)

# Create Streaming Layer
kinesis_stack = KinesisStreamingStack(
    app,
    f"DataPlatform-{ENVIRONMENT}-Kinesis",
    env=env,
    environment=ENVIRONMENT
)

lambda_stack = LambdaProcessorStack(
    app,
    f"DataPlatform-{ENVIRONMENT}-Lambda",
    env=env,
    kinesis_streams=kinesis_stack.streams,
    dynamodb_tables=dynamodb_stack.tables,
    s3_buckets=s3_stack.buckets,
    environment=ENVIRONMENT
)
lambda_stack.add_dependency(kinesis_stack)
lambda_stack.add_dependency(dynamodb_stack)
lambda_stack.add_dependency(s3_stack)

# Create Batch Processing Layer
emr_stack = EMRStack(
    app,
    f"DataPlatform-{ENVIRONMENT}-EMR",
    env=env,
    vpc=vpc_stack.vpc,
    s3_buckets=s3_stack.buckets,
    environment=ENVIRONMENT
)
emr_stack.add_dependency(vpc_stack)
emr_stack.add_dependency(s3_stack)

glue_stack = GlueETLStack(
    app,
    f"DataPlatform-{ENVIRONMENT}-Glue",
    env=env,
    s3_buckets=s3_stack.buckets,
    redshift_cluster=redshift_stack.cluster,
    environment=ENVIRONMENT
)
glue_stack.add_dependency(s3_stack)
glue_stack.add_dependency(redshift_stack)

athena_stack = AthenaStack(
    app,
    f"DataPlatform-{ENVIRONMENT}-Athena",
    env=env,
    s3_buckets=s3_stack.buckets,
    glue_catalog=glue_stack.catalog,
    environment=ENVIRONMENT
)
athena_stack.add_dependency(s3_stack)
athena_stack.add_dependency(glue_stack)

# Create ML Platform Layer
sagemaker_stack = SageMakerStack(
    app,
    f"DataPlatform-{ENVIRONMENT}-SageMaker",
    env=env,
    vpc=vpc_stack.vpc,
    s3_buckets=s3_stack.buckets,
    environment=ENVIRONMENT
)
sagemaker_stack.add_dependency(vpc_stack)
sagemaker_stack.add_dependency(s3_stack)

feature_store_stack = FeatureStoreStack(
    app,
    f"DataPlatform-{ENVIRONMENT}-FeatureStore",
    env=env,
    s3_buckets=s3_stack.buckets,
    environment=ENVIRONMENT
)
feature_store_stack.add_dependency(s3_stack)

# Create Analytics Layer
quicksight_stack = QuickSightStack(
    app,
    f"DataPlatform-{ENVIRONMENT}-QuickSight",
    env=env,
    redshift_cluster=redshift_stack.cluster,
    s3_buckets=s3_stack.buckets,
    environment=ENVIRONMENT
)
quicksight_stack.add_dependency(redshift_stack)
quicksight_stack.add_dependency(s3_stack)

# Create Monitoring Layer
cloudwatch_stack = CloudWatchStack(
    app,
    f"DataPlatform-{ENVIRONMENT}-CloudWatch",
    env=env,
    environment=ENVIRONMENT,
    kinesis_streams=kinesis_stack.streams,
    lambda_functions=lambda_stack.functions,
    emr_cluster=emr_stack.cluster,
    glue_jobs=glue_stack.jobs
)
cloudwatch_stack.add_dependency(kinesis_stack)
cloudwatch_stack.add_dependency(lambda_stack)
cloudwatch_stack.add_dependency(emr_stack)
cloudwatch_stack.add_dependency(glue_stack)

# Create Governance Layer
lake_formation_stack = LakeFormationStack(
    app,
    f"DataPlatform-{ENVIRONMENT}-LakeFormation",
    env=env,
    s3_buckets=s3_stack.buckets,
    glue_catalog=glue_stack.catalog,
    environment=ENVIRONMENT
)
lake_formation_stack.add_dependency(s3_stack)
lake_formation_stack.add_dependency(glue_stack)

# Apply global tags
for stack in [vpc_stack, s3_stack, dynamodb_stack, redshift_stack, kinesis_stack,
              lambda_stack, emr_stack, glue_stack, athena_stack, sagemaker_stack,
              feature_store_stack, quicksight_stack, cloudwatch_stack, lake_formation_stack]:
    Tags.of(stack).add("Project", "DataPlatform")
    Tags.of(stack).add("Environment", ENVIRONMENT)
    Tags.of(stack).add("ManagedBy", "CDK")
    Tags.of(stack).add("Owner", "DataEngineering")

app.synth()