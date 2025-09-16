"""
Lambda Processor Stack
Serverless stream processing using AWS Lambda functions
"""

from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    CfnOutput,
    aws_lambda as lambda_,
    aws_lambda_event_sources as lambda_events,
    aws_iam as iam,
    aws_logs as logs,
    aws_dynamodb as dynamodb,
    aws_s3 as s3
)
from constructs import Construct
from typing import Dict, List


class LambdaProcessorStack(Stack):
    """
    Creates Lambda functions for processing streaming data
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        kinesis_streams: Dict,
        dynamodb_tables: Dict,
        s3_buckets: Dict,
        environment: str,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.environment = environment
        self.kinesis_streams = kinesis_streams
        self.dynamodb_tables = dynamodb_tables
        self.s3_buckets = s3_buckets
        self.functions = {}

        # Create Lambda execution role
        self.lambda_role = self._create_lambda_role()

        # Create Lambda functions for different processing tasks
        self.functions['main_processor'] = self._create_stream_processor(
            "MainStreamProcessor",
            self.kinesis_streams['main'],
            handler_code=self._get_main_processor_code()
        )

        self.functions['clickstream_processor'] = self._create_stream_processor(
            "ClickstreamProcessor",
            self.kinesis_streams['clickstream'],
            handler_code=self._get_clickstream_processor_code()
        )

        self.functions['iot_processor'] = self._create_stream_processor(
            "IoTProcessor",
            self.kinesis_streams['iot'],
            handler_code=self._get_iot_processor_code()
        )

        self.functions['transaction_processor'] = self._create_stream_processor(
            "TransactionProcessor",
            self.kinesis_streams['transactions'],
            handler_code=self._get_transaction_processor_code(),
            memory_size=1024,
            timeout=Duration.minutes(5)
        )

        # Create data quality validation function
        self.functions['data_validator'] = self._create_data_validator()

        # Create enrichment function
        self.functions['data_enricher'] = self._create_data_enricher()

        # Output Lambda function ARNs
        for func_name, func in self.functions.items():
            CfnOutput(
                self, f"{func_name}Arn",
                value=func.function_arn,
                export_name=f"{self.stack_name}-{func_name}-arn"
            )

    def _create_lambda_role(self) -> iam.Role:
        """Create IAM role for Lambda functions"""

        role = iam.Role(
            self, "LambdaProcessorRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaKinesisExecutionRole"),
                iam.ManagedPolicy.from_aws_managed_policy_name("CloudWatchLambdaInsightsExecutionRolePolicy")
            ]
        )

        # Add permissions for DynamoDB
        role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "dynamodb:GetItem",
                    "dynamodb:PutItem",
                    "dynamodb:UpdateItem",
                    "dynamodb:Query",
                    "dynamodb:BatchWriteItem"
                ],
                resources=["arn:aws:dynamodb:*:*:table/data-platform-*"]
            )
        )

        # Add permissions for S3
        role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "s3:GetObject",
                    "s3:PutObject"
                ],
                resources=["arn:aws:s3:::data-platform-*/*"]
            )
        )

        # Add permissions for X-Ray tracing
        role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "xray:PutTraceSegments",
                    "xray:PutTelemetryRecords"
                ],
                resources=["*"]
            )
        )

        return role

    def _create_stream_processor(
        self,
        function_name: str,
        stream,
        handler_code: str,
        memory_size: int = 512,
        timeout: Duration = Duration.minutes(1)
    ) -> lambda_.Function:
        """Create a Lambda function for stream processing"""

        # Create Lambda function
        function = lambda_.Function(
            self, function_name,
            function_name=f"{function_name.lower()}-{self.environment}",
            runtime=lambda_.Runtime.PYTHON_3_9,
            handler="index.handler",
            code=lambda_.Code.from_inline(handler_code),
            memory_size=memory_size,
            timeout=timeout,
            role=self.lambda_role,
            environment={
                "ENVIRONMENT": self.environment,
                "DYNAMODB_TABLE": f"data-platform-events-{self.environment}",
                "S3_BUCKET": f"data-platform-processed-{self.environment}",
                "ENABLE_XRAY": "true"
            },
            tracing=lambda_.Tracing.ACTIVE,
            reserved_concurrent_executions=10 if self.environment == 'dev' else 100,
            retry_attempts=2,
            dead_letter_queue_enabled=True,
            insights_version=lambda_.LambdaInsightsVersion.VERSION_1_0_119_0
        )

        # Add Kinesis event source
        function.add_event_source(
            lambda_events.KinesisEventSource(
                stream,
                starting_position=lambda_.StartingPosition.LATEST,
                batch_size=100,
                max_batching_window_time=Duration.seconds(5),
                parallelization_factor=10,
                retry_attempts=3,
                on_failure=lambda_events.SqsDlq(
                    queue=None  # Will create default DLQ
                )
            )
        )

        # Add CloudWatch alarms
        function.metric_errors().create_alarm(
            self, f"{function_name}Errors",
            threshold=10,
            evaluation_periods=1,
            alarm_description=f"High error rate for {function_name}"
        )

        function.metric_throttles().create_alarm(
            self, f"{function_name}Throttles",
            threshold=5,
            evaluation_periods=1,
            alarm_description=f"Function {function_name} is being throttled"
        )

        return function

    def _create_data_validator(self) -> lambda_.Function:
        """Create Lambda function for data quality validation"""

        validation_code = '''
import json
import boto3
import os
from datetime import datetime
from decimal import Decimal

dynamodb = boto3.resource('dynamodb')
cloudwatch = boto3.client('cloudwatch')

def handler(event, context):
    """Validate data quality and emit metrics"""

    table = dynamodb.Table(os.environ['DYNAMODB_TABLE'])
    environment = os.environ['ENVIRONMENT']

    validation_results = []

    for record in event['Records']:
        payload = json.loads(record['body'])

        # Perform validation checks
        validation = {
            'record_id': payload.get('id'),
            'timestamp': datetime.now().isoformat(),
            'validations': {}
        }

        # Check for required fields
        required_fields = ['id', 'timestamp', 'event_type', 'data']
        for field in required_fields:
            validation['validations'][f'has_{field}'] = field in payload

        # Check data types
        if 'timestamp' in payload:
            try:
                datetime.fromisoformat(payload['timestamp'])
                validation['validations']['valid_timestamp'] = True
            except:
                validation['validations']['valid_timestamp'] = False

        # Check data ranges
        if 'amount' in payload.get('data', {}):
            amount = payload['data']['amount']
            validation['validations']['amount_positive'] = amount > 0
            validation['validations']['amount_reasonable'] = amount < 1000000

        # Calculate validation score
        passed = sum(1 for v in validation['validations'].values() if v)
        total = len(validation['validations'])
        validation['score'] = passed / total if total > 0 else 0

        # Store validation results
        table.put_item(Item=validation)

        # Emit CloudWatch metrics
        cloudwatch.put_metric_data(
            Namespace='DataPlatform/DataQuality',
            MetricData=[
                {
                    'MetricName': 'ValidationScore',
                    'Value': validation['score'],
                    'Unit': 'None',
                    'Dimensions': [
                        {'Name': 'Environment', 'Value': environment},
                        {'Name': 'EventType', 'Value': payload.get('event_type', 'unknown')}
                    ]
                }
            ]
        )

        validation_results.append(validation)

    return {
        'statusCode': 200,
        'body': json.dumps({
            'processed': len(validation_results),
            'average_score': sum(v['score'] for v in validation_results) / len(validation_results)
        })
    }
'''

        return lambda_.Function(
            self, "DataValidator",
            function_name=f"data-validator-{self.environment}",
            runtime=lambda_.Runtime.PYTHON_3_9,
            handler="index.handler",
            code=lambda_.Code.from_inline(validation_code),
            memory_size=512,
            timeout=Duration.minutes(2),
            role=self.lambda_role,
            environment={
                "ENVIRONMENT": self.environment,
                "DYNAMODB_TABLE": f"data-platform-validation-{self.environment}"
            },
            tracing=lambda_.Tracing.ACTIVE
        )

    def _create_data_enricher(self) -> lambda_.Function:
        """Create Lambda function for data enrichment"""

        enrichment_code = '''
import json
import boto3
import os
from datetime import datetime

s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

def handler(event, context):
    """Enrich streaming data with additional context"""

    enrichment_table = dynamodb.Table(os.environ['ENRICHMENT_TABLE'])

    enriched_records = []

    for record in event['Records']:
        payload = json.loads(record['body'])

        # Lookup enrichment data
        if 'user_id' in payload:
            try:
                response = enrichment_table.get_item(
                    Key={'user_id': payload['user_id']}
                )
                if 'Item' in response:
                    # Add user profile data
                    payload['user_profile'] = response['Item']
            except Exception as e:
                print(f"Failed to enrich user data: {e}")

        # Add processing metadata
        payload['enrichment'] = {
            'timestamp': datetime.now().isoformat(),
            'version': '1.0',
            'processor': context.function_name
        }

        # Geographic enrichment for IP addresses
        if 'ip_address' in payload:
            payload['geo_location'] = lookup_geo_location(payload['ip_address'])

        enriched_records.append(payload)

    # Write enriched data to S3
    s3.put_object(
        Bucket=os.environ['S3_BUCKET'],
        Key=f"enriched/{datetime.now().strftime('%Y/%m/%d/%H')}/{context.request_id}.json",
        Body=json.dumps(enriched_records),
        ContentType='application/json'
    )

    return {
        'statusCode': 200,
        'body': json.dumps({'enriched': len(enriched_records)})
    }

def lookup_geo_location(ip_address):
    """Mock geo-location lookup"""
    # In production, integrate with real geo-IP service
    return {
        'country': 'US',
        'city': 'Seattle',
        'latitude': 47.6062,
        'longitude': -122.3321
    }
'''

        return lambda_.Function(
            self, "DataEnricher",
            function_name=f"data-enricher-{self.environment}",
            runtime=lambda_.Runtime.PYTHON_3_9,
            handler="index.handler",
            code=lambda_.Code.from_inline(enrichment_code),
            memory_size=512,
            timeout=Duration.minutes(2),
            role=self.lambda_role,
            environment={
                "ENVIRONMENT": self.environment,
                "ENRICHMENT_TABLE": f"data-platform-enrichment-{self.environment}",
                "S3_BUCKET": f"data-platform-enriched-{self.environment}"
            },
            tracing=lambda_.Tracing.ACTIVE
        )

    def _get_main_processor_code(self) -> str:
        """Get code for main stream processor"""
        return '''
import json
import base64
import boto3
import os
from datetime import datetime

dynamodb = boto3.resource('dynamodb')
s3 = boto3.client('s3')

def handler(event, context):
    """Process records from Kinesis stream"""

    table = dynamodb.Table(os.environ['DYNAMODB_TABLE'])
    processed_records = []

    for record in event['Records']:
        # Decode Kinesis record
        payload = base64.b64decode(record['kinesis']['data']).decode('utf-8')
        data = json.loads(payload)

        # Add processing metadata
        data['processed_at'] = datetime.now().isoformat()
        data['processor_version'] = '1.0'

        # Store in DynamoDB
        table.put_item(Item=data)

        processed_records.append(data)

    # Batch write to S3
    if processed_records:
        s3.put_object(
            Bucket=os.environ['S3_BUCKET'],
            Key=f"processed/{datetime.now().strftime('%Y/%m/%d/%H')}/{context.request_id}.json",
            Body=json.dumps(processed_records)
        )

    return {'statusCode': 200, 'processed': len(processed_records)}
'''

    def _get_clickstream_processor_code(self) -> str:
        """Get code for clickstream processor"""
        return '''
import json
import base64
import boto3
import os
from datetime import datetime
from urllib.parse import urlparse

dynamodb = boto3.resource('dynamodb')

def handler(event, context):
    """Process clickstream events"""

    session_table = dynamodb.Table(f"data-platform-sessions-{os.environ['ENVIRONMENT']}")
    metrics_table = dynamodb.Table(f"data-platform-metrics-{os.environ['ENVIRONMENT']}")

    for record in event['Records']:
        payload = base64.b64decode(record['kinesis']['data']).decode('utf-8')
        click_event = json.loads(payload)

        # Parse URL
        parsed_url = urlparse(click_event.get('url', ''))

        # Update session data
        session_table.update_item(
            Key={'session_id': click_event['session_id']},
            UpdateExpression='SET last_activity = :time, page_views = page_views + :inc',
            ExpressionAttributeValues={
                ':time': datetime.now().isoformat(),
                ':inc': 1
            }
        )

        # Update metrics
        metrics_table.update_item(
            Key={
                'metric_type': 'page_view',
                'timestamp': datetime.now().strftime('%Y-%m-%d-%H')
            },
            UpdateExpression='SET #count = #count + :inc',
            ExpressionAttributeNames={'#count': 'count'},
            ExpressionAttributeValues={':inc': 1}
        )

    return {'statusCode': 200}
'''

    def _get_iot_processor_code(self) -> str:
        """Get code for IoT data processor"""
        return '''
import json
import base64
import boto3
import os
from datetime import datetime
from decimal import Decimal

dynamodb = boto3.resource('dynamodb')
cloudwatch = boto3.client('cloudwatch')

def handler(event, context):
    """Process IoT telemetry data"""

    telemetry_table = dynamodb.Table(f"data-platform-telemetry-{os.environ['ENVIRONMENT']}")
    alerts_table = dynamodb.Table(f"data-platform-alerts-{os.environ['ENVIRONMENT']}")

    for record in event['Records']:
        payload = base64.b64decode(record['kinesis']['data']).decode('utf-8')
        telemetry = json.loads(payload)

        # Store telemetry
        telemetry_table.put_item(Item={
            'device_id': telemetry['device_id'],
            'timestamp': telemetry['timestamp'],
            'metrics': telemetry['metrics'],
            'location': telemetry.get('location')
        })

        # Check for anomalies
        if 'temperature' in telemetry['metrics']:
            temp = telemetry['metrics']['temperature']
            if temp > 100 or temp < -20:
                # Create alert
                alerts_table.put_item(Item={
                    'alert_id': f"{telemetry['device_id']}-{datetime.now().timestamp()}",
                    'device_id': telemetry['device_id'],
                    'alert_type': 'temperature_anomaly',
                    'value': temp,
                    'timestamp': datetime.now().isoformat()
                })

                # Send CloudWatch metric
                cloudwatch.put_metric_data(
                    Namespace='DataPlatform/IoT',
                    MetricData=[{
                        'MetricName': 'TemperatureAnomaly',
                        'Value': 1,
                        'Unit': 'Count',
                        'Dimensions': [
                            {'Name': 'DeviceId', 'Value': telemetry['device_id']}
                        ]
                    }]
                )

    return {'statusCode': 200}
'''

    def _get_transaction_processor_code(self) -> str:
        """Get code for transaction processor with fraud detection"""
        return '''
import json
import base64
import boto3
import os
from datetime import datetime, timedelta
from decimal import Decimal

dynamodb = boto3.resource('dynamodb')
sns = boto3.client('sns')

def handler(event, context):
    """Process financial transactions with fraud detection"""

    transactions_table = dynamodb.Table(f"data-platform-transactions-{os.environ['ENVIRONMENT']}")
    fraud_table = dynamodb.Table(f"data-platform-fraud-{os.environ['ENVIRONMENT']}")

    for record in event['Records']:
        payload = base64.b64decode(record['kinesis']['data']).decode('utf-8')
        transaction = json.loads(payload, parse_float=Decimal)

        # Store transaction
        transactions_table.put_item(Item=transaction)

        # Fraud detection logic
        fraud_score = calculate_fraud_score(transaction, transactions_table)

        if fraud_score > 0.7:
            # Flag as potential fraud
            fraud_table.put_item(Item={
                'transaction_id': transaction['transaction_id'],
                'fraud_score': fraud_score,
                'timestamp': datetime.now().isoformat(),
                'reason': 'High risk transaction pattern detected'
            })

            # Send alert
            if os.environ.get('SNS_TOPIC_ARN'):
                sns.publish(
                    TopicArn=os.environ['SNS_TOPIC_ARN'],
                    Subject='Potential Fraud Detected',
                    Message=json.dumps({
                        'transaction_id': transaction['transaction_id'],
                        'amount': str(transaction['amount']),
                        'fraud_score': str(fraud_score)
                    })
                )

    return {'statusCode': 200}

def calculate_fraud_score(transaction, table):
    """Calculate fraud score based on transaction patterns"""

    # Get recent transactions for this user
    response = table.query(
        IndexName='user-transactions',
        KeyConditionExpression='user_id = :uid',
        ExpressionAttributeValues={':uid': transaction['user_id']},
        Limit=10,
        ScanIndexForward=False
    )

    recent_transactions = response.get('Items', [])

    score = 0.0

    # Check for unusual amount
    if recent_transactions:
        avg_amount = sum(float(t['amount']) for t in recent_transactions) / len(recent_transactions)
        if float(transaction['amount']) > avg_amount * 3:
            score += 0.4

    # Check for rapid transactions
    if recent_transactions and len(recent_transactions) > 3:
        time_diff = (datetime.now() - datetime.fromisoformat(recent_transactions[0]['timestamp'])).seconds
        if time_diff < 60:  # Less than 1 minute since last transaction
            score += 0.3

    # Check for unusual location
    if 'location' in transaction and recent_transactions:
        if transaction['location'] != recent_transactions[0].get('location'):
            score += 0.3

    return min(score, 1.0)
'''