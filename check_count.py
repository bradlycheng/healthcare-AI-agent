import requests
try:
    resp = requests.get("http://localhost:8080/messages?limit=1", timeout=5)
    print(f"Status: {resp.status_code}")
    data = resp.json()
    print(f"Total Messages: {data.get('total')}")
    print(f"Items in response: {len(data.get('items', []))}")
except Exception as e:
    print(f"Error: {e}")
