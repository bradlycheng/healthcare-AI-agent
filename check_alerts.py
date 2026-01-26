"""Check latest message for alerts"""
import requests
import json

resp = requests.get("http://localhost:8080/messages?limit=1")
items = resp.json().get("items", [])
if items:
    msg_id = items[0]['id']
    print(f"Message ID: {msg_id}")
    
    # Fetch observations
    r2 = requests.get(f"http://localhost:8080/messages/{msg_id}/observations")
    obs = r2.json().get("items", [])
    
    for o in obs:
        print(f"Code: '{o.get('code')}' | Display: '{o.get('display')}' | Value: {o.get('value')} | Alert: '{o.get('alert_level')}'")
else:
    print("No messages found.")
