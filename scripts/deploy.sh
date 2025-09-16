#!/bin/bash

# AWS Data Platform Deployment Script
# Usage: ./deploy.sh [--stack STACK_NAME] [--environment ENV] [--all] [--destroy]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default values
ENVIRONMENT="dev"
STACK=""
ALL=false
DESTROY=false
PROFILE=""

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --stack)
            STACK="$2"
            shift 2
            ;;
        --environment)
            ENVIRONMENT="$2"
            shift 2
            ;;
        --all)
            ALL=true
            shift
            ;;
        --destroy)
            DESTROY=true
            shift
            ;;
        --profile)
            PROFILE="$2"
            shift 2
            ;;
        --help)
            echo "Usage: $0 [--stack STACK_NAME] [--environment ENV] [--all] [--destroy] [--profile AWS_PROFILE]"
            echo ""
            echo "Options:"
            echo "  --stack         Deploy specific stack (vpc, streaming, batch, storage, ml, monitoring)"
            echo "  --environment   Environment to deploy (dev, staging, prod). Default: dev"
            echo "  --all          Deploy all stacks"
            echo "  --destroy      Destroy stacks instead of deploying"
            echo "  --profile      AWS profile to use"
            echo "  --help         Show this help message"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

# Validate environment
if [[ ! "$ENVIRONMENT" =~ ^(dev|staging|prod)$ ]]; then
    echo -e "${RED}Invalid environment: $ENVIRONMENT. Must be dev, staging, or prod${NC}"
    exit 1
fi

# Set AWS profile if specified
if [ ! -z "$PROFILE" ]; then
    export AWS_PROFILE=$PROFILE
    echo -e "${YELLOW}Using AWS Profile: $AWS_PROFILE${NC}"
fi

# Load environment variables
ENV_FILE=".env.$ENVIRONMENT"
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${YELLOW}Warning: $ENV_FILE not found. Using .env.example as template${NC}"
    cp .env.example "$ENV_FILE"
    echo -e "${YELLOW}Please edit $ENV_FILE with your configuration${NC}"
    exit 1
fi

# Source environment variables
set -a
source "$ENV_FILE"
set +a

# Bootstrap CDK if needed
echo -e "${GREEN}Checking CDK bootstrap status...${NC}"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION=${AWS_REGION:-us-east-1}

if ! aws cloudformation describe-stacks --stack-name CDKToolkit --region $REGION &> /dev/null; then
    echo -e "${YELLOW}Bootstrapping CDK...${NC}"
    cdk bootstrap aws://$ACCOUNT_ID/$REGION
fi

# Function to deploy a stack
deploy_stack() {
    local stack_name=$1
    local full_stack_name="DataPlatform-${ENVIRONMENT}-${stack_name}"

    if [ "$DESTROY" = true ]; then
        echo -e "${YELLOW}Destroying stack: $full_stack_name${NC}"
        cdk destroy "$full_stack_name" --force
    else
        echo -e "${GREEN}Deploying stack: $full_stack_name${NC}"
        cdk deploy "$full_stack_name" --require-approval never
    fi
}

# Function to run pre-deployment checks
pre_deployment_checks() {
    echo -e "${GREEN}Running pre-deployment checks...${NC}"

    # Check Python version
    python_version=$(python3 --version | cut -d' ' -f2)
    if [[ ! "$python_version" > "3.8" ]]; then
        echo -e "${RED}Python 3.9+ is required. Current version: $python_version${NC}"
        exit 1
    fi

    # Check AWS credentials
    if ! aws sts get-caller-identity &> /dev/null; then
        echo -e "${RED}AWS credentials not configured${NC}"
        exit 1
    fi

    # Check CDK installation
    if ! command -v cdk &> /dev/null; then
        echo -e "${RED}AWS CDK is not installed. Install with: npm install -g aws-cdk${NC}"
        exit 1
    fi

    # Install Python dependencies
    if [ ! -d ".venv" ]; then
        echo -e "${YELLOW}Creating virtual environment...${NC}"
        python3 -m venv .venv
    fi

    source .venv/bin/activate
    echo -e "${YELLOW}Installing dependencies...${NC}"
    pip install -q -r requirements.txt

    echo -e "${GREEN}Pre-deployment checks passed!${NC}"
}

