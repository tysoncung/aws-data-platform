"""
EMR Stack
Amazon EMR cluster for large-scale batch processing with Spark and Hive
"""

from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    CfnOutput,
    Tags,
    aws_emr as emr,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_s3 as s3,
    aws_logs as logs,
    aws_autoscaling as autoscaling
)
from constructs import Construct
from typing import Dict


class EMRStack(Stack):
    """
    Creates EMR cluster for batch processing workloads
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        vpc: ec2.Vpc,
        s3_buckets: Dict,
        environment: str,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.environment = environment
        self.vpc = vpc
        self.s3_buckets = s3_buckets

        # Create EMR service role
        self.emr_role = self._create_emr_service_role()

        # Create EC2 instance profile for EMR
        self.ec2_role = self._create_emr_ec2_role()
        self.ec2_profile = self._create_instance_profile()

        # Create security groups
        self.master_sg = self._create_master_security_group()
        self.worker_sg = self._create_worker_security_group()

        # Create EMR cluster
        self.cluster = self._create_emr_cluster()

        # Create auto-scaling configuration
        if environment != 'dev':
            self._configure_auto_scaling()

        # Output cluster ID
        CfnOutput(
            self, "ClusterId",
            value=self.cluster.ref,
            export_name=f"{self.stack_name}-cluster-id"
        )

    def _create_emr_service_role(self) -> iam.Role:
        """Create IAM role for EMR service"""

        role = iam.Role(
            self, "EMRServiceRole",
            role_name=f"EMRServiceRole-{self.environment}",
            assumed_by=iam.ServicePrincipal("elasticmapreduce.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonElasticMapReduceRole")
            ]
        )

        # Additional permissions for VPC
        role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "ec2:CreateNetworkInterface",
                    "ec2:RunInstances",
                    "ec2:CreateFleet",
                    "ec2:DescribeInstances",
                    "ec2:TerminateInstances",
                    "ec2:CreateTags"
                ],
                resources=["*"]
            )
        )

        return role

    def _create_emr_ec2_role(self) -> iam.Role:
        """Create IAM role for EMR EC2 instances"""

        role = iam.Role(
            self, "EMREC2Role",
            role_name=f"EMREC2Role-{self.environment}",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonElasticMapReduceforEC2Role")
            ]
        )

        # S3 access for data processing
        role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "s3:GetObject",
                    "s3:PutObject",
                    "s3:DeleteObject",
                    "s3:ListBucket"
                ],
                resources=[
                    f"arn:aws:s3:::data-platform-*",
                    f"arn:aws:s3:::data-platform-*/*"
                ]
            )
        )

        # Glue catalog access
        role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "glue:GetDatabase",
                    "glue:GetTable",
                    "glue:GetPartitions",
                    "glue:CreateTable",
                    "glue:UpdateTable"
                ],
                resources=["*"]
            )
        )

        # CloudWatch logs
        role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents"
                ],
                resources=["arn:aws:logs:*:*:*"]
            )
        )

        return role

    def _create_instance_profile(self) -> iam.CfnInstanceProfile:
        """Create EC2 instance profile for EMR"""

        return iam.CfnInstanceProfile(
            self, "EMRInstanceProfile",
            instance_profile_name=f"EMRInstanceProfile-{self.environment}",
            roles=[self.ec2_role.role_name]
        )

    def _create_master_security_group(self) -> ec2.SecurityGroup:
        """Create security group for EMR master node"""

        sg = ec2.SecurityGroup(
            self, "EMRMasterSecurityGroup",
            vpc=self.vpc,
            description="Security group for EMR master node",
            security_group_name=f"emr-master-{self.environment}"
        )

        # Allow SSH from bastion or specific IPs
        sg.add_ingress_rule(
            peer=ec2.Peer.ipv4("10.0.0.0/16"),  # VPC CIDR
            connection=ec2.Port.tcp(22),
            description="SSH access"
        )

        # Web UIs
        web_ports = [
            (8088, "YARN ResourceManager"),
            (9870, "HDFS NameNode"),
            (8998, "Livy"),
            (18080, "Spark History Server"),
            (9443, "Ganglia"),
            (8442, "Apache Ranger")
        ]

        for port, description in web_ports:
            sg.add_ingress_rule(
                peer=ec2.Peer.ipv4("10.0.0.0/16"),
                connection=ec2.Port.tcp(port),
                description=description
            )

        return sg

    def _create_worker_security_group(self) -> ec2.SecurityGroup:
        """Create security group for EMR worker nodes"""

        sg = ec2.SecurityGroup(
            self, "EMRWorkerSecurityGroup",
            vpc=self.vpc,
            description="Security group for EMR worker nodes",
            security_group_name=f"emr-worker-{self.environment}"
        )

        # Allow all traffic from master
        sg.add_ingress_rule(
            peer=self.master_sg,
            connection=ec2.Port.all_traffic(),
            description="All traffic from master"
        )

        return sg

    def _create_emr_cluster(self) -> emr.CfnCluster:
        """Create EMR cluster"""

        # Cluster configuration
        cluster_config = self._get_cluster_configuration()

        # Create cluster
        cluster = emr.CfnCluster(
            self, "EMRCluster",
            name=f"data-platform-{self.environment}",
            release_label="emr-6.9.0",
            service_role=self.emr_role.role_arn,
            job_flow_role=self.ec2_profile.ref,
            visible_to_all_users=True,
            log_uri=f"s3://data-platform-logs-{self.environment}/emr/",

            # Applications
            applications=[
                emr.CfnCluster.ApplicationProperty(name="Spark"),
                emr.CfnCluster.ApplicationProperty(name="Hadoop"),
                emr.CfnCluster.ApplicationProperty(name="Hive"),
                emr.CfnCluster.ApplicationProperty(name="Livy"),
                emr.CfnCluster.ApplicationProperty(name="JupyterHub"),
                emr.CfnCluster.ApplicationProperty(name="Ganglia"),
                emr.CfnCluster.ApplicationProperty(name="Presto")
            ],

            # Configurations
            configurations=cluster_config,

            # Instance configuration
            instances=emr.CfnCluster.JobFlowInstancesConfigProperty(
                master_instance_group=emr.CfnCluster.InstanceGroupConfigProperty(
                    instance_count=1,
                    instance_type=self._get_master_instance_type(),
                    market="ON_DEMAND",
                    name="Master"
                ),
                core_instance_group=emr.CfnCluster.InstanceGroupConfigProperty(
                    instance_count=self._get_core_instance_count(),
                    instance_type=self._get_core_instance_type(),
                    market="ON_DEMAND" if self.environment == 'prod' else "SPOT",
                    name="Core",
                    ebs_configuration=emr.CfnCluster.EbsConfigurationProperty(
                        ebs_block_device_configs=[
                            emr.CfnCluster.EbsBlockDeviceConfigProperty(
                                volume_specification=emr.CfnCluster.VolumeSpecificationProperty(
                                    size_in_gb=100,
                                    volume_type="gp3"
                                ),
                                volumes_per_instance=1
                            )
                        ]
                    )
                ),
                ec2_subnet_id=self.vpc.private_subnets[0].subnet_id,
                emr_managed_master_security_group=self.master_sg.security_group_id,
                emr_managed_slave_security_group=self.worker_sg.security_group_id,
                termination_protected=self.environment == 'prod'
            ),

            # Bootstrap actions
            bootstrap_actions=[
                emr.CfnCluster.BootstrapActionConfigProperty(
                    name="Install Python packages",
                    script_bootstrap_action=emr.CfnCluster.ScriptBootstrapActionConfigProperty(
                        path=f"s3://data-platform-scripts-{self.environment}/bootstrap/install_packages.sh",
                        args=["pandas", "numpy", "scikit-learn", "pyarrow"]
                    )
                )
            ],

            # Step concurrency
            step_concurrency_level=5 if self.environment == 'prod' else 1,

            # Tags
            tags=[
                {
                    "key": "Environment",
                    "value": self.environment
                },
                {
                    "key": "Project",
                    "value": "DataPlatform"
                }
            ]
        )

        return cluster

    def _get_cluster_configuration(self) -> list:
        """Get EMR cluster configuration"""

        return [
            {
                "classification": "spark",
                "properties": {
                    "maximizeResourceAllocation": "true"
                }
            },
            {
                "classification": "spark-defaults",
                "properties": {
                    "spark.dynamicAllocation.enabled": "true",
                    "spark.shuffle.service.enabled": "true",
                    "spark.serializer": "org.apache.spark.serializer.KryoSerializer",
                    "spark.sql.adaptive.enabled": "true",
                    "spark.sql.adaptive.coalescePartitions.enabled": "true",
                    "spark.speculation": "false",
                    "spark.sql.catalogImplementation": "hive"
                }
            },
            {
                "classification": "spark-hive-site",
                "properties": {
                    "hive.metastore.client.factory.class":
                        "com.amazonaws.glue.catalog.metastore.AWSGlueDataCatalogHiveClientFactory"
                }
            },
            {
                "classification": "hive-site",
                "properties": {
                    "hive.metastore.client.factory.class":
                        "com.amazonaws.glue.catalog.metastore.AWSGlueDataCatalogHiveClientFactory",
                    "hive.metastore.schema.verification": "false"
                }
            },
            {
                "classification": "yarn-site",
                "properties": {
                    "yarn.nodemanager.vmem-check-enabled": "false",
                    "yarn.nodemanager.pmem-check-enabled": "false"
                }
            },
            {
                "classification": "hdfs-site",
                "properties": {
                    "dfs.replication": "2" if self.environment != 'dev' else "1"
                }
            },
            {
                "classification": "emrfs-site",
                "properties": {
                    "fs.s3.maxConnections": "1000",
                    "fs.s3.maxRetries": "20"
                }
            }
        ]

    def _configure_auto_scaling(self):
        """Configure auto-scaling for EMR cluster"""

        # Auto-scaling policy for task nodes
        auto_scaling_policy = {
            "Constraints": {
                "MinCapacity": 0,
                "MaxCapacity": 10
            },
            "Rules": [
                {
                    "Name": "ScaleUpMemory",
                    "Trigger": {
                        "CloudWatchAlarmDefinition": {
                            "ComparisonOperator": "LESS_THAN",
                            "MetricName": "YARNMemoryAvailablePercentage",
                            "Namespace": "AWS/ElasticMapReduce",
                            "Period": 300,
                            "Threshold": 15,
                            "Statistic": "AVERAGE",
                            "EvaluationPeriods": 1
                        }
                    },
                    "Action": {
                        "SimpleScalingPolicyConfiguration": {
                            "AdjustmentType": "CHANGE_IN_CAPACITY",
                            "ScalingAdjustment": 2,
                            "CoolDown": 300
                        }
                    }
                },
                {
                    "Name": "ScaleDownMemory",
                    "Trigger": {
                        "CloudWatchAlarmDefinition": {
                            "ComparisonOperator": "GREATER_THAN",
                            "MetricName": "YARNMemoryAvailablePercentage",
                            "Namespace": "AWS/ElasticMapReduce",
                            "Period": 300,
                            "Threshold": 75,
                            "Statistic": "AVERAGE",
                            "EvaluationPeriods": 2
                        }
                    },
                    "Action": {
                        "SimpleScalingPolicyConfiguration": {
                            "AdjustmentType": "CHANGE_IN_CAPACITY",
                            "ScalingAdjustment": -1,
                            "CoolDown": 300
                        }
                    }
                }
            ]
        }

        # Apply auto-scaling policy (would be applied via Step Function or Lambda)

    def _get_master_instance_type(self) -> str:
        """Get master instance type based on environment"""
        instance_types = {
            'dev': 'm5.xlarge',
            'staging': 'm5.2xlarge',
            'prod': 'm5.4xlarge'
        }
        return instance_types.get(self.environment, 'm5.xlarge')

    def _get_core_instance_type(self) -> str:
        """Get core instance type based on environment"""
        instance_types = {
            'dev': 'm5.xlarge',
            'staging': 'm5.2xlarge',
            'prod': 'r5.4xlarge'
        }
        return instance_types.get(self.environment, 'm5.xlarge')

    def _get_core_instance_count(self) -> int:
        """Get core instance count based on environment"""
        instance_counts = {
            'dev': 2,
            'staging': 3,
            'prod': 5
        }
        return instance_counts.get(self.environment, 2)