# Network Architecture

## Overview

The AWS Data Platform uses a multi-tier network architecture with strict isolation between public, private, and database layers. This document describes the network design, connectivity patterns, and security controls.

## VPC Design

### Network Topology

```
┌─────────────────────────────────────────────────────────────┐
│                    VPC: 10.0.0.0/16                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────────────┐    ┌──────────────────────┐     │
│  │  Public Subnet 1     │    │  Public Subnet 2     │     │
│  │  10.0.1.0/24        │    │  10.0.2.0/24        │     │
│  │  AZ: us-east-1a     │    │  AZ: us-east-1b     │     │
│  │  ┌────────────┐     │    │  ┌────────────┐     │     │
│  │  │    NAT     │     │    │  │    NAT     │     │     │
│  │  │  Gateway   │     │    │  │  Gateway   │     │     │
│  │  └────────────┘     │    │  └────────────┘     │     │
│  └──────────┬───────────┘    └──────────┬──────────┘     │
│             │                           │                  │
│  ┌──────────▼───────────┐    ┌──────────▼──────────┐     │
│  │  Private Subnet 1    │    │  Private Subnet 2   │     │
│  │  10.0.10.0/24       │    │  10.0.11.0/24       │     │
│  │  AZ: us-east-1a     │    │  AZ: us-east-1b     │     │
│  │  ┌────────────┐     │    │  ┌────────────┐     │     │
│  │  │EMR Cluster │     │    │  │  Lambda    │     │     │
│  │  │  Workers   │     │    │  │ Functions  │     │     │
│  │  └────────────┘     │    │  └────────────┘     │     │
│  └──────────────────────┘    └──────────────────────┘     │
│                                                             │
│  ┌──────────────────────┐    ┌──────────────────────┐     │
│  │  Database Subnet 1   │    │  Database Subnet 2  │     │
│  │  10.0.20.0/24       │    │  10.0.21.0/24       │     │
│  │  AZ: us-east-1a     │    │  AZ: us-east-1b     │     │
│  │  ┌────────────┐     │    │  ┌────────────┐     │     │
│  │  │  Redshift  │     │    │  │    RDS     │     │     │
│  │  │  Cluster   │     │    │  │  Instance  │     │     │
│  │  └────────────┘     │    │  └────────────┘     │     │
│  └──────────────────────┘    └──────────────────────┘     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### CIDR Allocation

| Subnet Type | CIDR Block | Available IPs | Purpose |
|------------|------------|---------------|---------|
| VPC | 10.0.0.0/16 | 65,536 | Entire network |
| Public-1a | 10.0.1.0/24 | 256 | NAT, ALB, Bastion |
| Public-1b | 10.0.2.0/24 | 256 | NAT, ALB, Bastion |
| Private-1a | 10.0.10.0/24 | 256 | EMR, Lambda, ECS |
| Private-1b | 10.0.11.0/24 | 256 | EMR, Lambda, ECS |
| Database-1a | 10.0.20.0/24 | 256 | Redshift, RDS |
| Database-1b | 10.0.21.0/24 | 256 | Redshift, RDS |
| Reserved | 10.0.30.0/20 | 4,096 | Future expansion |

## CDK Implementation

### VPC Stack

```python
from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_logs as logs,
    RemovalPolicy,
    CfnOutput
)
from constructs import Construct

