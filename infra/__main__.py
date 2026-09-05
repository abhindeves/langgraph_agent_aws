import json
import pulumi
import pulumi_aws as aws

config = pulumi.Config()
aws_config = pulumi.Config("aws")
region = aws_config.get("region") or "ap-south-1"

# Secrets & Config
openai_api_key = config.require_secret("openai_api_key")
langfuse_secret_key = config.require_secret("langfuse_secret_key")
langfuse_public_key = config.get("langfuse_public_key") or ""
langfuse_base_url = config.get("langfuse_base_url") or "https://jp.cloud.langfuse.com"

# ==============================================================================
# Stage 5: ECR Repository
# ==============================================================================
ecr_repo = aws.ecr.Repository(
    "langgraph-agent-repo",
    name="langgraph-agent",
    image_tag_mutability="MUTABLE",
    force_delete=True,
    image_scanning_configuration=aws.ecr.RepositoryImageScanningConfigurationArgs(
        scan_on_push=True,
    ),
    tags={
        "Project": "LangGraphAgent",
        "Environment": pulumi.get_stack(),
    },
)

# Keep only last 3 images to prevent storage costs
ecr_lifecycle = aws.ecr.LifecyclePolicy(
    "langgraph-agent-lifecycle",
    repository=ecr_repo.name,
    policy="""{
        "rules": [
            {
                "rulePriority": 1,
                "description": "Keep only last 3 images to save cost",
                "selection": {
                    "tagStatus": "any",
                    "countType": "imageCountMoreThan",
                    "countNumber": 3
                },
                "action": {
                    "type": "expire"
                }
            }
        ]
    }""",
)

# ==============================================================================
# Stage 6: CloudWatch Logs, Security Group & IAM Roles
# ==============================================================================

# 1. CloudWatch Log Group with 3-day retention (Cost Control)
log_group = aws.cloudwatch.LogGroup(
    "ecs-log-group",
    name="/ecs/langgraph-agent",
    retention_in_days=3,
    tags={
        "Project": "LangGraphAgent",
        "Environment": pulumi.get_stack(),
    },
)

# 2. Get Default VPC & Public Subnets
default_vpc = aws.ec2.get_vpc(default=True)
public_subnets = aws.ec2.get_subnets(
    filters=[
        aws.ec2.GetSubnetsFilterArgs(
            name="vpc-id",
            values=[default_vpc.id],
        ),
        aws.ec2.GetSubnetsFilterArgs(
            name="default-for-az",
            values=["true"],
        ),
    ]
)

# 3. Security Group for FastAPI (Port 8000 inbound, all outbound)
security_group = aws.ec2.SecurityGroup(
    "ecs-security-group",
    name="langgraph-agent-sg",
    description="Security group for LangGraph FastAPI agent on ECS Fargate",
    vpc_id=default_vpc.id,
    ingress=[
        aws.ec2.SecurityGroupIngressArgs(
            protocol="tcp",
            from_port=8000,
            to_port=8000,
            cidr_blocks=["0.0.0.0/0"],
            description="FastAPI service port",
        ),
    ],
    egress=[
        aws.ec2.SecurityGroupEgressArgs(
            protocol="-1",
            from_port=0,
            to_port=0,
            cidr_blocks=["0.0.0.0/0"],
            description="Allow all outbound traffic for OpenAI API and Langfuse",
        ),
    ],
    tags={
        "Project": "LangGraphAgent",
        "Environment": pulumi.get_stack(),
    },
)

# 4. IAM Task Execution Role (allows Fargate to pull from ECR and push logs to CloudWatch)
task_execution_role = aws.iam.Role(
    "ecs-task-execution-role",
    name="langgraph-agent-ecs-execution-role",
    assume_role_policy=json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Action": "sts:AssumeRole",
            "Effect": "Allow",
            "Principal": {
                "Service": "ecs-tasks.amazonaws.com"
            }
        }]
    }),
    tags={
        "Project": "LangGraphAgent",
        "Environment": pulumi.get_stack(),
    },
)

aws.iam.RolePolicyAttachment(
    "ecs-task-execution-role-policy",
    role=task_execution_role.name,
    policy_arn="arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy",
)

