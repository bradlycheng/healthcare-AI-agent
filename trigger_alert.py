import requests
import sys

URL = "http://localhost:8080/oru/parse"
DATA = """MSH|^~\&|LAB|LAB|HOSP|HOSP|20250123120000||ORU^R01|MSG-TEST|P|2.5
PID|1||TROP-TEST||DANGER^DAVID||19800101|M
OBR|1|||CARD-PANEL
OBX|1|NM|49563-0^Troponin I^LN||0.15|ng/mL|0.00-0.04|H|||F
OBX|2|TX|NOTE^Clinical Note||CRITICAL: Myocardial Infarction indicated.||||||F"""

try:
    print(f"Sending request to {URL}...")
    resp = requests.post(URL, json={"hl7_text": DATA, "persist": True})
    print(f"Status: {resp.status_code}")
    if resp.status_code == 200:
        print("SUCCESS: Alert Triggered")
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)
