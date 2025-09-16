"""
Kinesis Streaming Stack
Implements real-time data streaming infrastructure using Amazon Kinesis
"""

from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    CfnOutput,
    aws_kinesis as kinesis,
    aws_kinesis_firehose as firehose,
    aws_iam as iam,
    aws_kinesisanalytics_v2 as analytics,
    aws_logs as logs
)
from constructs import Construct
from typing import Dict


class KinesisStreamingStack(Stack):
    """
    Creates Kinesis Data Streams for real-time data ingestion and processing
    """

    def __init__(self, scope: Construct, construct_id: str, environment: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.environment = environment
        self.streams = {}

        # Create main data ingestion stream
        self.streams['main'] = self._create_data_stream(
            "MainDataStream",
            shard_count=self._get_shard_count(),
            retention_days=7
        )

        # Create clickstream data stream for web analytics
        self.streams['clickstream'] = self._create_data_stream(
            "ClickstreamDataStream",
            shard_count=2,
            retention_days=3
        )

        # Create IoT data stream for device telemetry
        self.streams['iot'] = self._create_data_stream(
            "IoTDataStream",
            shard_count=4,
            retention_days=1
        )

        # Create transaction stream for financial data
        self.streams['transactions'] = self._create_data_stream(
            "TransactionDataStream",
            shard_count=self._get_shard_count(),
            retention_days=30,
            encryption=True
        )

        # Create Kinesis Analytics application for real-time SQL
        self.analytics_app = self._create_analytics_application()

        # Create Kinesis Data Firehose for S3 delivery
        self.firehose_delivery = self._create_firehose_delivery()

        # Output stream ARNs for cross-stack references
        for stream_name, stream in self.streams.items():
            CfnOutput(
                self, f"{stream_name}StreamArn",
                value=stream.stream_arn,
                export_name=f"{self.stack_name}-{stream_name}-stream-arn"
            )

    def _create_data_stream(
        self,
        stream_name: str,
        shard_count: int,
        retention_days: int,
        encryption: bool = True
    ) -> kinesis.Stream:
        """Create a Kinesis Data Stream with specified configuration"""

        stream = kinesis.Stream(
            self, stream_name,
            stream_name=f"{stream_name.lower()}-{self.environment}",
            shard_count=shard_count,
            retention_period=Duration.days(retention_days),
            encryption=kinesis.StreamEncryption.MANAGED if encryption else kinesis.StreamEncryption.UNENCRYPTED,
            removal_policy=RemovalPolicy.DESTROY if self.environment == 'dev' else RemovalPolicy.RETAIN
        )

        # Add CloudWatch metrics
        stream.metric_incoming_records().create_alarm(
            self, f"{stream_name}HighVolume",
            threshold=1000000,
            evaluation_periods=1,
            alarm_description=f"High volume of records in {stream_name}"
        )

        stream.metric_get_records_iterator_age_milliseconds().create_alarm(
            self, f"{stream_name}IteratorAge",
            threshold=60000,
            evaluation_periods=2,
            alarm_description=f"Iterator age too high for {stream_name}"
        )

        return stream

    def _create_analytics_application(self) -> analytics.CfnApplicationV2:
        """Create Kinesis Analytics application for real-time SQL queries"""

        analytics_role = iam.Role(
            self, "AnalyticsRole",
            assumed_by=iam.ServicePrincipal("kinesisanalytics.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonKinesisAnalyticsFullAccess")
            ]
        )

        # Grant read access to all streams
        for stream in self.streams.values():
            stream.grant_read(analytics_role)

        # SQL application code for real-time analytics
        sql_code = """
        CREATE OR REPLACE STREAM "DESTINATION_SQL_STREAM" (
            event_time TIMESTAMP,
            event_type VARCHAR(64),
            user_id VARCHAR(128),
            metric_value DOUBLE,
            aggregated_value DOUBLE
        );

        CREATE OR REPLACE PUMP "STREAM_PUMP" AS INSERT INTO "DESTINATION_SQL_STREAM"
        SELECT STREAM
            ROWTIME as event_time,
            event_type,
            user_id,
            metric_value,
            SUM(metric_value) OVER (
                PARTITION BY user_id
                RANGE INTERVAL '1' HOUR PRECEDING
            ) as aggregated_value
        FROM SOURCE_SQL_STREAM_001
        WHERE event_type IS NOT NULL;
        """

        application = analytics.CfnApplicationV2(
            self, "StreamAnalyticsApp",
            application_name=f"data-platform-analytics-{self.environment}",
            runtime_environment="SQL-1_0",
            service_execution_role=analytics_role.role_arn,
            application_configuration=analytics.CfnApplicationV2.ApplicationConfigurationProperty(
                application_code_configuration=analytics.CfnApplicationV2.ApplicationCodeConfigurationProperty(
                    code_content=analytics.CfnApplicationV2.CodeContentProperty(
                        text_content=sql_code
                    ),
                    code_content_type="PLAINTEXT"
                ),
                sql_application_configuration=analytics.CfnApplicationV2.SqlApplicationConfigurationProperty(
                    inputs=[
                        analytics.CfnApplicationV2.InputProperty(
                            name_prefix="SOURCE_SQL_STREAM",
                            input_schema=analytics.CfnApplicationV2.InputSchemaProperty(
                                record_columns=[
                                    analytics.CfnApplicationV2.RecordColumnProperty(
                                        name="event_type",
                                        sql_type="VARCHAR(64)",
                                        mapping="$.eventType"
                                    ),
                                    analytics.CfnApplicationV2.RecordColumnProperty(
                                        name="user_id",
                                        sql_type="VARCHAR(128)",
                                        mapping="$.userId"
                                    ),
                                    analytics.CfnApplicationV2.RecordColumnProperty(
                                        name="metric_value",
                                        sql_type="DOUBLE",
                                        mapping="$.metricValue"
                                    )
                                ],
                                record_format=analytics.CfnApplicationV2.RecordFormatProperty(
                                    record_format_type="JSON",
                                    mapping_parameters=analytics.CfnApplicationV2.MappingParametersProperty(
                                        json_mapping_parameters=analytics.CfnApplicationV2.JSONMappingParametersProperty(
                                            record_row_path="$"
                                        )
                                    )
                                )
                            ),
                            kinesis_streams_input=analytics.CfnApplicationV2.KinesisStreamsInputProperty(
                                resource_arn=self.streams['main'].stream_arn
                            )
                        )
                    ]
                )
            )
        )

        return application

    def _create_firehose_delivery(self) -> firehose.CfnDeliveryStream:
        """Create Kinesis Data Firehose for batch delivery to S3"""

        firehose_role = iam.Role(
            self, "FirehoseRole",
            assumed_by=iam.ServicePrincipal("firehose.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonKinesisFirehoseFullAccess")
            ]
        )

        # Log group for Firehose errors
        log_group = logs.LogGroup(
            self, "FirehoseLogGroup",
            log_group_name=f"/aws/kinesisfirehose/{self.environment}",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY
        )

        # Create Firehose delivery stream
        delivery_stream = firehose.CfnDeliveryStream(
            self, "S3DeliveryStream",
            delivery_stream_name=f"data-platform-s3-delivery-{self.environment}",
            delivery_stream_type="KinesisStreamAsSource",
            kinesis_stream_source_configuration=firehose.CfnDeliveryStream.KinesisStreamSourceConfigurationProperty(
                kinesis_stream_arn=self.streams['main'].stream_arn,
                role_arn=firehose_role.role_arn
            ),
            extended_s3_destination_configuration=firehose.CfnDeliveryStream.ExtendedS3DestinationConfigurationProperty(
                bucket_arn=f"arn:aws:s3:::data-platform-raw-{self.environment}",
                prefix="kinesis/year=!{timestamp:yyyy}/month=!{timestamp:MM}/day=!{timestamp:dd}/",
                error_output_prefix="errors/",
                buffering_hints=firehose.CfnDeliveryStream.BufferingHintsProperty(
                    interval_in_seconds=60,
                    size_in_m_bs=128
                ),
                compression_format="GZIP",
                role_arn=firehose_role.role_arn,
                processing_configuration=firehose.CfnDeliveryStream.ProcessingConfigurationProperty(
                    enabled=True,
                    processors=[
                        firehose.CfnDeliveryStream.ProcessorProperty(
                            type="RecordDeAggregation",
                            parameters=[
                                firehose.CfnDeliveryStream.ProcessorParameterProperty(
                                    parameter_name="SubRecordType",
                                    parameter_value="JSON"
                                )
                            ]
                        )
                    ]
                ),
                data_format_conversion_configuration=firehose.CfnDeliveryStream.DataFormatConversionConfigurationProperty(
                    enabled=True,
                    output_format_configuration=firehose.CfnDeliveryStream.OutputFormatConfigurationProperty(
                        serializer=firehose.CfnDeliveryStream.SerializerProperty(
                            parquet_ser_de=firehose.CfnDeliveryStream.ParquetSerDeProperty()
                        )
                    )
                ),
                cloud_watch_logging_options=firehose.CfnDeliveryStream.CloudWatchLoggingOptionsProperty(
                    enabled=True,
                    log_group_name=log_group.log_group_name,
                    log_stream_name=f"s3-delivery-{self.environment}"
                )
            )
        )

        return delivery_stream

    def _get_shard_count(self) -> int:
        """Get appropriate shard count based on environment"""
        shard_counts = {
            'dev': 2,
            'staging': 4,
            'prod': 10
        }
        return shard_counts.get(self.environment, 2)