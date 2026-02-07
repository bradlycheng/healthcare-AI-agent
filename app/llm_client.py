# app/llm_client.py

import os
import json
import boto3
from botocore.exceptions import ClientError
from typing import Dict, Any, List

# AWS Bedrock Configuration
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "meta.llama3-8b-instruct-v1:0")

class LLMError(Exception):
    """Custom error for LLM / Bedrock failures."""
    pass

# Initialize Bedrock Client
try:
    bedrock_runtime = boto3.client(
        service_name="bedrock-runtime",
        region_name=AWS_REGION
    )
except Exception as e:
    print(f"Warning: Failed to initialize Bedrock client: {e}")
    bedrock_runtime = None


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

ORU_INSTRUCTIONS = """
You are a clinical data transformer that receives:

1) A parsed patient object.
2) A list of structured observations parsed from HL7 OBX segments.

You MUST:

- ONLY use the values actually present in the patient object and in the list
  of structured observations. Do NOT invent new lab values, vital signs,
  diagnoses, or reference ranges.
- If there are NO observations, or all observations have empty code/display/value,
  then:
    * "clinical_summary" MUST be a short factual sentence such as
      "No clinically meaningful observations were parsed from the input HL7."
    * "structured_observations" MUST be an empty list: []
    * "fhir_bundle.entry" MUST contain only a Patient resource (if patient.id exists),
      and NO Observation resources.
- If there ARE observations, you MAY:
    * Normalize units and reference ranges when they are explicitly present.
    * Interpret flags (H, L, N, etc.) to describe high/low/normal in the
      clinical_summary.
- You MUST NOT introduce any new codes, values, or dates that are not present
  in the input data.
- For AI_EXTRACTED observations from clinical notes: ONLY extract values that 
  have an EXPLICIT numeric value stated in the text. For example, "BP 160/95" 
  can be extracted as Blood Pressure. But do NOT infer or assume values that 
  are not explicitly written with a number. If glucose is not mentioned with 
  a specific value like "glucose 120 mg/dL", do NOT add a glucose observation.

You MUST respond with a SINGLE JSON object of the exact form:

{
  "clinical_summary": string,
  "notes_analysis": string,
  "structured_observations": [
    {
      "code": string,
      "display": string,
      "value": any,
      "unit": string,
      "reference_low": string or null,
      "reference_high": string or null,
      "flag": string,
      "observation_datetime": string or null,
      "status": string or null,
      "source": "AI_EXTRACTED"
    },
    ...
  ]
}

Where OPTIONAL means the field may be omitted entirely if you have no data
for it. All JSON MUST be syntactically valid. Do NOT wrap the JSON in any
markdown fences or explanations. Output JSON ONLY.
""".strip()


def build_oru_prompt(patient: Dict[str, Any],
                     observations: List[Dict[str, Any]]) -> str:
    """
    Build the user prompt for the ORU HL7 pipeline.
    """
    patient_json = json.dumps(patient, ensure_ascii=False)
    obs_json = json.dumps(observations, ensure_ascii=False)

    prompt = f"""
{ORU_INSTRUCTIONS}

Here is the parsed patient object:

PATIENT_JSON:
{patient_json}

Here is the list of structured observations parsed from OBX segments:

OBSERVATIONS_JSON:
{obs_json}

Now produce the final JSON object with keys:
  "patient", "clinical_summary", "structured_observations", "fhir_bundle".
Remember: output JSON ONLY.
""".strip()

    return prompt


# ---------------------------------------------------------------------------
# Low-level Bedrock call + JSON handling
# ---------------------------------------------------------------------------

def _strip_markdown_fences(content: str) -> str:
    """
    Robustly extract JSON object from LLM response.
    Finds the first '{' and the last '}'.
    """
    text = content.strip()
    
    start_idx = text.find("{")
    end_idx = text.rfind("}")
    
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        return text[start_idx : end_idx + 1]
        
    return text


def _try_repair_json(raw: str) -> str:
    """
    Very small, conservative JSON "repair" helper.
    Handles common LLM issues like missing braces or trailing comments.
    """
    import re
    text = raw.strip()
    
    # Remove single-line comments like // this is a comment
    text = re.sub(r'//.*$', '', text, flags=re.MULTILINE)
    
    # Case 1: Response starts with a key (missing opening brace)
    # e.g., '\n  "answer": ...'
    if text.startswith('"') or text.lstrip().startswith('"'):
        text = text.lstrip()
        # Add opening brace
        candidate = "{" + text
        # Also add closing brace if missing
        if not candidate.rstrip().endswith("}"):
            candidate = candidate.rstrip().rstrip(",") + "\n}"
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            pass  # Try other repairs

    # Case 2: LLM forgot the final closing brace on a top-level object
    if text.startswith("{") and not text.endswith("}"):
        candidate = text + "\n}"
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            pass
    
    # Case 3: LLM forgot opening brace but has closing
    if not text.startswith("{") and text.endswith("}"):
        candidate = "{\n" + text
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            pass

    return text


def call_llm_for_json(prompt: str) -> Dict[str, Any]:
    """
    Call AWS Bedrock with a prompt that should return a single JSON object.
    Uses Llama 3 format.
    """
    if not bedrock_runtime:
        raise LLMError("AWS Bedrock client is not initialized. Check your AWS credentials.")

    # Llama 3 Inference Configuration
    # https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters-meta.html
    payload = {
        "prompt": f"<|begin_of_text|><|start_header_id|>user<|end_header_id|>\n\n{prompt}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n",
        "max_gen_len": 2048,
        "temperature": 0.0,
        "top_p": 0.9
    }

    try:
        response = bedrock_runtime.invoke_model(
            modelId=BEDROCK_MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(payload)
        )
        
        response_body = json.loads(response.get("body").read())
        generation = response_body.get("generation", "").strip()

    except ClientError as e:
        raise LLMError(f"AWS Bedrock Error: {e}")
    except Exception as e:
        raise LLMError(f"Unexpected error calling Bedrock: {e}")

    # JSON Parsing Logic
    content = _strip_markdown_fences(generation)

    try:
        parsed = json.loads(content, strict=False)
    except json.JSONDecodeError as e:
        repaired = _try_repair_json(content)
        if repaired != content:
            try:
                parsed = json.loads(repaired, strict=False)
            except json.JSONDecodeError as e2:
                raise LLMError(f"Failed to parse LLM JSON after repair: {e2}\nRaw: {content}") from e2
        else:
            raise LLMError(f"Failed to parse LLM JSON: {e}\nRaw: {content}") from e

    if not isinstance(parsed, dict):
        raise LLMError(f"LLM output is not a JSON object. Raw: {content}")

    return parsed


def call_llm(prompt: str) -> str:
    """
    Call AWS Bedrock with a prompt and return plain text response.
    Used for simple text generation (e.g., summaries).
    """
    if not bedrock_runtime:
        raise LLMError("AWS Bedrock client is not initialized. Check your AWS credentials.")

    payload = {
        "prompt": f"<|begin_of_text|><|start_header_id|>user<|end_header_id|>\n\n{prompt}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n",
        "max_gen_len": 512,
        "temperature": 0.5,
        "top_p": 0.9
    }

    try:
        response = bedrock_runtime.invoke_model(
            modelId=BEDROCK_MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(payload)
        )
        
        response_body = json.loads(response.get("body").read())
        generation = response_body.get("generation", "").strip()
        return generation

    except ClientError as e:
        raise LLMError(f"AWS Bedrock Error: {e}")
    except Exception as e:
        raise LLMError(f"Unexpected error calling Bedrock: {e}")
