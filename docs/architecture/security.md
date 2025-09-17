# Security Architecture

## Overview

The AWS Data Platform implements defense-in-depth security with multiple layers of protection for data, infrastructure, and access control. This document outlines the security architecture, controls, and best practices.

## Security Principles

### 1. Least Privilege Access
- Grant minimum permissions required
- Use IAM roles instead of users
- Regular access reviews

### 2. Defense in Depth
- Multiple security layers
- Redundant controls
- Fail-secure defaults

### 3. Zero Trust Model
- Verify everything
- Never trust, always verify
- Continuous authentication

### 4. Data Protection
- Encryption everywhere
- Data classification
- Privacy by design

## Identity and Access Management (IAM)

### Role Architecture

```python
# IAM Role Definitions
roles = {
    "DataEngineerRole": {
        "assume_role_policy": "arn:aws:iam::aws:policy/DataEngineerAssumeRole",
        "managed_policies": [
            "AmazonS3ReadOnlyAccess",
            "AmazonEMRFullAccess",
            "AWSGlueConsoleFullAccess"
        ],
        "inline_policies": {
            "RedshiftAccess": {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": [
                            "redshift:DescribeClusters",
                            "redshift:ExecuteQuery",
                            "redshift-data:ExecuteStatement"
                        ],
                        "Resource": "arn:aws:redshift:*:*:cluster:data-platform-*"
                    }
                ]
            }
        }
    },
    "DataScientistRole": {
        "managed_policies": [
            "AmazonSageMakerFullAccess",
            "AmazonS3ReadOnlyAccess"
        ],
        "inline_policies": {
            "NotebookAccess": {
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": [
                            "sagemaker:CreateNotebookInstance",
                            "sagemaker:StartNotebookInstance"
                        ],
                        "Resource": "*",
                        "Condition": {
                            "StringEquals": {
                                "sagemaker:InstanceTypes": ["ml.t3.medium", "ml.t3.large"]
                            }
                        }
                    }
                ]
            }
        }
    },
    "DataAnalystRole": {
        "managed_policies": [
            "AmazonAthenaFullAccess",
            "AmazonQuickSightDescribeAccess"
        ],
        "inline_policies": {
            "S3ReadAccess": {
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": ["s3:GetObject", "s3:ListBucket"],
                        "Resource": [
                            "arn:aws:s3:::data-platform-curated-*/*",
                            "arn:aws:s3:::data-platform-processed-*/*"
                        ]
                    }
                ]
            }
        }
    }
}
```

### Service Roles

```python
# Service-specific IAM roles
service_roles = {
    "EMRServiceRole": {
        "trust_relationship": "elasticmapreduce.amazonaws.com",
        "policies": ["AmazonElasticMapReduceRole"]
    },
    "GlueServiceRole": {
        "trust_relationship": "glue.amazonaws.com",
        "policies": ["AWSGlueServiceRole"]
    },
    "LambdaExecutionRole": {
        "trust_relationship": "lambda.amazonaws.com",
        "policies": [
            "AWSLambdaKinesisExecutionRole",
            "CloudWatchLambdaInsightsExecutionRolePolicy"
        ]
    },
    "RedshiftServiceRole": {
        "trust_relationship": "redshift.amazonaws.com",
        "policies": ["AmazonRedshiftServiceLinkedRolePolicy"]
    }
}
```

### Cross-Account Access

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::TRUSTED-ACCOUNT:role/DataAccessRole"
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "sts:ExternalId": "unique-external-id",
          "aws:PrincipalOrgID": "o-organization-id"
        },
        "IpAddress": {
          "aws:SourceIp": ["10.0.0.0/8", "172.16.0.0/12"]
        }
      }
    }
  ]
}
```

## Data Encryption

### Encryption at Rest

```python
# S3 Bucket Encryption
s3_encryption = {
    "BucketEncryption": {
        "ServerSideEncryptionConfiguration": {
            "Rules": [{
                "ApplyServerSideEncryptionByDefault": {
                    "SSEAlgorithm": "aws:kms",
                    "KMSMasterKeyID": "arn:aws:kms:region:account:key/key-id"
                },
                "BucketKeyEnabled": True
            }]
        }
    }
}

# DynamoDB Encryption
dynamodb_encryption = {
    "SSESpecification": {
        "Enabled": True,
        "SSEType": "KMS",
        "KMSMasterKeyId": "alias/data-platform-key"
    }
}

# Redshift Encryption
redshift_encryption = {
    "Encrypted": True,
    "KmsKeyId": "arn:aws:kms:region:account:key/key-id"
}
```

### Encryption in Transit

```python
# TLS Configuration
tls_config = {
    "MinimumProtocolVersion": "TLSv1.2",
    "CipherSuites": [
        "TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256",
        "TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384"
    ],
    "PreferServerCipherSuites": True
}

