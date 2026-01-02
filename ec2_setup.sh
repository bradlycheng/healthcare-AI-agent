#!/bin/bash
# ec2_setup.sh - AWS User Data Script for Healthcare AI Agent
# Best used with: Ubuntu 22.04 LTS on g4dn.xlarge

set -e

echo "--- Starting EC2 Setup ---"

# 1. Update and install basic dependencies
sudo apt-get update -y
sudo apt-get install -y ca-certificates curl gnupg lsb-release git

# 2. Install Docker
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update -y
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# 3. Install NVIDIA Container Toolkit (Requirement for Ollama GPU support)
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg \
  && curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
    sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit

# Configure Docker to use NVIDIA
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker

# 4. Clone Project (Optional: You can also use ECR, but cloning is easier for a first demo)
cd /home/ubuntu
git clone https://github.com/YOUR_GITHUB_USERNAME/healthcare_ai_agent.git
cd healthcare_ai_agent

# 5. Build and Start Stack
sudo docker compose up -d

# 6. Pre-pull the LLM within the container
# We wait a few seconds for Ollama to be ready
sleep 30
sudo docker exec healthcare_ai_agent-ollama-1 ollama pull llama3.2:3b

echo "--- Setup Complete! Dashboard should be live on port 80 ---"