class VPCStack(Stack):
    """Network infrastructure stack"""

    def __init__(self, scope: Construct, construct_id: str, environment: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.environment = environment

        # Create VPC
        self.vpc = ec2.Vpc(
            self, "DataPlatformVPC",
            vpc_name=f"data-platform-{environment}",
            cidr="10.0.0.0/16",
            max_azs=2,
            nat_gateways=2,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24
                ),
                ec2.SubnetConfiguration(
                    name="Private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24
                ),
                ec2.SubnetConfiguration(
                    name="Database",
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=24
                )
            ],
            enable_dns_hostnames=True,
            enable_dns_support=True
        )

        # VPC Flow Logs
        self._create_flow_logs()

        # VPC Endpoints
        self._create_vpc_endpoints()

        # Network ACLs
        self._create_network_acls()

        # Bastion Host
        if environment == 'prod':
            self._create_bastion_host()

        # Outputs
        CfnOutput(
            self, "VPCId",
            value=self.vpc.vpc_id,
            export_name=f"{self.stack_name}-vpc-id"
        )

    def _create_flow_logs(self):
        """Enable VPC Flow Logs"""

        log_group = logs.LogGroup(
            self, "VPCFlowLogs",
            log_group_name=f"/aws/vpc/{self.environment}",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.DESTROY
        )

        ec2.FlowLog(
            self, "FlowLog",
            resource_type=ec2.FlowLogResourceType.from_vpc(self.vpc),
            destination=ec2.FlowLogDestination.to_cloud_watch_logs(log_group),
            traffic_type=ec2.TrafficType.ALL
        )

    def _create_vpc_endpoints(self):
        """Create VPC endpoints for AWS services"""

        # S3 Gateway Endpoint
        self.vpc.add_gateway_endpoint(
            "S3Endpoint",
            service=ec2.GatewayVpcEndpointAwsService.S3
        )

        # DynamoDB Gateway Endpoint
        self.vpc.add_gateway_endpoint(
            "DynamoDBEndpoint",
            service=ec2.GatewayVpcEndpointAwsService.DYNAMODB
        )

        # Interface Endpoints
        services = [
            ("KinesisEndpoint", ec2.InterfaceVpcEndpointAwsService.KINESIS_STREAMS),
            ("SecretsManagerEndpoint", ec2.InterfaceVpcEndpointAwsService.SECRETS_MANAGER),
            ("KMSEndpoint", ec2.InterfaceVpcEndpointAwsService.KMS),
            ("CloudWatchEndpoint", ec2.InterfaceVpcEndpointAwsService.CLOUDWATCH_LOGS),
            ("SageMakerEndpoint", ec2.InterfaceVpcEndpointAwsService.SAGEMAKER_RUNTIME)
        ]

        for endpoint_name, service in services:
            self.vpc.add_interface_endpoint(
                endpoint_name,
                service=service,
                private_dns_enabled=True
            )

    def _create_network_acls(self):
        """Create custom Network ACLs"""

        # Database Subnet NACL
        db_nacl = ec2.NetworkAcl(
            self, "DatabaseNACL",
            vpc=self.vpc,
            subnet_selection=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED
            )
        )

        # Allow inbound from private subnets
        db_nacl.add_entry(
            "AllowPrivateInbound",
            rule_number=100,
            cidr=ec2.AclCidr.ipv4("10.0.10.0/23"),
            traffic=ec2.AclTraffic.all_traffic(),
            direction=ec2.TrafficDirection.INGRESS,
            rule_action=ec2.Action.ALLOW
        )

        # Allow all outbound
        db_nacl.add_entry(
            "AllowAllOutbound",
            rule_number=100,
            cidr=ec2.AclCidr.any_ipv4(),
            traffic=ec2.AclTraffic.all_traffic(),
            direction=ec2.TrafficDirection.EGRESS,
            rule_action=ec2.Action.ALLOW
        )

    def _create_bastion_host(self):
        """Create bastion host for secure access"""

        bastion = ec2.BastionHostLinux(
            self, "BastionHost",
            vpc=self.vpc,
            instance_name=f"bastion-{self.environment}",
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.T3,
                ec2.InstanceSize.MICRO
            ),
            subnet_selection=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PUBLIC
            )
        )

        # Allow SSH from specific IPs
        bastion.allow_ssh_access_from(
            ec2.Peer.ipv4("203.0.113.0/24")  # Replace with your IP range
        )
