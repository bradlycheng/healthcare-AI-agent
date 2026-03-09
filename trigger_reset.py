
import requests
import json

def reset_demo():
    url = "http://localhost:8080/admin/reset"
    payload = {"password": "d3m0th1s"}
    headers = {"Content-Type": "application/json"}
    
    try:
        response = requests.post(url, data=json.dumps(payload), headers=headers)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    reset_demo()
