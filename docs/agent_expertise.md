# Agent Expertise: Critical Rules & Use Cases

## Expert Refinement of Critical Rules

The current rules focus on *finding* data. Expert rules should focus on *clinical synthesis* and *safety*.

### 1. The "Data Primacy" Rule
> **Current:** "If query_database returns rows, those ARE the medical data."
> **Expert Refinement:** "Treat tool results as the *ground truth* for the patient's current state. Do not invent data, but do not ignore 'null' or 'missing' values—report them as gaps in the record."

### 2. The "Risk Stratification" Rule
> **Current:** "You MUST list these patients and their specific values."
> **Expert Refinement:** "When identifying risk, prioritize by clinical acuity. Group findings into:
> - **Critical/Emergency**: Immediate threat (e.g., SpO2 < 90%, active chest pain).
> - **Urgent/Abnormal**: Require attention (e.g., BP 160/100, High Glucose).
> - **Watch List**: Borderline values or trending deterioration.
> Always explicitly state *why* a value is concerning (e.g., 'HR 125 suggests tachycardia')."

### 3. The "Contextual Trace" Rule
> **New Rule:** "Never present a value in isolation if history is available.
> - **Bad:** 'BP is 140/90.'
> - **Good:** 'BP is 140/90, which is elevated compared to baseline of 120/80 from last month.'
> Context (trends, baselines, medication changes) turns *data* into *information*."

---

## Supported Scenarios (with Sample Data)

Based on the `seed_realistic_data.py`, the following scenarios are fully supported:

### 1. Chronic Disease Management (Diabetes & Hypertension)
**Data Available:** 
- Conditions: Diabetes, Hypertension, Hyperlipidemia, CKD.
- Labs: Glucose, A1c, Lipid Panel, Creatinine, eGFR.
- Meds: Metformin, Lisinopril, Atorvastatin.
**Query:** "Show me all diabetic patients with A1c > 9."
**Status:** ✅ Fully Supported

### 2. Vitals Monitoring (Risk Stratification)
**Data Available:** 
- Vitals: Heart Rate, BP, SpO2, Temp, RR.
- Logic: Abnormal flags (H/L) generated in seed data.
**Query:** "Which patients have critical vitals (HR > 120 or SpO2 < 90)?"
**Status:** ✅ Fully Supported

### 3. Procedure/Visit History (Limited)
**Data Available:** 
- Visits: "Routine Follow-up", "Outpatient".
- Providers: "Dr. Alice Chen", "Dr. Bob Smith", etc.
**Query:** "Show me all patients seen by Dr. Chen yesterday."
**Status:** ✅ Supported (but limited visit types)

### 4. Kidney Function Tracking (CKD)
**Data Available:** 
- Labs: Creatinine, BUN, eGFR.
- Diagnosis: "Chronic kidney disease, stage 3".
**Query:** "List patients with eGFR < 60."
**Status:** ✅ Supported

