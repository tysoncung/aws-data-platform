# AWS Data Platform Template

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![AWS CDK](https://img.shields.io/badge/AWS%20CDK-2.100.0-orange)](https://aws.amazon.com/cdk/)
[![Python](https://img.shields.io/badge/Python-3.9%2B-blue)](https://www.python.org/)

A production-ready, enterprise-grade data platform template for AWS that integrates real-time streaming, batch processing, machine learning, and business intelligence capabilities. Built entirely with AWS CDK in Python, this template provides a complete foundation for data-driven organizations.

## 🚀 Features

### Real-Time Streaming Architecture
- **Amazon Kinesis Data Streams** for high-throughput data ingestion
- **AWS Lambda** for serverless stream processing
- **Amazon DynamoDB** for low-latency data storage
- **Kinesis Data Analytics** for real-time SQL analytics

### Batch Processing Infrastructure
- **Amazon EMR** for large-scale distributed processing
- **AWS Glue ETL** for serverless data transformation
- **Amazon Athena** for interactive SQL queries
- **Apache Spark** and **Apache Hive** support

### Data Lake & Warehousing
- **Amazon S3** multi-tier storage (raw, processed, curated)
- **AWS Glue Data Catalog** for metadata management
- **Amazon Redshift** for data warehousing
- **Amazon QuickSight** for business intelligence

### Machine Learning Platform
- **Amazon SageMaker** for model training and deployment
- **Feature Store** for ML feature management
- **MLflow** for experiment tracking
- **Real-time inference** endpoints

### Monitoring & Governance
- **Amazon CloudWatch** dashboards and alarms
- **AWS CloudTrail** for audit logging
- **AWS Lake Formation** for data governance
- **Cost optimization** with auto-scaling

## 📋 Prerequisites

- AWS Account with appropriate permissions
- AWS CLI configured (`aws configure`)
- Python 3.9+ installed
- Node.js 14+ (for CDK)
- Docker (for Lambda packaging)

## 🛠️ Installation

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/aws-data-platform.git
cd aws-data-platform
```

### 2. Set Up Python Environment

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### 3. Install AWS CDK

```bash
npm install -g aws-cdk
cdk --version
```

### 4. Configure Environment

```bash
# Copy environment template
cp .env.example .env

# Edit .env with your configuration
nano .env
```

Required environment variables:
```bash
AWS_ACCOUNT_ID=123456789012
AWS_REGION=us-east-1
ENVIRONMENT=dev
DATA_LAKE_BUCKET_PREFIX=my-company-data-lake
REDSHIFT_MASTER_USER=admin
NOTIFICATION_EMAIL=data-team@company.com
```

## 🏗️ Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Data Sources                            │
│  (Applications, IoT Devices, APIs, Databases, Files)            │
└─────────────┬───────────────────────┬───────────────────────────┘
              │                       │
              ▼                       ▼
┌──────────────────────┐  ┌────────────────────────┐
│   Real-Time Layer    │  │    Batch Layer         │
├──────────────────────┤  ├────────────────────────┤
│ • Kinesis Streams    │  │ • S3 Data Lake         │
│ • Lambda Functions   │  │ • Glue ETL Jobs        │
│ • DynamoDB           │  │ • EMR Clusters         │
│ • Kinesis Analytics  │  │ • Athena Queries       │
└──────────┬───────────┘  └───────────┬────────────┘
           │                          │
           ▼                          ▼
┌─────────────────────────────────────────────────┐
│              Processing & Analytics              │
├─────────────────────────────────────────────────┤
│ • Spark Streaming    • Batch ETL                │
│ • ML Feature Eng.   • Data Validation           │
│ • Aggregations      • Data Quality              │
└─────────────────────┬───────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────┐
│           Storage & Serving Layer               │
├─────────────────────────────────────────────────┤
│ • Redshift (DW)     • DynamoDB (NoSQL)          │
│ • S3 (Data Lake)    • ElasticSearch             │
│ • Feature Store     • Time Series DB            │
└─────────────────────┬───────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────┐
│            Consumption Layer                    │
├─────────────────────────────────────────────────┤
│ • QuickSight        • SageMaker                 │
│ • API Gateway       • Custom Apps               │
│ • Notebooks         • ML Inference              │
└─────────────────────────────────────────────────┘
```

## 🚀 Quick Start

### Deploy the Complete Platform

```bash
# Deploy all stacks
./scripts/deploy.sh --all --environment dev

# Or deploy individual components
./scripts/deploy.sh --stack streaming --environment dev
./scripts/deploy.sh --stack batch --environment dev
./scripts/deploy.sh --stack ml --environment dev
```

### Verify Deployment

```bash
# Check stack status
aws cloudformation describe-stacks --stack-name DataPlatform-Dev-*

# Run validation tests
pytest tests/integration/test_deployment.py
```

## 📦 Project Structure

```
aws-data-platform/
├── infrastructure/           # CDK infrastructure code
│   ├── stacks/              # CDK stack definitions
│   │   ├── streaming/       # Real-time streaming stack
│   │   ├── batch/          # Batch processing stack
│   │   ├── storage/        # Data lake & warehouse stack
│   │   ├── ml/            # Machine learning stack
│   │   └── monitoring/     # Monitoring stack
│   ├── constructs/         # Reusable CDK constructs
│   └── configs/           # Environment configurations
├── src/                   # Application source code
│   ├── ingestion/        # Data ingestion modules
│   ├── processing/       # Data processing logic
│   ├── ml/              # ML pipelines and models
│   └── orchestration/    # Workflow orchestration
├── tests/               # Test suites
├── scripts/            # Deployment and utility scripts
└── docs/              # Documentation
```

## 🔧 Customization Guide

### 1. Adding New Data Sources

Edit `infrastructure/stacks/streaming/kinesis_stack.py`:

```python
from aws_cdk import aws_kinesis as kinesis

class StreamingStack(Stack):
    def __init__(self, scope, id, **kwargs):
        super().__init__(scope, id, **kwargs)

        # Add your custom stream
        self.custom_stream = kinesis.Stream(
            self, "CustomDataStream",
            stream_name=f"custom-data-{self.environment}",
            shard_count=2,
            retention_period=Duration.days(7)
        )
```

### 2. Configuring Data Processing

Modify `src/processing/batch/spark_jobs.py`:

```python
from pyspark.sql import SparkSession
from pyspark.sql.functions import *

class DataProcessor:
    def __init__(self, app_name="DataProcessor"):
        self.spark = SparkSession.builder \
            .appName(app_name) \
            .config("spark.sql.adaptive.enabled", "true") \
            .getOrCreate()

    def process_sales_data(self, input_path, output_path):
        """
        Customize this method for your business logic
        """
        df = self.spark.read.parquet(input_path)

        # Add your transformations
        processed_df = df \
            .filter(col("amount") > 0) \
            .groupBy("product_id", "date") \
            .agg(
                sum("amount").alias("total_revenue"),
                count("transaction_id").alias("transaction_count")
            )

        processed_df.write \
            .mode("overwrite") \
            .partitionBy("date") \
            .parquet(output_path)
```

### 3. Setting Up ML Pipelines

Configure ML workflows in `src/ml/training/pipeline.py`:

```python
import sagemaker
from sagemaker.sklearn.processing import SKLearnProcessor
from sagemaker.workflow.pipeline import Pipeline

class MLPipeline:
    def __init__(self, role, bucket):
        self.role = role
        self.bucket = bucket
        self.session = sagemaker.Session()

    def create_training_pipeline(self, model_name):
        """
        Define your ML training pipeline
        """
        # Feature engineering step
        processor = SKLearnProcessor(
            framework_version="0.23-1",
            instance_type="ml.m5.xlarge",
            role=self.role
        )

        # Add your pipeline steps
        # ...

        return Pipeline(
            name=f"{model_name}-training",
            steps=[preprocessing_step, training_step, evaluation_step]
        )
```

### 4. Configuring Business Intelligence

Set up QuickSight dashboards in `infrastructure/stacks/analytics/quicksight.py`:

```python
from aws_cdk import aws_quicksight as qs

class QuickSightDashboard(Construct):
    def __init__(self, scope, id, data_source_arn):
        super().__init__(scope, id)

        # Create custom dashboard
        self.dashboard = qs.CfnDashboard(
            self, "BusinessDashboard",
            dashboard_id="business-metrics",
            name="Business Metrics Dashboard",
            source_entity=qs.CfnDashboard.DashboardSourceEntityProperty(
                source_template=qs.CfnDashboard.DashboardSourceTemplateProperty(
                    data_set_references=[
                        # Configure your datasets
                    ]
                )
            )
        )
```

## 🔐 Security Configuration

### IAM Roles and Policies

The platform implements least-privilege access:

```python
# infrastructure/constructs/security.py
from aws_cdk import aws_iam as iam

class DataPlatformSecurity:
    @staticmethod
    def create_glue_role(scope, id):
        """Create IAM role for Glue ETL jobs"""
        return iam.Role(
            scope, id,
            assumed_by=iam.ServicePrincipal("glue.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSGlueServiceRole"
                )
            ],
            inline_policies={
                "S3Access": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            actions=["s3:GetObject", "s3:PutObject"],
                            resources=[f"arn:aws:s3:::{bucket}/*"]
                        )
                    ]
                )
            }
        )
```

### Encryption

All data is encrypted at rest and in transit:

- S3: SSE-S3 or SSE-KMS
- Redshift: KMS encryption
- DynamoDB: Encryption at rest
- Kinesis: Server-side encryption

## 📊 Monitoring & Observability

### CloudWatch Dashboards

Pre-configured dashboards for:
- Stream processing metrics
- ETL job performance
- Data quality metrics
- ML model performance
- Cost tracking

### Alerts

Automated alerts for:
- Failed ETL jobs
- Stream processing errors
- Data quality violations
- Cost anomalies
- Security events

## 💰 Cost Optimization

### Auto-Scaling

```yaml
# infrastructure/configs/scaling.yaml
emr_cluster:
  min_instances: 2
  max_instances: 10
  target_utilization: 70
  scale_down_delay: 300

kinesis_streams:
  auto_scaling_enabled: true
  target_utilization: 70
  scale_in_cooldown: 60
  scale_out_cooldown: 60
```

### Resource Tagging

All resources are tagged for cost allocation:

```python
Tags.of(stack).add("Environment", environment)
Tags.of(stack).add("Project", "DataPlatform")
Tags.of(stack).add("CostCenter", "DataEngineering")
Tags.of(stack).add("Owner", "data-team@company.com")
```

## 🧪 Testing

### Unit Tests

```bash
# Run unit tests
pytest tests/unit/ -v

# With coverage
pytest tests/unit/ --cov=src --cov-report=html
```

### Integration Tests

```bash
# Test data pipeline
pytest tests/integration/test_pipeline.py

# Test ML workflows
pytest tests/integration/test_ml_pipeline.py
```

### Load Testing

```bash
# Generate test data
python scripts/generate_test_data.py --records 1000000

# Run load test
locust -f tests/load/test_streaming.py --host https://kinesis.us-east-1.amazonaws.com
```

## 📚 Use Cases

### 1. Real-Time Analytics Dashboard

Monitor business metrics in real-time:
- Sales transactions
- User activity
- System performance
- Fraud detection

### 2. Customer 360 View

Unified customer data platform:
- Profile aggregation
- Behavior tracking
- Segmentation
- Personalization

### 3. Predictive Maintenance

IoT data processing for:
- Anomaly detection
- Failure prediction
- Optimization recommendations

### 4. Financial Reporting

Automated financial analytics:
- Revenue forecasting
- Cost analysis
- Compliance reporting
- Risk assessment

## 🛠️ Troubleshooting

### Common Issues

1. **Stack deployment fails**
   ```bash
   # Check CloudFormation events
   aws cloudformation describe-stack-events --stack-name DataPlatform-Dev-Streaming
   ```

2. **Glue job failures**
   ```bash
   # Check Glue job logs
   aws glue get-job-runs --job-name my-etl-job
   ```

3. **Permission errors**
   ```bash
   # Verify IAM roles
   aws iam simulate-principal-policy --policy-source-arn arn:aws:iam::123456789012:role/GlueRole
   ```

## 🤝 Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## 📄 License

This project is licensed under the MIT License - see [LICENSE](LICENSE) file.

## 🆘 Support

- Documentation: [docs/](docs/)
- Issues: [GitHub Issues](https://github.com/yourusername/aws-data-platform/issues)
- Discussions: [GitHub Discussions](https://github.com/yourusername/aws-data-platform/discussions)

## 🙏 Acknowledgments

Built with AWS best practices and community contributions.

---
**Note**: This is a template repository. Customize it according to your organization's specific requirements.
