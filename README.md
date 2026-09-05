# LangGraph Production Agent on AWS ECS Fargate

A production-ready, asynchronous multi-turn LangGraph calculator agent packaged with FastAPI, Docker, Pulumi Infrastructure as Code (IaC), AWS ECS Fargate (Graviton ARM64), and Langfuse observability.

---

## Architecture Overview

- **FastAPI Service**: Streaming Server-Sent Events (SSE) `/api/v1/chat/stream` with LangGraph `astream` token streaming, correlation ID tracking, and safe AST math evaluation.
- **Observability**: Direct integration with [Langfuse](https://langfuse.com) tracking TTFT (Time To First Token), token counts, and full execution traces.
- **Container**: Multi-stage `Dockerfile` with `uv` and `python:3.12-slim`, producing an ultra-lean 81.3 MB production image running as a non-root `appuser`.
- **Infrastructure as Code (Pulumi)**: Fully reproducible AWS stack using an S3 remote state backend (`s3://abhin-langgraph-pulumi-state-ap-south-1`).
- **Compute**: AWS ECS Fargate running on Graviton ARM64 (`0.25 vCPU / 0.5 GB RAM`) in a public subnet with direct public IP (zero Load Balancer or NAT Gateway costs).

---

## Cost Management ($0 Idle / Low Cost Operations)

To prevent unwanted AWS compute charges, the service can be turned on and off on demand with a single CLI command.

### 1. Scale Down to 0 Tasks (Stop Compute Billing)
Stops the running container and releases the public IPv4 address. Billing drops to **$0.00/hour** immediately:
```bash
aws ecs update-service \
  --cluster langgraph-cluster \
  --service langgraph-agent-service \
  --desired-count 0
```

### 2. Scale Up to 1 Task (Start Compute for Testing)
Spins up a Fargate container, boots the FastAPI service, and assigns a public IP:
```bash
aws ecs update-service \
  --cluster langgraph-cluster \
  --service langgraph-agent-service \
  --desired-count 1
```

### 3. Get the Live Public IP
Once scaled up (takes ~30-45 seconds), retrieve the running task's public IP:
```bash
TASK_ARN=$(aws ecs list-tasks --cluster langgraph-cluster --query "taskArns[0]" --output text)
ENI_ID=$(aws ecs describe-tasks --cluster langgraph-cluster --tasks $TASK_ARN --query "tasks[0].attachments[0].details[?name=='networkInterfaceId'].value" --output text)
PUBLIC_IP=$(aws ec2 describe-network-interfaces --network-interface-ids $ENI_ID --query "NetworkInterfaces[0].Association.PublicIp" --output text)

echo "Live Service URL: http://${PUBLIC_IP}:8000"
```

### 4. Test the Live Service
Health check:
```bash
curl http://${PUBLIC_IP}:8000/health
```

Multi-turn SSE stream calculation:
```bash
curl -N -X POST http://${PUBLIC_IP}:8000/api/v1/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "Calculate (45 * 12) + 180", "session_id": "test-session"}'
```

---

## Local Development & Testing

### 1. Install Dependencies
```bash
uv sync --extra dev
```

### 2. Run Tests
```bash
uv run pytest tests/
```

### 3. Run Locally
```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## Docker Build & ECR Deployment

### 1. Build Local Container (ARM64)
```bash
docker build -t langgraph-agent:latest .
```

### 2. Log in and Push to AWS ECR
```bash
aws ecr get-login-password --region ap-south-1 | docker login --username AWS --password-stdin 422600867909.dkr.ecr.ap-south-1.amazonaws.com
docker tag langgraph-agent:latest 422600867909.dkr.ecr.ap-south-1.amazonaws.com/langgraph-agent:latest
docker push 422600867909.dkr.ecr.ap-south-1.amazonaws.com/langgraph-agent:latest
```

---

## Full Infrastructure Teardown (Pulumi)

If you want to completely destroy all AWS resources (ECR repo, ECS cluster, service, security groups, CloudWatch log groups):
```bash
PULUMI_CONFIG_PASSPHRASE="" pulumi down --yes --cwd infra
```
