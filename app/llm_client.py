# app/llm_client.py

import os

# Local Ollama chat endpoint
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")

# Use a smaller, faster model (adjust if you want)
MODEL_NAME = "llama3.2:3b"  # make sure you pulled this with `ollama pull llama3.2:3b`
REQUEST_TIMEOUT_SECONDS = 25  # generous timeout for complex clinical analyses


class LLMError(Exception):
    """Custom error for LLM / Ollama failures."""
    pass


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

You MUST respond with a SINGLE JSON object of the exact form:

{
  "patient": {
    "id": string,
    "first_name": string,
    "last_name": string,
    "dob": string,
    "sex": string
  },
  "clinical_summary": string,
  "structured_observations": [
    {
      "code": string,
      "display": string,
      "value": any,
      "unit": string,
      "reference_low": string or null,
      "reference_high": string or null,
      "flag": string,
      "observation_datetime": string,
      "status": string
    },
    ...
  ],
  "fhir_bundle": {
    "resourceType": "Bundle",
    "type": "collection",
    "entry": [
      {
        "fullUrl": string,
        "resource": {
          "resourceType": "Patient",
          "id": string,
          "name": [
            {
              "family": string,
              "given": [string]
            }
          ],
          "birthDate": string,
          "gender": string
        }
      },
      {
        "fullUrl": string,
        "resource": {
          "resourceType": "Observation",
          "id": string,
          "status": string,
          "code": {
            "coding": [
              {
                "system": string,
                "code": string,
                "display": string
              }
            ],
            "text": string
          },
          "subject": {
            "reference": string
          },
          "valueQuantity": {
            "value": number,
            "unit": string
          },
          "effectiveDateTime": string,
          "referenceRange": [
            {
              "low": { "value": number } OPTIONAL,
              "high": { "value": number } OPTIONAL
            }
          ] OPTIONAL,
          "interpretation": [
            {
              "coding": [
                {
                  "system": string,
                  "code": string
                }
              ]
            }
          ] OPTIONAL
        }
      },
      ...
    ]
  }
}

Where OPTIONAL means the field may be omitted entirely if you have no data
for it. All JSON MUST be syntactically valid. Do NOT wrap the JSON in any
markdown fences or explanations. Output JSON ONLY.
""".strip()


def build_oru_prompt(patient: Dict[str, Any],
                     observations: List[Dict[str, Any]]) -> str:
    """
    Build the user prompt for the ORU HL7 pipeline.

    We embed the already-parsed patient + observations as JSON, and
    prepend strict instructions telling the model not to hallucinate.
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
# Low-level Ollama call + JSON handling
# ---------------------------------------------------------------------------

def _strip_markdown_fences(content: str) -> str:
    """
    Remove ```json ... ``` wrappers if present.
    """
    text = content.strip()
    if not text.startswith("```"):
        return text

    # Strip leading/trailing backticks
    text = text.strip("`").strip()
    # Drop a leading 'json' or 'JSON' token if present
    lowered = text.lower()
    if lowered.startswith("json"):
        text = text[4:].lstrip()

    return text


def _try_repair_json(raw: str) -> str:
    """
    Very small, conservative JSON "repair" helper.

    We ONLY do trivial fixes that are extremely likely to be correct:
    - If it starts with '{' but doesn't end with '}', try appending one '}'.
      If that parses, we use it; otherwise we just return the original.
    """
    text = raw.strip()

    # Case: LLM forgot the final closing brace on a top-level object.
    if text.startswith("{") and not text.endswith("}"):
        candidate = text + "\n}"
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            # If that didn't work, fall back to the original
            return text

    # If no fix applies, just return original
    return text


def call_llm_for_json(prompt: str) -> Dict[str, Any]:
    """
    Call Ollama with a prompt that should return a single JSON object.

    Expects the model to respond with JSON only. We:
      - call the local Ollama chat API
      - strip markdown fences if present
      - try to parse JSON
      - if that fails, try a minimal repair and parse again
    """
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a precise clinical data transformer. "
                    "Always respond with a SINGLE valid JSON object, "
                    "no explanations, no markdown."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "stream": False,
    }

    try:
        resp = requests.post(
            OLLAMA_URL,
            json=payload,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as e:
        raise LLMError(
            f"Error calling Ollama at {OLLAMA_URL}: {e}. "
            f"Check that Ollama is running and the model '{MODEL_NAME}' is available "
            f"(try: `ollama run {MODEL_NAME} \"test\"`)."
        ) from e

    if resp.status_code != 200:
        raise LLMError(f"Ollama returned HTTP {resp.status_code}: {resp.text}")

    data = resp.json()
    content = data.get("message", {}).get("content", "").strip()

    # First pass: strip ```json fences if present
    content = _strip_markdown_fences(content)

    # Try direct parse
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as e:
        # Try a minimal repair (e.g., missing final brace)
        repaired = _try_repair_json(content)
        if repaired != content:
            try:
                parsed = json.loads(repaired)
            except json.JSONDecodeError as e2:
                # Still bad; bubble up with the original content for debugging
                raise LLMError(
                    f"Failed to parse LLM JSON even after repair: {e2}\nRaw content:\n{content}"
                ) from e2
        else:
            # No repair possible, just fail with context
            raise LLMError(
                f"Failed to parse LLM JSON: {e}\nRaw content:\n{content}"
            ) from e

    if not isinstance(parsed, dict):
        raise LLMError(f"LLM output is not a JSON object. Raw content:\n{content}")

    return parsed