```

## Security Groups

### Security Group Architecture

```python
# Security Group Definitions
security_groups = {
    "alb_sg": {
        "description": "Application Load Balancer",
        "rules": {
            "inbound": [
                {"port": 443, "protocol": "tcp", "source": "0.0.0.0/0"},
                {"port": 80, "protocol": "tcp", "source": "0.0.0.0/0"}
            ],
            "outbound": [
                {"port": 0, "protocol": "-1", "destination": "0.0.0.0/0"}
            ]
        }
    },
    "emr_master_sg": {
        "description": "EMR Master Node",
        "rules": {
            "inbound": [
                {"port": 8088, "protocol": "tcp", "source": "alb_sg"},
                {"port": 18080, "protocol": "tcp", "source": "alb_sg"},
                {"port": 22, "protocol": "tcp", "source": "bastion_sg"}
            ],
            "outbound": [
                {"port": 0, "protocol": "-1", "destination": "0.0.0.0/0"}
            ]
        }
    },
    "emr_worker_sg": {
        "description": "EMR Worker Nodes",
        "rules": {
            "inbound": [
                {"port": 0, "protocol": "-1", "source": "emr_master_sg"},
                {"port": 0, "protocol": "-1", "source": "self"}
            ],
            "outbound": [
                {"port": 0, "protocol": "-1", "destination": "0.0.0.0/0"}
            ]
        }
    },
    "lambda_sg": {
        "description": "Lambda Functions",
        "rules": {
            "inbound": [],
            "outbound": [
                {"port": 443, "protocol": "tcp", "destination": "0.0.0.0/0"},
                {"port": 5439, "protocol": "tcp", "destination": "redshift_sg"},
                {"port": 443, "protocol": "tcp", "destination": "dynamodb_endpoint"}
            ]
        }
    },
    "redshift_sg": {
        "description": "Redshift Cluster",
        "rules": {
            "inbound": [
                {"port": 5439, "protocol": "tcp", "source": "lambda_sg"},
                {"port": 5439, "protocol": "tcp", "source": "emr_master_sg"},
                {"port": 5439, "protocol": "tcp", "source": "quicksight_sg"}
            ],
            "outbound": [
                {"port": 443, "protocol": "tcp", "destination": "s3_endpoint"}
            ]
        }
    }
}
```

### Security Group Implementation

```python
def create_security_groups(self, vpc: ec2.Vpc) -> Dict[str, ec2.SecurityGroup]:
    """Create security groups for all components"""

    security_groups = {}

    # ALB Security Group
    security_groups['alb'] = ec2.SecurityGroup(
        self, "ALBSecurityGroup",
        vpc=vpc,
        description="Security group for Application Load Balancer",
        allow_all_outbound=True
    )
    security_groups['alb'].add_ingress_rule(
        peer=ec2.Peer.any_ipv4(),
        connection=ec2.Port.tcp(443),
        description="HTTPS from Internet"
    )

    # Lambda Security Group
    security_groups['lambda'] = ec2.SecurityGroup(
        self, "LambdaSecurityGroup",
        vpc=vpc,
        description="Security group for Lambda functions",
        allow_all_outbound=False
    )

    # Redshift Security Group
    security_groups['redshift'] = ec2.SecurityGroup(
        self, "RedshiftSecurityGroup",
        vpc=vpc,
        description="Security group for Redshift cluster",
        allow_all_outbound=False
    )

    # Add inter-service rules
    security_groups['lambda'].add_egress_rule(
        peer=security_groups['redshift'],
        connection=ec2.Port.tcp(5439),
        description="Lambda to Redshift"
    )

    security_groups['redshift'].add_ingress_rule(
        peer=security_groups['lambda'],
        connection=ec2.Port.tcp(5439),
        description="Lambda to Redshift"
    )

    return security_groups
```

## Direct Connect and VPN

### Direct Connect Configuration

```python
# Direct Connect Virtual Interface
direct_connect = {
    "ConnectionId": "dxcon-abc123",
    "VLAN": 100,
    "CustomerAddress": "192.168.1.1/30",
    "AmazonAddress": "192.168.1.2/30",
    "AddressFamily": "ipv4",
    "DirectConnectGatewayId": "dx-gateway-id",
    "BGPAsn": 65000
}

# Virtual Private Gateway
vpg = ec2.CfnVPNGateway(
    self, "VPNGateway",
    type="ipsec.1",
    amazon_side_asn=64512
)

# Attach to VPC
ec2.CfnVPCGatewayAttachment(
    self, "VPGAttachment",
    vpc_id=vpc.vpc_id,
    vpn_gateway_id=vpg.ref
)
```

### Site-to-Site VPN

```python
# Customer Gateway
customer_gateway = ec2.CfnCustomerGateway(
    self, "CustomerGateway",
    type="ipsec.1",
    ip_address="203.0.113.12",  # Customer public IP
    bgp_asn=65000
)

# VPN Connection
vpn_connection = ec2.CfnVPNConnection(
    self, "VPNConnection",
    type="ipsec.1",
    customer_gateway_id=customer_gateway.ref,
    vpn_gateway_id=vpg.ref,
    static_routes_only=False,
    vpn_tunnel_options_specifications=[
        {
            "TunnelInsideCidr": "169.254.10.0/30",
            "PreSharedKey": "YOUR_PRESHARED_KEY"
        },
        {
            "TunnelInsideCidr": "169.254.11.0/30",
            "PreSharedKey": "YOUR_PRESHARED_KEY"
        }
    ]
)
```

## Transit Gateway

### Multi-VPC Architecture

```python
# Transit Gateway
transit_gateway = ec2.CfnTransitGateway(
    self, "TransitGateway",
    amazon_side_asn=64512,
    description="Data Platform Transit Gateway",
    default_route_table_association="enable",
    default_route_table_propagation="enable",
    dns_support="enable",
    vpn_ecmp_support="enable"
)

# Attach VPCs
for vpc_config in vpc_attachments:
    attachment = ec2.CfnTransitGatewayAttachment(
        self, f"TGWAttachment-{vpc_config['name']}",
        transit_gateway_id=transit_gateway.ref,
        vpc_id=vpc_config['vpc_id'],
        subnet_ids=vpc_config['subnet_ids']
    )

# Route Tables
route_table = ec2.CfnTransitGatewayRouteTable(
    self, "TGWRouteTable",
    transit_gateway_id=transit_gateway.ref
)

