# Streaming Pipeline Guide

## Overview

The streaming pipeline provides real-time data ingestion and processing capabilities using Amazon Kinesis, AWS Lambda, and DynamoDB. This guide covers configuration, optimization, and best practices for streaming workloads.

## Architecture

```
Data Producers → Kinesis Data Streams → Lambda Functions → DynamoDB/S3
                           ↓
                   Kinesis Analytics → Real-time Insights
                           ↓
                   Kinesis Firehose → S3 Data Lake
```

## Components

### Kinesis Data Streams

The platform includes four pre-configured streams:

1. **Main Data Stream** (`maindatastream-{env}`)
   - General purpose data ingestion
   - Configurable shard count
   - 7-day retention

2. **Clickstream** (`clickstreamdatastream-{env}`)
   - Web analytics and user behavior
   - 2 shards by default
   - 3-day retention

3. **IoT Stream** (`iotdatastream-{env}`)
   - Device telemetry and sensor data
   - 4 shards for high throughput
   - 1-day retention

4. **Transaction Stream** (`transactiondatastream-{env}`)
   - Financial transactions
   - Encryption enabled
   - 30-day retention for compliance

### Lambda Processors

Each stream has a dedicated Lambda processor:

- **MainStreamProcessor**: General data processing
- **ClickstreamProcessor**: Session tracking and metrics
- **IoTProcessor**: Telemetry analysis and alerting
- **TransactionProcessor**: Fraud detection

## Producer Implementation

### Python SDK Producer

```python
import boto3
import json
import uuid
from datetime import datetime
from typing import Dict, Any

class KinesisProducer:
    def __init__(self, stream_name: str, region: str = 'us-east-1'):
        self.stream_name = stream_name
        self.kinesis = boto3.client('kinesis', region_name=region)

    def send_record(self, data: Dict[str, Any], partition_key: str = None) -> Dict:
        """Send single record to Kinesis stream"""
        if partition_key is None:
            partition_key = str(uuid.uuid4())

        # Add metadata
        data['timestamp'] = datetime.utcnow().isoformat()
        data['version'] = '1.0'

        response = self.kinesis.put_record(
            StreamName=self.stream_name,
            Data=json.dumps(data),
            PartitionKey=partition_key
        )

        return response

    def send_batch(self, records: list) -> Dict:
        """Send batch of records to Kinesis"""
        kinesis_records = []

        for record in records:
            kinesis_records.append({
                'Data': json.dumps(record),
                'PartitionKey': record.get('id', str(uuid.uuid4()))
            })

        response = self.kinesis.put_records(
            Records=kinesis_records,
            StreamName=self.stream_name
        )

        # Handle failed records
        if response['FailedRecordCount'] > 0:
            failed_records = []
            for i, result in enumerate(response['Records']):
                if 'ErrorCode' in result:
                    failed_records.append(records[i])

            # Retry failed records
            if failed_records:
                return self.send_batch(failed_records)

        return response

# Usage
producer = KinesisProducer('maindatastream-dev')

# Send single record
producer.send_record({
    'event_type': 'user_action',
    'user_id': 'user123',
    'action': 'click',
    'page': '/products'
})

# Send batch
records = [
    {'event_type': 'page_view', 'page': '/home'},
    {'event_type': 'page_view', 'page': '/products'},
    {'event_type': 'purchase', 'amount': 99.99}
]
producer.send_batch(records)
```

### Kinesis Agent Configuration

For file-based ingestion, use Kinesis Agent:

```json
{
  "cloudwatch.emitMetrics": true,
  "kinesis.endpoint": "https://kinesis.us-east-1.amazonaws.com",
  "firehose.endpoint": "https://firehose.us-east-1.amazonaws.com",

  "flows": [
    {
      "filePattern": "/var/log/app/*.log",
      "kinesisStream": "maindatastream-dev",
      "partitionKeyOption": "RANDOM",
      "dataProcessingOptions": [
        {
          "processingPattern": "^([^ ]+) ([^ ]+) ([^ ]+) \\[([^\\]]+)\\].*",
          "processedRecordFormat": "{\"timestamp\": \"$4\", \"ip\": \"$1\", \"user\": \"$3\"}"
        }
      ]
    }
  ]
}
```

