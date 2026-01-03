#!/bin/bash
# deploy_cloud.sh - Bulletproof AWS Free Tier Deployment
# Usage: Paste into EC2 User Data field
#
# PREREQUISITES:
# - EC2 Instance must have IAM Role with bedrock:InvokeModel permission
# - Bedrock model access must be enabled in AWS Console (us-east-1)

set -e
exec > >(tee /var/log/user-data.log)
exec 2>&1

echo "=== Healthcare AI Agent Cloud Deployment ==="
echo "Started at: $(date)"

# 0. Verify AWS IAM Role is attached
echo "[0/6] Verifying AWS credentials (IAM Role)..."
if ! curl -s -f http://169.254.169.254/latest/meta-data/iam/security-credentials/ > /dev/null; then
    echo "ERROR: No IAM role attached to this EC2 instance!"
    echo "Please attach an IAM role with bedrock:InvokeModel permission."
    exit 1
fi
echo "✓ IAM Role detected"

# 1. Update system
echo "[1/7] Updating system packages..."
sudo apt-get update -y

# 2. Install Docker from Ubuntu repos (more reliable than docker.com)
echo "[2/7] Installing Docker..."
sudo apt-get install -y docker.io docker-compose-v2 git

# Start Docker service
sudo systemctl start docker
sudo systemctl enable docker

# 3. Clone repository
echo "[3/7] Cloning repository..."
cd /home/ubuntu
sudo -u ubuntu git clone https://github.com/bradlycheng/healthcare-Ai-agent.git
cd healthcare-Ai-agent
sudo -u ubuntu git checkout feature/aws-bedrock-migration

# 4. Set up environment
echo "[4/7] Configuring environment..."
sudo -u ubuntu cp .env.example .env

# 5. Build Docker images
echo "[5/7] Building Docker images (this takes 2-3 minutes)..."
sudo docker compose build app

# 6. Start services
echo "[6/7] Starting application..."
sudo docker compose up -d app caddy

echo "=== Deployment Complete ==="
echo "Finished at: $(date)"
echo ""
echo "Your dashboard should be available at: http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4)"
echo ""
echo "To check logs: sudo docker compose logs -f"
