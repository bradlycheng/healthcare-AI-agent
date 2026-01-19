import requests
import json
import sys

API_URL = "http://localhost:8080/oru/parse"

valid_msg = (
    "MSH|^~\\&|SEND|FAC|REC|FAC|20230101||ORU^R01|MSGID|P|2.5.1\r"
    "PID|1||12345||DOE^JOHN||19800101|M\r"
    "OBR|1|||BASIC_PANEL\r"
    "OBX|1|NM|GLU^Glucose||100|mg/dL|70-110|N|||F"
)

try:
    print(f"Sending VALID ORU message...")
    resp = requests.post(API_URL, json={"hl7_text": valid_msg, "use_llm": False, "persist": False})
    
    if resp.status_code == 200:
        data = resp.json()
        ack = data.get("hl7_ack", "")
        print(f"SUCCESS (200)")
        print(f"ACK: {ack}") 
    else:
        print(f"FAILED: {resp.status_code}")
        print(resp.text)

except Exception as e:
    print(e)