# 5. IAM Task Role (runtime role for the container itself)
task_role = aws.iam.Role(
    "ecs-task-role",
    name="langgraph-agent-ecs-task-role",
    assume_role_policy=json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Action": "sts:AssumeRole",
            "Effect": "Allow",
            "Principal": {
                "Service": "ecs-tasks.amazonaws.com"
            }
        }]
    }),
    tags={
        "Project": "LangGraphAgent",
        "Environment": pulumi.get_stack(),
    },
)

# ==============================================================================
# Stage 7: ECS Cluster, Fargate Task Definition & Service (0.25 vCPU / 0.5 GB ARM64)
# ==============================================================================

# 1. ECS Cluster
ecs_cluster = aws.ecs.Cluster(
    "langgraph-cluster",
    name="langgraph-cluster",
    tags={
        "Project": "LangGraphAgent",
        "Environment": pulumi.get_stack(),
    },
)

# 2. Fargate Task Definition
# Uses 0.25 vCPU (256 units) and 0.5 GB RAM (512 MB) on Graviton ARM64
container_definition = pulumi.Output.all(
    ecr_repo.repository_url,
    log_group.name,
    openai_api_key,
    langfuse_secret_key,
).apply(
    lambda args: json.dumps([{
        "name": "langgraph-agent",
        "image": f"{args[0]}:latest",
        "essential": True,
        "portMappings": [{
            "containerPort": 8000,
            "hostPort": 8000,
            "protocol": "tcp",
        }],
        "environment": [
            {"name": "PORT", "value": "8000"},
            {"name": "ENVIRONMENT", "value": "production"},
            {"name": "MODEL_NAME", "value": "gpt-4o-mini"},
            {"name": "LANGFUSE_PUBLIC_KEY", "value": langfuse_public_key},
            {"name": "LANGFUSE_BASE_URL", "value": langfuse_base_url},
            {"name": "OPENAI_API_KEY", "value": args[2]},
            {"name": "LANGFUSE_SECRET_KEY", "value": args[3]},
        ],
        "logConfiguration": {
            "logDriver": "awslogs",
            "options": {
                "awslogs-group": args[1],
                "awslogs-region": region,
                "awslogs-stream-prefix": "ecs",
            },
        },
    }])
)

task_definition = aws.ecs.TaskDefinition(
    "langgraph-agent-task",
    family="langgraph-agent",
    cpu="256",          # 0.25 vCPU
    memory="512",       # 0.5 GB RAM
    network_mode="awsvpc",
    requires_compatibilities=["FARGATE"],
    execution_role_arn=task_execution_role.arn,
    task_role_arn=task_role.arn,
    runtime_platform=aws.ecs.TaskDefinitionRuntimePlatformArgs(
        cpu_architecture="ARM64",     # Graviton ARM64 matches our M-series build
        operating_system_family="LINUX",
    ),
    container_definitions=container_definition,
    tags={
        "Project": "LangGraphAgent",
        "Environment": pulumi.get_stack(),
    },
)

# 3. ECS Fargate Service (Runs 1 task in public subnet, assigned public IP, no ALB)
ecs_service = aws.ecs.Service(
    "langgraph-agent-service",
    name="langgraph-agent-service",
    cluster=ecs_cluster.arn,
    task_definition=task_definition.arn,
    launch_type="FARGATE",
    desired_count=1,
    network_configuration=aws.ecs.ServiceNetworkConfigurationArgs(
        subnets=public_subnets.ids,
        security_groups=[security_group.id],
        assign_public_ip=True,
    ),
    opts=pulumi.ResourceOptions(depends_on=[task_execution_role]),
    tags={
        "Project": "LangGraphAgent",
        "Environment": pulumi.get_stack(),
    },
)

# Exports
pulumi.export("ecr_repository_url", ecr_repo.repository_url)
pulumi.export("ecs_cluster_name", ecs_cluster.name)
pulumi.export("ecs_service_name", ecs_service.name)
pulumi.export("security_group_id", security_group.id)
pulumi.export("log_group_name", log_group.name)
