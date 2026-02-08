
import asyncio
from app.agent import run_oru_pipeline

hl7_msg = "MSH|^~\\&|HIS|MedCenter|LIS|LAB|202401201200||ORU^R01|MSG_E2E|P|2.5\rPID|1||99999||TEST^E2E||19800101|M\rOBR|1|ORD1|RES1|PANEL1|||202401201200\rOBX|1|NM|GLUCOSE||120|mg/dL|70-100|H|||F"

try:
    print("Running pipeline...")
    result = run_oru_pipeline(hl7_msg, use_llm=True, persist=True)
    print("Success!")
except Exception as e:
    print("Caught exception:")
    import traceback
    traceback.print_exc()
