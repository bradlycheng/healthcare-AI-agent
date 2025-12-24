import requests
import json

url = "http://localhost:8080/oru/parse"
hl7_data = """MSH|^~\\&|HIS|MedCenter|LIS|LocalLab|202405021000||ORU^R01|MSG1001|P|2.3
PID|1||123456^^^MRN||DOE^JOHN||19800101|M
OBR|1|||BASIC_PANEL
OBX|1|NM|GLU^Glucose||105|mg/dL|70-100|H|||F"""

payload = {"hl7_text": hl7_data}

try:
    response = requests.post(url, json=payload)
    response.raise_for_status()
    print("Status Code:", response.status_code)
    print("Response JSON:")
    print(json.dumps(response.json(), indent=2))
except Exception as e:
    print(f"Error: {e}")
    if hasattr(e, 'response') and e.response:
        print(e.response.text)
