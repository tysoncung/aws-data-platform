# Quick Start Guide

Get your AWS Data Platform up and running in 15 minutes!

## Prerequisites

Before you begin, ensure you have:

- ✅ AWS Account with appropriate permissions
- ✅ AWS CLI installed and configured
- ✅ Python 3.9+ installed
- ✅ Node.js 14+ installed (for CDK)
- ✅ Git installed

## Step 1: Clone the Repository

```bash
git clone https://github.com/tysoncung/aws-data-platform.git
cd aws-data-platform
```

## Step 2: Install Dependencies

### Create Python Virtual Environment
```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### Install Python Packages
```bash
pip install -r requirements.txt
```

### Install AWS CDK
```bash
npm install -g aws-cdk
cdk --version
```

## Step 3: Configure Environment

### Copy Environment Template
```bash
cp .env.example .env.dev
```

### Edit Configuration
Open `.env.dev` and update with your values:

```bash
AWS_ACCOUNT_ID=YOUR_ACCOUNT_ID
AWS_REGION=us-east-1
ENVIRONMENT=dev
NOTIFICATION_EMAIL=your-email@company.com
```

### Set AWS Credentials
```bash
aws configure
# Enter your AWS Access Key ID
# Enter your AWS Secret Access Key
# Enter default region (us-east-1)
# Enter default output format (json)
```

## Step 4: Deploy the Platform

### Deploy All Stacks
```bash
./scripts/deploy.sh --all --environment dev
```

### Or Deploy Individual Components
```bash
# Deploy streaming infrastructure
./scripts/deploy.sh --stack streaming --environment dev

# Deploy batch processing
./scripts/deploy.sh --stack batch --environment dev

# Deploy machine learning
./scripts/deploy.sh --stack ml --environment dev
```

## Step 5: Verify Deployment

### Check CloudFormation Stacks
```bash
aws cloudformation list-stacks --query "StackSummaries[?starts_with(StackName, 'DataPlatform-dev')].StackName"
```

### Access Services

1. **EMR Cluster**:
   ```
   https://console.aws.amazon.com/emr
   ```

2. **Kinesis Streams**:
   ```
   https://console.aws.amazon.com/kinesis
   ```

3. **Redshift Console**:
   ```
   https://console.aws.amazon.com/redshiftv2
   ```

4. **CloudWatch Dashboards**:
   ```
   https://console.aws.amazon.com/cloudwatch
   ```

## Step 6: Test the Platform

### Send Test Data to Kinesis
```python
import boto3
import json
import datetime

kinesis = boto3.client('kinesis', region_name='us-east-1')

# Send test record
response = kinesis.put_record(
    StreamName='maindatastream-dev',
    Data=json.dumps({
        'timestamp': datetime.datetime.now().isoformat(),
        'event_type': 'test',
        'data': {'message': 'Hello Data Platform!'}
    }),
    PartitionKey='test-partition'
)

print(f"Record sent: {response['ShardId']}")
```

### Query Data with Athena
```sql
-- Run in Athena console
SELECT *
FROM data_platform_dev.raw_data
WHERE date = CURRENT_DATE
LIMIT 10;
```

### Submit Spark Job to EMR
```bash
aws emr add-steps --cluster-id YOUR_CLUSTER_ID \
  --steps Type=Spark,Name="Test Spark Job",\
  Args=[--class,org.apache.spark.examples.SparkPi,\
  /usr/lib/spark/examples/jars/spark-examples.jar,100]
```

## Step 7: Monitor the Platform

### View CloudWatch Metrics
```bash
# View Kinesis metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/Kinesis \
  --metric-name IncomingRecords \
  --dimensions Name=StreamName,Value=maindatastream-dev \
  --start-time 2024-01-01T00:00:00Z \
  --end-time 2024-01-01T23:59:59Z \
  --period 3600 \
  --statistics Sum
```

### Check Lambda Logs
```bash
# View Lambda function logs
aws logs tail /aws/lambda/mainstreampprocessor-dev --follow
```

## Common Operations

### Scale Kinesis Shards
```python
import boto3

kinesis = boto3.client('kinesis')

# Update shard count
kinesis.update_shard_count(
    StreamName='maindatastream-dev',
    TargetShardCount=4
)
```

### Resize EMR Cluster
```bash
# Add more worker nodes
aws emr modify-instance-groups \
  --cluster-id YOUR_CLUSTER_ID \
  --instance-groups InstanceGroupId=YOUR_INSTANCE_GROUP_ID,InstanceCount=5
```

### Create Redshift Snapshot
```bash
aws redshift create-cluster-snapshot \
  --cluster-identifier data-platform-cluster-dev \
  --snapshot-identifier manual-snapshot-$(date +%Y%m%d)
```

## Troubleshooting

### Issue: CDK Bootstrap Fails
**Solution:**
```bash
# Manually bootstrap with admin permissions
cdk bootstrap aws://ACCOUNT_ID/REGION --cloudformation-execution-policies arn:aws:iam::aws:policy/AdministratorAccess
```

### Issue: Lambda Function Errors
**Solution:**
```bash
# Check function logs
aws logs get-log-events \
  --log-group-name /aws/lambda/YOUR_FUNCTION_NAME \
  --log-stream-name 'LATEST'
```

### Issue: EMR Cluster Won't Start
**Solution:**
```bash
# Check cluster status
aws emr describe-cluster --cluster-id YOUR_CLUSTER_ID

# View step failures
aws emr list-steps --cluster-id YOUR_CLUSTER_ID --step-states FAILED
```

### Issue: Insufficient Permissions
**Solution:**
Ensure your IAM user has these policies:
- `AWSCloudFormationFullAccess`
- `IAMFullAccess`
- `AmazonS3FullAccess`
- `AmazonKinesisFullAccess`
- `AmazonEMRFullAccessPolicy_v2`
- `AmazonRedshiftFullAccess`

## Next Steps

1. **Customize Processing Logic**
   - Modify Lambda functions in `infrastructure/stacks/streaming/`
   - Add Spark jobs in `src/processing/batch/`

2. **Set Up Data Sources**
   - Configure Kinesis producers
   - Set up S3 data uploads
   - Connect databases

3. **Create Dashboards**
   - Design QuickSight visualizations
   - Build CloudWatch dashboards
   - Set up alerts

4. **Implement ML Models**
   - Create SageMaker notebooks
   - Train models
   - Deploy endpoints

## Clean Up

To avoid charges, destroy resources when not needed:

```bash
# Destroy all stacks
./scripts/deploy.sh --all --environment dev --destroy

# Or destroy specific stack
./scripts/deploy.sh --stack streaming --environment dev --destroy
```

## Getting Help

- 📖 [Full Documentation](../README.md)
- 🐛 [Report Issues](https://github.com/tysoncung/aws-data-platform/issues)
- 💬 [Discussions](https://github.com/tysoncung/aws-data-platform/discussions)

## Summary

You've successfully deployed the AWS Data Platform! The platform is now ready to:
- ✅ Ingest streaming data via Kinesis
- ✅ Process data with Lambda and EMR
- ✅ Store data in S3, DynamoDB, and Redshift
- ✅ Analyze data with Athena and QuickSight
- ✅ Train ML models with SageMaker

For production deployment, see the [Production Deployment Guide](production-deployment.md).