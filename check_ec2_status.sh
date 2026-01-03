#!/bin/bash
# Quick EC2 deployment status checker
# Run this on your EC2 instance after SSH'ing in

echo "=== EC2 Deployment Status Check ==="
echo ""

# Check if deployment script ran
echo "[1/5] Checking if user-data script ran..."
if [ -f /var/log/user-data.log ]; then
    echo "✓ User data log exists"
    tail -20 /var/log/user-data.log
else
    echo "✗ No user-data log found - script may not have run!"
fi

echo ""
echo "[2/5] Checking Docker installation..."
if command -v docker &> /dev/null; then
    echo "✓ Docker is installed"
    docker --version
else
    echo "✗ Docker not installed"
fi

echo ""
echo "[3/5] Checking if repository was cloned..."
if [ -d /home/ubuntu/healthcare-AI-agent ]; then
    echo "✓ Repository cloned"
    cd /home/ubuntu/healthcare-AI-agent
    git branch
else
    echo "✗ Repository not found"
fi

echo ""
echo "[4/5] Checking Docker containers..."
cd /home/ubuntu/healthcare-AI-agent 2>/dev/null
sudo docker compose ps 2>/dev/null || echo "No containers running"

echo ""
echo "[5/5] Checking if port 80 is listening..."
if sudo netstat -tlnp | grep :80; then
    echo "✓ Something is listening on port 80"
else
    echo "✗ Nothing listening on port 80!"
fi

echo ""
echo "=== Container Logs (if available) ==="
cd /home/ubuntu/healthcare-AI-agent 2>/dev/null
sudo docker compose logs --tail=30 2>/dev/null || echo "No logs available"
