from typing import Dict, Any, Optional

# Clinical Rules Definition
# code: { limit, op, msg, level }
CLINICAL_RULES = {
    # Troponin I (Cardiac)
    '49563-0': {
        'limit': 0.04, 
        'op': '>', 
        'msg': 'CRITICAL: Elevated Troponin - Possible Myocardial Infarction',
        'level': 'CRITICAL'
    },
    # Glucose (Metabolic)
    '2345-7': {
        'limit': 140, 
        'op': '>', 
        'msg': 'High Glucose - Hyperglycemia',
        'level': 'WARNING'
    },
    '2339-0': { # Alternative Glucose Code
        'limit': 140, 
        'op': '>', 
        'msg': 'High Glucose - Hyperglycemia',
        'level': 'WARNING'
    },
    # Potassium (Electrolytes)
    '6298-4': {
        'limit': 5.5,
        'op': '>',
        'msg': 'High Potassium - Hyperkalemia Risk',
        'level': 'CRITICAL'
    }
}

def check_alert(code: str, value: Any) -> Optional[Dict[str, str]]:
    """
    Evaluate a lab result against clinical rules.
    Returns a dict with alert details if triggered, else None.
    """
    if code not in CLINICAL_RULES:
        return None
        
    rule = CLINICAL_RULES[code]
    print(f"DEBUG ALERT CHECK: Code={code}, Value={value}, Rule={rule}", flush=True)
    
    try:
        # Convert to float for comparison if it's a number
        val_float = float(value)
        
        limit = rule['limit']
        operator = rule['op']
        
        triggered = False
        if operator == '>' and val_float > limit:
            triggered = True
        elif operator == '<' and val_float < limit:
            triggered = True
            
        if triggered:
            return {
                'message': rule['msg'],
                'level': rule['level'],
                'code': code
            }
            
    except (ValueError, TypeError):
        # Value wasn't a number, skip quantitative check
        pass
        
    return None