# VPC Endpoints for Private Communication
vpc_endpoints = {
    "S3": {
        "Type": "Gateway",
        "ServiceName": "com.amazonaws.region.s3"
    },
    "Kinesis": {
        "Type": "Interface",
        "ServiceName": "com.amazonaws.region.kinesis-streams",
        "PrivateDnsEnabled": True
    },
    "DynamoDB": {
        "Type": "Gateway",
        "ServiceName": "com.amazonaws.region.dynamodb"
    }
}
```

### Key Management

```python
# AWS KMS Key Policy
kms_key_policy = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "Enable IAM User Permissions",
            "Effect": "Allow",
            "Principal": {
                "AWS": f"arn:aws:iam::{ACCOUNT_ID}:root"
            },
            "Action": "kms:*",
            "Resource": "*"
        },
        {
            "Sid": "Allow services to use the key",
            "Effect": "Allow",
            "Principal": {
                "Service": [
                    "s3.amazonaws.com",
                    "kinesis.amazonaws.com",
                    "dynamodb.amazonaws.com"
                ]
            },
            "Action": [
                "kms:Decrypt",
                "kms:GenerateDataKey"
            ],
            "Resource": "*"
        },
        {
            "Sid": "Allow attachment of persistent resources",
            "Effect": "Allow",
            "Principal": {
                "AWS": f"arn:aws:iam::{ACCOUNT_ID}:role/DataPlatformRole"
            },
            "Action": [
                "kms:CreateGrant",
                "kms:ListGrants",
                "kms:RevokeGrant"
            ],
            "Resource": "*",
            "Condition": {
                "Bool": {
                    "kms:GrantIsForAWSResource": "true"
                }
            }
        }
    ]
}

# Key Rotation
key_rotation_config = {
    "EnableKeyRotation": True,
    "RotationPeriodInDays": 90
}
```

## Network Security

### VPC Architecture

```python
# VPC Configuration
vpc_config = {
    "CidrBlock": "10.0.0.0/16",
    "EnableDnsHostnames": True,
    "EnableDnsSupport": True,
    "InstanceTenancy": "default"
}

# Subnet Configuration
subnets = {
    "Public": [
        {"CidrBlock": "10.0.1.0/24", "AvailabilityZone": "us-east-1a"},
        {"CidrBlock": "10.0.2.0/24", "AvailabilityZone": "us-east-1b"}
    ],
    "Private": [
        {"CidrBlock": "10.0.10.0/24", "AvailabilityZone": "us-east-1a"},
        {"CidrBlock": "10.0.11.0/24", "AvailabilityZone": "us-east-1b"}
    ],
    "Database": [
        {"CidrBlock": "10.0.20.0/24", "AvailabilityZone": "us-east-1a"},
        {"CidrBlock": "10.0.21.0/24", "AvailabilityZone": "us-east-1b"}
    ]
}
```

### Security Groups

```python
# Security Group Rules
security_groups = {
    "EMRMasterSG": {
        "Ingress": [
            {"Protocol": "tcp", "Port": 22, "Source": "10.0.0.0/16"},
            {"Protocol": "tcp", "Port": 8088, "Source": "10.0.0.0/16"},
            {"Protocol": "tcp", "Port": 18080, "Source": "10.0.0.0/16"}
        ],
        "Egress": [
            {"Protocol": -1, "Port": -1, "Destination": "0.0.0.0/0"}
        ]
    },
    "RedshiftSG": {
        "Ingress": [
            {"Protocol": "tcp", "Port": 5439, "Source": "10.0.10.0/24"}
        ],
        "Egress": [
            {"Protocol": "tcp", "Port": 443, "Destination": "0.0.0.0/0"}
        ]
    },
    "LambdaSG": {
        "Ingress": [],
        "Egress": [
            {"Protocol": -1, "Port": -1, "Destination": "0.0.0.0/0"}
        ]
    }
}
```

### Network ACLs

```python
# Network ACL Rules
nacl_rules = {
    "PublicNACL": {
        "InboundRules": [
            {"RuleNumber": 100, "Protocol": "tcp", "Port": 443, "Allow": True},
            {"RuleNumber": 110, "Protocol": "tcp", "Port": 80, "Allow": True},
            {"RuleNumber": 120, "Protocol": "tcp", "PortRange": "1024-65535", "Allow": True}
        ],
        "OutboundRules": [
            {"RuleNumber": 100, "Protocol": -1, "Allow": True}
        ]
    },
    "PrivateNACL": {
        "InboundRules": [
            {"RuleNumber": 100, "Protocol": -1, "Source": "10.0.0.0/16", "Allow": True}
        ],
        "OutboundRules": [
            {"RuleNumber": 100, "Protocol": -1, "Allow": True}
        ]
    }
}
```

## Data Security

### Data Classification

```python
# Data Classification Levels
data_classification = {
    "PUBLIC": {
        "description": "Public information",
        "encryption": "Optional",
        "access": "Unrestricted",
        "retention": "1 year"
    },
    "INTERNAL": {
        "description": "Internal use only",
        "encryption": "Required",
        "access": "Employees only",
        "retention": "3 years"
    },
    "CONFIDENTIAL": {
        "description": "Confidential business data",
        "encryption": "Required (KMS)",
        "access": "Need-to-know basis",
        "retention": "5 years"
    },
    "RESTRICTED": {
        "description": "Highly sensitive data",
        "encryption": "Required (Customer-managed KMS)",
        "access": "Explicit approval required",
        "retention": "7 years"
    }
}