## Lambda Processor Development

### Custom Processor Template

```python
import json
import base64
import boto3
import os
from datetime import datetime
from typing import List, Dict, Any

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
s3 = boto3.client('s3')
cloudwatch = boto3.client('cloudwatch')

# Environment variables
TABLE_NAME = os.environ['DYNAMODB_TABLE']
BUCKET_NAME = os.environ['S3_BUCKET']
ENVIRONMENT = os.environ['ENVIRONMENT']

def handler(event: Dict, context: Any) -> Dict:
    """Process Kinesis stream records"""

    processed_count = 0
    error_count = 0

    for record in event['Records']:
        try:
            # Decode Kinesis data
            payload = base64.b64decode(record['kinesis']['data']).decode('utf-8')
            data = json.loads(payload)

            # Process record
            processed_data = process_record(data)

            # Store in DynamoDB
            store_in_dynamodb(processed_data)

            # Archive to S3
            archive_to_s3(processed_data)

            # Emit metrics
            emit_metrics(processed_data)

            processed_count += 1

        except Exception as e:
            print(f"Error processing record: {e}")
            error_count += 1
            handle_error(record, e)

    return {
        'statusCode': 200,
        'batchItemFailures': [],
        'processed': processed_count,
        'errors': error_count
    }

def process_record(data: Dict) -> Dict:
    """Apply business logic to record"""

    # Data validation
    validate_schema(data)

    # Enrichment
    data['processed_timestamp'] = datetime.utcnow().isoformat()
    data['environment'] = ENVIRONMENT

    # Transform
    if 'amount' in data:
        data['amount_cents'] = int(data['amount'] * 100)

    # Data quality checks
    data['quality_score'] = calculate_quality_score(data)

    return data

def validate_schema(data: Dict):
    """Validate record schema"""
    required_fields = ['event_type', 'timestamp']
    for field in required_fields:
        if field not in data:
            raise ValueError(f"Missing required field: {field}")

def calculate_quality_score(data: Dict) -> float:
    """Calculate data quality score"""
    score = 1.0

    # Penalize missing optional fields
    optional_fields = ['user_id', 'session_id', 'metadata']
    for field in optional_fields:
        if field not in data:
            score -= 0.1

    # Check data freshness
    if 'timestamp' in data:
        record_time = datetime.fromisoformat(data['timestamp'])
        age_seconds = (datetime.utcnow() - record_time).total_seconds()
        if age_seconds > 3600:  # Older than 1 hour
            score -= 0.2

    return max(0, score)

def store_in_dynamodb(data: Dict):
    """Store processed record in DynamoDB"""
    table = dynamodb.Table(TABLE_NAME)

    # Add DynamoDB-specific attributes
    item = {
        'pk': f"{data['event_type']}#{data.get('user_id', 'anonymous')}",
        'sk': data['timestamp'],
        'ttl': int(datetime.utcnow().timestamp()) + 86400 * 30,  # 30 days
        **data
    }

    table.put_item(Item=item)

def archive_to_s3(data: Dict):
    """Archive record to S3"""
    key = f"processed/{datetime.utcnow().strftime('%Y/%m/%d/%H')}/{data['event_type']}/{data.get('id', 'unknown')}.json"

    s3.put_object(
        Bucket=BUCKET_NAME,
        Key=key,
        Body=json.dumps(data),
        ContentType='application/json',
        Metadata={
            'event_type': data['event_type'],
            'processed_by': 'lambda'
        }
    )

def emit_metrics(data: Dict):
    """Send custom metrics to CloudWatch"""
    cloudwatch.put_metric_data(
        Namespace='DataPlatform/Streaming',
        MetricData=[
            {
                'MetricName': 'RecordsProcessed',
                'Value': 1,
                'Unit': 'Count',
                'Dimensions': [
                    {'Name': 'Environment', 'Value': ENVIRONMENT},
                    {'Name': 'EventType', 'Value': data['event_type']}
                ]
            },
            {
                'MetricName': 'DataQualityScore',
                'Value': data.get('quality_score', 0),
                'Unit': 'None',
                'Dimensions': [
                    {'Name': 'Environment', 'Value': ENVIRONMENT}
                ]
            }
        ]
    )

def handle_error(record: Dict, error: Exception):
    """Handle processing errors"""
    # Log error
    print(f"Failed to process record: {record}")
    print(f"Error: {error}")

    # Send to DLQ
    # Emit error metric
    cloudwatch.put_metric_data(
        Namespace='DataPlatform/Streaming',
        MetricData=[{
            'MetricName': 'ProcessingErrors',
            'Value': 1,
            'Unit': 'Count',
            'Dimensions': [{'Name': 'Environment', 'Value': ENVIRONMENT}]
        }]
    )
```

