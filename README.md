# Healthcare AI Agent 🏥

An intelligent interoperability agent that parses HL7 v2 ORU messages, standardizes them to FHIR R4, and uses AWS Bedrock to generate clinical summaries with LLMs like Llama 3.

## 🚀 Quick Start

### Prerequisites
1. **AWS Account** with Bedrock access enabled
2. **AWS Credentials configured** (via `aws configure` or IAM role)
3. **Bedrock Model Access**: Enable Llama 3 in [AWS Console](https://console.aws.amazon.com/bedrock/) → Model access

### Local Development
1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
2. **Configure AWS Credentials**:
   ```bash
   aws configure
   # Enter your AWS Access Key ID, Secret Access Key, and set region to us-east-1
   ```
3. **Set Environment Variables** (copy `.env.example` to `.env`)
4. **Run App**:
   ```bash
   uvicorn app.api:app --reload
   ```
   Visit **http://localhost:8000** for the Landing Page and **http://localhost:8000/dashboard.html** for the Dashboard.

### Docker Deployment (Local)
Run the entire application in containers:

```bash
docker compose up -d
```

The app will be available at **http://localhost** (port 80).

### EC2 Deployment (Production)

#### Step 1: Create IAM Role
1. Go to AWS Console → IAM → Roles → Create Role
2. Select "AWS Service" → "EC2"
3. Create a policy with these permissions:
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
4. Name it `HealthcareAI-Bedrock-Role`

#### Step 2: Launch EC2 Instance
1. **AMI**: Ubuntu 22.04 LTS (Free Tier eligible)
2. **Instance Type**: `t2.micro` (Free Tier)
3. **IAM Role**: Attach `HealthcareAI-Bedrock-Role`
4. **Security Group**: Allow HTTP (port 80) from anywhere
5. **User Data**: Copy contents of [`deploy_cloud.sh`](./deploy_cloud.sh)

#### Step 3: Access Application
After 3-5 minutes, visit `http://<your-ec2-public-ip>` to see the dashboard!

---

## 🛠 Features

- **Ingestion**: Parses raw HL7 V2.5.1 ORU^R01 messages.
- **Conversion**: Transforms data into HL7 FHIR R4 Bundles.
- **AI Analysis**: Uses AWS Bedrock (Llama 3) for clinical summaries. Leverages AWS's secure infrastructure.
- **Interactive Dashboard**: Real-time monitoring of processed messages.

## 📁 Project Structure

- `app/`: Backend logic (FastAPI, parsing, AI client).
- `web/`: Frontend assets (Landing page, Dashboard).
- `agent.db`: Consolidated SQLite database (contains all sample data).
- `docker-compose.yml`: Production-ready orchestration.

## 🔒 Security (Demo Note)
For this demo, authentication is **DISABLED** to ensure a smooth viewing experience. If deploying to a public server, re-enable the `authenticate` logic in `app/api.py`.

## ⚙️ Environment Variables
| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_PATH` | `agent.db` | Path to the SQLite DB |
| `AWS_REGION` | `us-east-1` | AWS region for Bedrock |
| `BEDROCK_MODEL_ID` | `meta.llama3-8b-instruct-v1:0` | Bedrock model to use |
| `AUTH_USERNAME` | `admin` | Dashboard username (optional) |
| `AUTH_PASSWORD` | `healthcare2025` | Dashboard password (optional) |

## 💰 Cost Estimate
- **EC2**: Free Tier eligible (t2.micro, 750 hrs/month)
- **Bedrock**: ~$0.0004 per 1000 tokens (~$0.01 per HL7 message)
- **Data Transfer**: Negligible for demo usage

**Estimated monthly cost for demo**: < $5 USD
