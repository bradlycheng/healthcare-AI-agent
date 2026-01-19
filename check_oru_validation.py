import requests

API_URL = "http://localhost:8080/oru/parse"

adt_message = (
    "MSH|^~\\&|SEND|FAC|REC|FAC|20230101||ADT^A01|MSGID|P|2.5.1\r"
    "PID|1||12345||DOE^JOHN||19800101|M"
)

try:
    print(f"Sending ADT message...")
    resp = requests.post(API_URL, json={"hl7_text": adt_message, "use_llm": False, "persist": False})
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.text}")
    
    if resp.status_code == 400 and "Expected ORU" in resp.text:
        print("✅ SUCCESS: ADT message rejected as expected.")
    else:
        print("❌ FAILURE: Message was not rejected correctly.")

except Exception as e:
    print(e)
