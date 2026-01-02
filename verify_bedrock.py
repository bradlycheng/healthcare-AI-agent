import boto3
import json
import os
from botocore.exceptions import ClientError

# Configuration
REGION = "us-east-1"
MODEL_ID = "meta.llama3-8b-instruct-v1:0"

def test_bedrock_connection():
    print(f"--- Testing Connection to AWS Bedrock ({REGION}) ---")
    print(f"Model ID: {MODEL_ID}")
    
    # 1. Initialize Client
    try:
        bedrock = boto3.client(service_name="bedrock-runtime", region_name=REGION)
        print("[OK] AWS Bedrock Client initialized successfully.")
    except Exception as e:
        print(f"[FAIL] Failed to initialize client: {e}")
        return

    # 2. Test Model Inference
    prompt = "Hello! Are you working? Reply with 'Yes, I am online.'"
    
    # Llama 3 payload format
    payload = {
        "prompt": f"<|begin_of_text|><|start_header_id|>user<|end_header_id|>\n\n{prompt}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n",
        "max_gen_len": 50,
        "temperature": 0.1
    }

    try:
        print("Sending test request to model...")
        response = bedrock.invoke_model(
            modelId=MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(payload)
        )
        
        response_body = json.loads(response.get("body").read())
        generation = response_body.get("generation", "").strip()
        
        print("\n[OK] Model Response Received:")
        print(f"\"{generation}\"")
        print("\n--- Verification Passed! ---")
        
    except ClientError as e:
        print(f"\n[FAIL] AWS Error: {e}")
        print("Tip: Check if 'AmazonBedrockFullAccess' is enabled for your user/role.")
        print(f"Tip: Check if the model '{MODEL_ID}' is enabled in the Bedrock Console.")
    except Exception as e:
        print(f"\n[FAIL] Unexpected Error: {e}")

if __name__ == "__main__":
    test_bedrock_connection()