# Routes
ec2.CfnTransitGatewayRoute(
    self, "DefaultRoute",
    transit_gateway_route_table_id=route_table.ref,
    destination_cidr_block="0.0.0.0/0",
    transit_gateway_attachment_id=egress_attachment.ref
)
```

## DNS Resolution

### Route 53 Private Hosted Zone

```python
from aws_cdk import aws_route53 as route53

# Private Hosted Zone
private_zone = route53.PrivateHostedZone(
    self, "PrivateZone",
    zone_name="dataplatform.internal",
    vpc=vpc
)

# DNS Records
route53.ARecord(
    self, "RedshiftDNS",
    zone=private_zone,
    record_name="warehouse",
    target=route53.RecordTarget.from_alias(
        route53_targets.RedshiftClusterEndpointTarget(redshift_cluster)
    )
)

route53.CnameRecord(
    self, "EMRMasterDNS",
    zone=private_zone,
    record_name="emr-master",
    domain_name=emr_cluster.master_public_dns
)
```

## Network Performance Optimization

### Enhanced Networking

```python
# Enable SR-IOV for EMR instances
emr_launch_config = {
    "Instances": {
        "InstanceGroups": [{
            "InstanceRole": "MASTER",
            "InstanceType": "m5.xlarge",
            "InstanceCount": 1,
            "Configurations": [{
                "Classification": "yarn-site",
                "Properties": {
                    "yarn.scheduler.capacity.resource-calculator":
                        "org.apache.hadoop.yarn.util.resource.DominantResourceCalculator"
                }
            }],
            "EbsConfiguration": {
                "EbsOptimized": True
            }
        }],
        "Ec2SubnetId": private_subnet.subnet_id,
        "AdditionalMasterSecurityGroups": [emr_master_sg.security_group_id]
    }
}
```

### VPC Peering

```python
# VPC Peering Connection
peering = ec2.CfnVPCPeeringConnection(
    self, "VPCPeering",
    vpc_id=vpc.vpc_id,
    peer_vpc_id="vpc-peer123",
    peer_region="us-west-2"
)

# Update Route Tables
for subnet in vpc.private_subnets:
    ec2.CfnRoute(
        self, f"PeeringRoute-{subnet.subnet_id}",
        route_table_id=subnet.route_table.route_table_id,
        destination_cidr_block="172.16.0.0/16",
        vpc_peering_connection_id=peering.ref
    )
```

## Network Monitoring

### VPC Flow Logs Analysis

```python
# Athena Table for Flow Logs
create_table_query = """
CREATE EXTERNAL TABLE IF NOT EXISTS vpc_flow_logs (
    version int,
    account_id string,
    interface_id string,
    src_addr string,
    dst_addr string,
    src_port int,
    dst_port int,
    protocol bigint,
    packets bigint,
    bytes bigint,
    start_time bigint,
    end_time bigint,
    action string,
    log_status string
)
PARTITIONED BY (dt string)
STORED AS PARQUET
LOCATION 's3://data-platform-logs/vpc-flow-logs/'
"""

# Analysis Queries
top_talkers = """
SELECT
    src_addr,
    dst_addr,
    SUM(bytes) as total_bytes,
    COUNT(*) as connection_count
FROM vpc_flow_logs
WHERE dt = CURRENT_DATE
GROUP BY src_addr, dst_addr
ORDER BY total_bytes DESC
LIMIT 10
"""
```

### CloudWatch Metrics

```python
# Network Metrics Dashboard
dashboard = cloudwatch.CfnDashboard(
    self, "NetworkDashboard",
    dashboard_name="DataPlatform-Network",
    dashboard_body=json.dumps({
        "widgets": [
            {
                "type": "metric",
                "properties": {
                    "metrics": [
                        ["AWS/EC2", "NetworkIn", {"stat": "Sum"}],
                        [".", "NetworkOut", {"stat": "Sum"}],
                        ["AWS/NAT", "BytesInFromDestination"],
                        [".", "BytesOutToSource"]
                    ],
                    "period": 300,
                    "stat": "Average",
                    "region": "us-east-1",
                    "title": "Network Traffic"
                }
            }
        ]
    })
)
```

## Best Practices

1. **Segmentation**
   - Isolate workloads by subnet
   - Use security groups as primary control
   - Implement NACLs for defense in depth

2. **High Availability**
   - Deploy across multiple AZs
   - Use redundant NAT gateways
   - Implement connection draining

3. **Cost Optimization**
   - Use VPC endpoints to reduce NAT costs
   - Right-size NAT instances
   - Implement S3 Transfer Acceleration

4. **Security**
   - Enable VPC Flow Logs
   - Use PrivateLink for SaaS
   - Implement GuardDuty

5. **Performance**
   - Use placement groups for HPC
   - Enable enhanced networking
   - Optimize route tables