# Data Tagging
data_tags = {
    "Classification": "CONFIDENTIAL",
    "DataOwner": "data-governance@company.com",
    "Compliance": "GDPR,CCPA",
    "Retention": "5years"
}
```

### Data Masking

```python
# PII Masking Functions
import hashlib
import re

class DataMasking:
    @staticmethod
    def mask_email(email):
        """Mask email address"""
        parts = email.split('@')
        if len(parts) == 2:
            masked = parts[0][:2] + '***@' + parts[1]
            return masked
        return '***'

    @staticmethod
    def mask_ssn(ssn):
        """Mask SSN"""
        return 'XXX-XX-' + ssn[-4:] if len(ssn) >= 4 else 'XXX-XX-XXXX'

    @staticmethod
    def mask_credit_card(cc):
        """Mask credit card"""
        return 'XXXX-XXXX-XXXX-' + cc[-4:] if len(cc) >= 4 else 'XXXX-XXXX-XXXX-XXXX'

    @staticmethod
    def tokenize(value, salt='data-platform'):
        """Tokenize sensitive data"""
        return hashlib.sha256(f"{value}{salt}".encode()).hexdigest()

# Dynamic Data Masking in Redshift
redshift_masking = """
CREATE OR REPLACE FUNCTION mask_pii(input_text VARCHAR)
RETURNS VARCHAR
STABLE
AS $$
    import re

    # Mask SSN
    ssn_pattern = r'\b\d{3}-\d{2}-\d{4}\b'
    text = re.sub(ssn_pattern, 'XXX-XX-XXXX', input_text)

    # Mask email
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    text = re.sub(email_pattern, lambda m: m.group()[:2] + '***@***', text)

    return text
$$ LANGUAGE plpythonu;
"""
```

## Compliance and Auditing

### AWS CloudTrail

```python
# CloudTrail Configuration
cloudtrail_config = {
    "TrailName": "data-platform-audit",
    "S3BucketName": "data-platform-audit-logs",
    "IncludeGlobalServiceEvents": True,
    "IsMultiRegionTrail": True,
    "EnableLogFileValidation": True,
    "EventSelectors": [
        {
            "ReadWriteType": "All",
            "IncludeManagementEvents": True,
            "DataResources": [
                {
                    "Type": "AWS::S3::Object",
                    "Values": ["arn:aws:s3:::data-platform-*/*"]
                },
                {
                    "Type": "AWS::Kinesis::Stream",
                    "Values": ["arn:aws:kinesis:*:*:stream/data-platform-*"]
                }
            ]
        }
    ],
    "InsightSelectors": [
        {"InsightType": "ApiCallRateInsight"}
    ]
}
```

### AWS Config Rules

```python
# Config Rules for Compliance
config_rules = [
    {
        "ConfigRuleName": "s3-bucket-encryption",
        "Source": {
            "Owner": "AWS",
            "SourceIdentifier": "S3_BUCKET_SERVER_SIDE_ENCRYPTION_ENABLED"
        }
    },
    {
        "ConfigRuleName": "rds-encryption",
        "Source": {
            "Owner": "AWS",
            "SourceIdentifier": "RDS_STORAGE_ENCRYPTED"
        }
    },
    {
        "ConfigRuleName": "iam-password-policy",
        "Source": {
            "Owner": "AWS",
            "SourceIdentifier": "IAM_PASSWORD_POLICY"
        }
    },
    {
        "ConfigRuleName": "vpc-flow-logs",
        "Source": {
            "Owner": "AWS",
            "SourceIdentifier": "VPC_FLOW_LOGS_ENABLED"
        }
    }
]
```

### Audit Logging

```python
# Centralized Audit Logging
import json
import boto3
from datetime import datetime