# Function to create S3 buckets for logs and scripts
create_s3_buckets() {
    echo -e "${GREEN}Creating S3 buckets...${NC}"

    buckets=(
        "data-platform-logs-${ENVIRONMENT}"
        "data-platform-scripts-${ENVIRONMENT}"
        "data-platform-raw-${ENVIRONMENT}"
        "data-platform-processed-${ENVIRONMENT}"
        "data-platform-curated-${ENVIRONMENT}"
    )

    for bucket in "${buckets[@]}"; do
        if aws s3api head-bucket --bucket "$bucket" 2>/dev/null; then
            echo -e "${YELLOW}Bucket $bucket already exists${NC}"
        else
            echo -e "${GREEN}Creating bucket: $bucket${NC}"
            if [ "$REGION" = "us-east-1" ]; then
                aws s3api create-bucket --bucket "$bucket" --region "$REGION"
            else
                aws s3api create-bucket --bucket "$bucket" --region "$REGION" \
                    --create-bucket-configuration LocationConstraint="$REGION"
            fi

            # Enable versioning for critical buckets
            if [[ "$bucket" == *"curated"* ]] || [[ "$bucket" == *"processed"* ]]; then
                aws s3api put-bucket-versioning --bucket "$bucket" \
                    --versioning-configuration Status=Enabled
            fi

            # Enable encryption
            aws s3api put-bucket-encryption --bucket "$bucket" \
                --server-side-encryption-configuration '{
                    "Rules": [{
                        "ApplyServerSideEncryptionByDefault": {
                            "SSEAlgorithm": "AES256"
                        }
                    }]
                }'
        fi
    done
}

# Function to upload bootstrap scripts
upload_bootstrap_scripts() {
    echo -e "${GREEN}Uploading bootstrap scripts...${NC}"

    # Create bootstrap script
    cat > /tmp/install_packages.sh << 'EOF'
#!/bin/bash
sudo pip3 install pandas numpy scikit-learn pyarrow boto3 awswrangler
sudo yum install -y htop tmux
EOF

    # Upload to S3
    aws s3 cp /tmp/install_packages.sh "s3://data-platform-scripts-${ENVIRONMENT}/bootstrap/install_packages.sh"
}

# Stack deployment order (dependencies matter!)
STACK_ORDER=(
    "VPC"
    "S3"
    "DynamoDB"
    "Kinesis"
    "Lambda"
    "Redshift"
    "EMR"
    "Glue"
    "Athena"
    "SageMaker"
    "FeatureStore"
    "QuickSight"
    "CloudWatch"
    "LakeFormation"
)

# Main execution
echo -e "${GREEN}===========================================${NC}"
echo -e "${GREEN}   AWS Data Platform Deployment Script     ${NC}"
echo -e "${GREEN}===========================================${NC}"
echo -e "${YELLOW}Environment: $ENVIRONMENT${NC}"
echo -e "${YELLOW}Account: $ACCOUNT_ID${NC}"
echo -e "${YELLOW}Region: $REGION${NC}"
echo ""

# Run pre-deployment checks
pre_deployment_checks

# Create S3 buckets if deploying
if [ "$DESTROY" = false ]; then
    create_s3_buckets
    upload_bootstrap_scripts
fi

# Deploy or destroy stacks
if [ "$ALL" = true ]; then
    echo -e "${GREEN}Deploying all stacks...${NC}"
    for stack in "${STACK_ORDER[@]}"; do
        deploy_stack "$stack"
    done
elif [ ! -z "$STACK" ]; then
    # Deploy specific stack
    case "$STACK" in
        vpc)
            deploy_stack "VPC"
            ;;
        streaming)
            deploy_stack "Kinesis"
            deploy_stack "Lambda"
            ;;
        batch)
            deploy_stack "EMR"
            deploy_stack "Glue"
            deploy_stack "Athena"
            ;;
        storage)
            deploy_stack "S3"
            deploy_stack "DynamoDB"
            deploy_stack "Redshift"
            ;;
        ml)
            deploy_stack "SageMaker"
            deploy_stack "FeatureStore"
            ;;
        monitoring)
            deploy_stack "CloudWatch"
            ;;
        *)
            echo -e "${RED}Unknown stack: $STACK${NC}"
            exit 1
            ;;
    esac
else
    echo -e "${RED}Please specify --stack STACK_NAME or --all${NC}"
    exit 1
fi

# Post-deployment actions
if [ "$DESTROY" = false ]; then
    echo ""
    echo -e "${GREEN}===========================================${NC}"
    echo -e "${GREEN}        Deployment Complete!                ${NC}"
    echo -e "${GREEN}===========================================${NC}"
    echo ""
    echo -e "${YELLOW}Next steps:${NC}"
    echo "1. Access EMR cluster UI: https://console.aws.amazon.com/emr"
    echo "2. View CloudWatch dashboards: https://console.aws.amazon.com/cloudwatch"
    echo "3. Configure QuickSight: https://quicksight.aws.amazon.com"
    echo "4. Check Glue Data Catalog: https://console.aws.amazon.com/glue"
    echo ""
    echo -e "${GREEN}To test the deployment:${NC}"
    echo "  pytest tests/integration/test_deployment.py"
else
    echo -e "${GREEN}Stack destruction complete${NC}"
fi