# Fresh EC2 Deployment Checklist

## Step 1: Create IAM Role (One-Time Setup)

1. Go to **IAM Console** → **Roles** → **Create role**
2. Select **AWS service** → **EC2** → **Next**
3. Click **Create policy** (opens new tab):
   - Click **JSON** tab
   - Paste this:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [{
       "Effect": "Allow",
       "Action": ["bedrock:InvokeModel"],
       "Resource": "arn:aws:bedrock:us-east-1::foundation-model/meta.llama3-8b-instruct-v1:0"
     }]
   }
   ```
   - Click **Next**
   - Name: `HealthcareAI-Bedrock-Policy`
   - Click **Create policy**
4. Return to role creation tab, refresh policies, search for `HealthcareAI-Bedrock-Policy`, check it
5. Click **Next**
6. Role name: `HealthcareAI-Bedrock-Role`
7. Click **Create role**

---

## Step 2: Enable Bedrock Model Access (One-Time Setup)

1. Go to **Bedrock Console**: https://console.aws.amazon.com/bedrock/
2. Select region: **us-east-1** (top-right dropdown)
3. Click **Model access** (left sidebar)
4. Click **Manage model access**
5. Find **Meta** → Check **Llama 3 8B Instruct**
6. Click **Request model access**
7. Wait for status to show **Access granted** (takes 1-2 minutes)

---

## Step 3: Terminate Old Instance

1. Go to **EC2 Console** → **Instances**
2. Select your old instance (98.92.174.14)
3. **Instance State** → **Terminate instance**
4. Confirm termination

---

## Step 4: Launch New Instance

### Basic Configuration
- Click **Launch instances**
- **Name**: `Healthcare-AI-Agent`
- **AMI**: Ubuntu Server 24.04 LTS (or 22.04 LTS)
- **Instance type**: `t2.micro` (Free Tier)
- **Key pair**: Select existing or create new

### Network Settings
Click **Edit** on Network settings:
- **Auto-assign public IP**: Enable
- **Firewall (security groups)**: Create new
  - Name: `healthcare-ai-sg`
  - Add rules:
    ```
    Rule 1: SSH, Port 22, Source: My IP (for debugging)
    Rule 2: HTTP, Port 80, Source: 0.0.0.0/0 (CRITICAL!)
    ```

### Advanced Details
Scroll down to **Advanced details**:
- **IAM instance profile**: Select `HealthcareAI-Bedrock-Role` ← CRITICAL!
- **User data**: Paste this entire script:

```bash
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
sudo -u ubuntu git clone https://github.com/bradlycheng/healthcare-AI-agent.git
cd healthcare-AI-agent
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
```

### Launch!
- Click **Launch instance**
- Wait for instance to show **Running** (1-2 minutes)

---

## Step 5: Wait and Access

1. **Wait 3-5 minutes** for deployment to complete
2. Copy the **Public IPv4 address** from instance details
3. Visit in browser: `http://<your-public-ip>`

**Expected:**
- Landing page loads immediately
- Dashboard at `http://<your-public-ip>/dashboard.html`
- API docs at `http://<your-public-ip>/docs`

---

## Troubleshooting (If Still Not Working)

SSH into instance:
```bash
ssh -i your-key.pem ubuntu@<your-public-ip>

# Check deployment log
sudo tail -50 /var/log/user-data.log

# Check if you see "Deployment Complete"
# Check containers
cd /home/ubuntu/healthcare-AI-agent
sudo docker compose ps

# Check logs
sudo docker compose logs app
```
