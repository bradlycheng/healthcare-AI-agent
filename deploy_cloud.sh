#!/bin/bash
# deploy_cloud.sh - Deploy Healthcare AI Agent to AWS Free Tier (t2.micro)
# Usage: Paste the contents of this file into the "User Data" field when launching an EC2 instance.

set -e

echo "--- Starting Cloud Deployment (Free Tier) ---"

# 1. Update and install basic dependencies
sudo apt-get update -y
sudo apt-get install -y ca-certificates curl gnupg lsb-release git python3-pip

# 2. Install Docker
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update -y
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# 3. Clone Project
cd /home/ubuntu
# NOTE: In a real scenario, you would clone your specific repo. 
# For now, we assume public or auth is handled.
git clone https://github.com/YOUR_GITHUB_USERNAME/healthcare_ai_agent.git
cd healthcare_ai_agent
git checkout feature/aws-bedrock-migration

# 4. Configure Environment (Placeholder - You must edit this on the server!)
# We create a dummy .env so docker-compose doesn't complain, but 
# YOU MUST EDIT IT TO ADD AWS KEYS IF NOT USING IAM ROLE
cp .env.example .env

# 5. Build and Start Stack
# We use the build process on the t2.micro (it might be slow, but it's free)
sudo docker compose build app
sudo docker compose up -d app caddy

echo "--- Setup Complete! Application running on Port 80 ---"
echo "IMPORTANT: Ensure this EC2 instance had an IAM Role with 'AmazonBedrockFullAccess' attached!"