class AuditLogger:
    def __init__(self):
        self.cloudwatch = boto3.client('logs')
        self.log_group = '/aws/data-platform/audit'

    def log_data_access(self, user, resource, action, result):
        """Log data access events"""
        event = {
            'timestamp': datetime.utcnow().isoformat(),
            'event_type': 'DATA_ACCESS',
            'user': user,
            'resource': resource,
            'action': action,
            'result': result,
            'source_ip': self.get_source_ip(),
            'user_agent': self.get_user_agent()
        }

        self.cloudwatch.put_log_events(
            logGroupName=self.log_group,
            logStreamName=f"data-access-{datetime.utcnow().strftime('%Y-%m-%d')}",
            logEvents=[
                {
                    'timestamp': int(datetime.utcnow().timestamp() * 1000),
                    'message': json.dumps(event)
                }
            ]
        )

    def log_configuration_change(self, resource, change_type, details):
        """Log configuration changes"""
        event = {
            'timestamp': datetime.utcnow().isoformat(),
            'event_type': 'CONFIG_CHANGE',
            'resource': resource,
            'change_type': change_type,
            'details': details
        }

        self.cloudwatch.put_log_events(
            logGroupName=self.log_group,
            logStreamName=f"config-changes-{datetime.utcnow().strftime('%Y-%m-%d')}",
            logEvents=[
                {
                    'timestamp': int(datetime.utcnow().timestamp() * 1000),
                    'message': json.dumps(event)
                }
            ]
        )
```

## Security Monitoring

### AWS GuardDuty

```python
# GuardDuty Configuration
guardduty_config = {
    "Enable": True,
    "FindingPublishingFrequency": "FIFTEEN_MINUTES",
    "DataSources": {
        "S3Logs": {"Enable": True},
        "Kubernetes": {"AuditLogs": {"Enable": True}},
        "MalwareProtection": {
            "ScanEc2InstanceWithFindings": {"EbsVolumes": True}
        }
    }
}

# GuardDuty Threat Intel
threat_intel_set = {
    "Name": "custom-threat-list",
    "Format": "TXT",
    "Location": "s3://security-lists/threat-intel.txt",
    "Activate": True
}
```

### Security Hub

```python
# Security Hub Standards
security_standards = [
    "arn:aws:securityhub:::ruleset/cis-aws-foundations-benchmark/v/1.2.0",
    "arn:aws:securityhub:::ruleset/aws-foundational-security-best-practices/v/1.0.0",
    "arn:aws:securityhub:::ruleset/pci-dss/v/3.2.1"
]

# Custom Security Checks
custom_checks = {
    "CheckUnencryptedData": {
        "Severity": "HIGH",
        "Title": "Check for unencrypted sensitive data",
        "Description": "Identifies S3 objects containing sensitive data without encryption"
    },
    "CheckStaleAccessKeys": {
        "Severity": "MEDIUM",
        "Title": "Check for stale access keys",
        "Description": "Identifies IAM access keys not rotated in 90 days"
    }
}
```

## Incident Response

### Incident Response Plan

```python
# Incident Response Automation
class IncidentResponse:
    def __init__(self):
        self.sns = boto3.client('sns')
        self.lambda_client = boto3.client('lambda')

    def handle_security_event(self, event):
        """Automated incident response"""
        severity = self.assess_severity(event)

        if severity == "CRITICAL":
            self.isolate_resource(event['resource'])
            self.notify_security_team(event)
            self.create_snapshot(event['resource'])
            self.invoke_forensics(event)

        elif severity == "HIGH":
            self.notify_security_team(event)
            self.enable_enhanced_monitoring(event['resource'])

        self.log_incident(event)

    def isolate_resource(self, resource_id):
        """Isolate compromised resource"""
        # Remove from security groups
        # Disable IAM access
        # Create forensic snapshot
        pass

    def invoke_forensics(self, event):
        """Trigger forensic analysis"""
        self.lambda_client.invoke(
            FunctionName='forensic-analysis',
            InvocationType='Event',
            Payload=json.dumps(event)
        )
```

## Security Best Practices

1. **Access Control**
   - Use MFA for all human users
   - Rotate credentials regularly
   - Implement just-in-time access

2. **Data Protection**
   - Encrypt everything
   - Implement data loss prevention
   - Regular security assessments

3. **Network Security**
   - Use private subnets
   - Implement WAF rules
   - Enable VPC Flow Logs

4. **Monitoring**
   - Real-time threat detection
   - Automated response
   - Regular security reviews

5. **Compliance**
   - Regular audits
   - Compliance automation
   - Documentation maintenance