## Kinesis Analytics SQL

### Real-time Aggregations

```sql
-- Create output stream
CREATE OR REPLACE STREAM "AGGREGATED_STREAM" (
    event_time TIMESTAMP,
    event_type VARCHAR(64),
    event_count INTEGER,
    unique_users INTEGER,
    avg_amount DOUBLE
);

-- Aggregate events by type
CREATE OR REPLACE PUMP "AGGREGATION_PUMP" AS
INSERT INTO "AGGREGATED_STREAM"
SELECT STREAM
    ROWTIME as event_time,
    event_type,
    COUNT(*) as event_count,
    COUNT(DISTINCT user_id) as unique_users,
    AVG(amount) as avg_amount
FROM SOURCE_SQL_STREAM_001
GROUP BY
    event_type,
    ROWTIME RANGE INTERVAL '1' MINUTE;

-- Detect anomalies
CREATE OR REPLACE STREAM "ANOMALY_STREAM" (
    event_time TIMESTAMP,
    anomaly_score DOUBLE,
    event_type VARCHAR(64)
);

CREATE OR REPLACE PUMP "ANOMALY_PUMP" AS
INSERT INTO "ANOMALY_STREAM"
SELECT STREAM
    event_time,
    anomaly_score,
    event_type
FROM TABLE(RANDOM_CUT_FOREST(
    CURSOR(SELECT STREAM * FROM SOURCE_SQL_STREAM_001),
    100,  -- Number of trees
    256,  -- Sample size
    100000,  -- Time decay
    1     -- Shingle size
));
```

## Monitoring and Operations

### CloudWatch Dashboards

Key metrics to monitor:

1. **Stream Metrics**
   - IncomingRecords
   - IncomingBytes
   - GetRecords.IteratorAge
   - PutRecords.Success
   - PutRecords.Throttled

2. **Lambda Metrics**
   - Invocations
   - Errors
   - Duration
   - Throttles
   - IteratorAge

3. **DynamoDB Metrics**
   - ConsumedReadCapacityUnits
   - ConsumedWriteCapacityUnits
   - Throttled requests

### Alarms Configuration

```python
import boto3

cloudwatch = boto3.client('cloudwatch')

# High iterator age alarm
cloudwatch.put_metric_alarm(
    AlarmName='HighIteratorAge',
    ComparisonOperator='GreaterThanThreshold',
    EvaluationPeriods=2,
    MetricName='GetRecords.IteratorAge',
    Namespace='AWS/Kinesis',
    Period=60,
    Statistic='Maximum',
    Threshold=60000.0,
    ActionsEnabled=True,
    AlarmActions=['arn:aws:sns:region:account:topic'],
    AlarmDescription='Alarm when iterator age is too high',
    Dimensions=[
        {
            'Name': 'StreamName',
            'Value': 'maindatastream-prod'
        }
    ]
)
```

## Performance Optimization

### Shard Management

