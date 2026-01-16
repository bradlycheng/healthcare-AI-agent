import requests
import json

# Test HL7 message with clinical note containing BP values
hl7 = '''MSH|^~\\&|LAB|FACILITY|EHR|FACILITY|20250116||ORU^R01|12345|P|2.5
PID|1||99001^^^MRN||SMITH^JOHN||19800515|M
OBR|1|||CBC|||20250116090000
OBX|1|NM|718-7^HEMOGLOBIN||14.2|g/dL|13.5-17.5|N|||F
NTE|1||Patient reports fasting glucose of 145 mg/dL. BP 138/88 mmHg.'''

response = requests.post(
    'http://localhost:8001/oru/parse',
    json={'hl7_text': hl7, 'use_llm': True, 'persist': False}
)

result = response.json()
fhir = result.get('fhir_bundle', {})

print('=== FHIR Bundle Observations ===')
for entry in fhir.get('entry', []):
    res = entry.get('resource', {})
    if res.get('resourceType') == 'Observation':
        code_info = res.get('code', {}).get('coding', [{}])[0]
        value_qty = res.get('valueQuantity', {})
        print(f"Display: {code_info.get('display')}")
        print(f"  Code: {code_info.get('code')}")
        print(f"  Value: {value_qty.get('value')} {value_qty.get('unit')}")
        print()
