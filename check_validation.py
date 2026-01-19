import requests
try:
    resp = requests.post("http://localhost:8080/oru/parse", json={"hl7_text": "GARBAGE_TEXT", "use_llm": False, "persist": False})
    print(f"Status: {resp.status_code}")
    print(resp.text)
except Exception as e:
    print(e)