```python
def calculate_shard_count(records_per_second: int,
                         avg_record_size_kb: float) -> int:
    """Calculate required number of shards"""

    # Kinesis limits per shard
    MAX_RECORDS_PER_SECOND = 1000
    MAX_BYTES_PER_SECOND = 1024  # KB

    # Calculate based on record count
    shards_by_count = math.ceil(records_per_second / MAX_RECORDS_PER_SECOND)

    # Calculate based on data volume
    data_rate_kb = records_per_second * avg_record_size_kb
    shards_by_volume = math.ceil(data_rate_kb / MAX_BYTES_PER_SECOND)

    # Return maximum required
    return max(shards_by_count, shards_by_volume)

# Auto-scaling based on metrics
def auto_scale_shards(stream_name: str):
    kinesis = boto3.client('kinesis')
    cloudwatch = boto3.client('cloudwatch')

    # Get current metrics
    response = cloudwatch.get_metric_statistics(
        Namespace='AWS/Kinesis',
        MetricName='IncomingRecords',
        Dimensions=[{'Name': 'StreamName', 'Value': stream_name}],
        StartTime=datetime.utcnow() - timedelta(minutes=5),
        EndTime=datetime.utcnow(),
        Period=300,
        Statistics=['Average']
    )

    if response['Datapoints']:
        avg_records = response['Datapoints'][0]['Average']
        required_shards = calculate_shard_count(avg_records, 1.0)

        # Update shard count if needed
        stream_info = kinesis.describe_stream_summary(StreamName=stream_name)
        current_shards = stream_info['StreamDescriptionSummary']['OpenShardCount']

        if required_shards > current_shards:
            kinesis.update_shard_count(
                StreamName=stream_name,
                TargetShardCount=required_shards
            )
```

### Lambda Optimization

1. **Memory Configuration**
   - Start with 512 MB
   - Use AWS Lambda Power Tuning
   - Monitor duration and adjust

2. **Batch Size**
   - Default: 100 records
   - Increase for higher throughput
   - Decrease for lower latency

3. **Parallelization**
   - Default: 1 concurrent batch per shard
   - Increase ParallelizationFactor for more concurrency

4. **Error Handling**
   - Implement partial batch failure reporting
   - Use DLQ for failed records
   - Implement exponential backoff

## Troubleshooting

### Common Issues

1. **High Iterator Age**
   - Cause: Lambda can't keep up with stream
   - Solution: Increase Lambda concurrency or add shards

2. **Throttling**
   - Cause: Exceeding shard limits
   - Solution: Add more shards or implement backpressure

3. **Data Loss**
   - Cause: Records expiring before processing
   - Solution: Increase retention period or fix processing bottleneck

4. **Duplicate Records**
   - Cause: Lambda retries
   - Solution: Implement idempotent processing

### Debug Commands

```bash
# Check stream status
aws kinesis describe-stream --stream-name maindatastream-dev

# List shards
aws kinesis list-shards --stream-name maindatastream-dev

# Get shard iterator
aws kinesis get-shard-iterator \
  --stream-name maindatastream-dev \
  --shard-id shardId-000000000000 \
  --shard-iterator-type LATEST

# Read records
aws kinesis get-records --shard-iterator YOUR_ITERATOR

# Check Lambda errors
aws logs tail /aws/lambda/mainstreampprocessor-dev --follow
```

## Best Practices

1. **Partition Key Strategy**
   - Use high cardinality keys for even distribution
   - Avoid hot partitions
   - Consider composite keys for complex scenarios

2. **Error Handling**
   - Implement circuit breakers
   - Use dead letter queues
   - Log all errors with context

3. **Security**
   - Encrypt sensitive data at rest
   - Use VPC endpoints for private communication
   - Implement least privilege IAM policies

4. **Cost Optimization**
   - Use on-demand pricing for variable workloads
   - Archive old data to S3
   - Right-size Lambda memory allocation

5. **Testing**
   - Use Kinesis Data Generator for load testing
   - Implement integration tests
   - Test failure scenarios