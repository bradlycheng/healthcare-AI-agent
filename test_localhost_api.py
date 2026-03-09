
import requests
import json

def test_localhost_ckd():
    url = "http://localhost:8080/api/query"
    payload = {
        "question": "Which patients should I be worried about?",
        "history": [],
        "reasoning_depth": "fast"
    }
    
    print(f"Testing {url} with question: '{payload['question']}'")
    try:
        response = requests.post(url, json=payload, timeout=30)
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Success: {data.get('success')}")
            print(f"SQL Used: {data.get('sql_used')}")
            print(f"Row Count: {data.get('row_count')}")
            print(f"Answer: {data.get('answer')}")
        else:
            print(f"Error: {response.text}")
    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    test_localhost_ckd()
