#!/bin/bash
# ec2_setup.sh - AWS User Data Script for Healthcare AI Agent
# This script is designed for Ubuntu 22.04 LTS on t2.micro (Free Tier)
#
# PREREQUISITES:
# 1. EC2 Instance IAM Role with bedrock:InvokeModel permission
# 2. Enable Bedrock model access in AWS Console (us-east-1)
# 3. Repository must be public OR use GitHub deploy keys

set -e

echo "--- Starting EC2 Setup for Healthcare AI Agent ---"
echo "Started at: $(date)"

# 1. Update system packages
echo "[1/5] Updating system packages..."
sudo apt-get update -y

# 2. Install Docker (using Ubuntu's docker.io for simplicity)
echo "[2/5] Installing Docker..."
sudo apt-get install -y docker.io docker-compose-v2 git

# Start and enable Docker service
sudo systemctl start docker
sudo systemctl enable docker

# 3. Clone repository
echo "[3/5] Cloning repository..."
cd /home/ubuntu
sudo -u ubuntu git clone https://github.com/bradlycheng/healthcare-AI-agent.git
cd healthcare-AI-agent
sudo -u ubuntu git checkout feature/aws-bedrock-migration

# 4. Set up environment
echo "[4/5] Configuring environment..."
sudo -u ubuntu cp .env.example .env

# NOTE: AWS credentials are automatically provided via EC2 IAM Role
# No need to configure AWS_ACCESS_KEY_ID or AWS_SECRET_ACCESS_KEY

# 5. Build and start services
echo "[5/5] Building Docker images and starting application..."
sudo docker compose build app
sudo docker compose up -d app caddy

echo ""
echo "=== Deployment Complete ==="
echo "Finished at: $(date)"
echo ""
echo "Your dashboard should be available at: http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4)"
echo ""
echo "To check logs: cd /home/ubuntu/healthcare-AI-agent && sudo docker compose logs -f"
echo "To restart: sudo docker compose restart"
