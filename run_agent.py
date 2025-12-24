# run_agent.py

import sys
import json
from pathlib import Path

from app.agent import run_oru_pipeline  # only use the pipeline, not parse_oru


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python run_agent.py path/to/message.hl7")
        sys.exit(1)

    hl7_path = Path(sys.argv[1])

    if not hl7_path.exists():
        print(f"File not found: {hl7_path}")
        sys.exit(1)

    hl7_text = hl7_path.read_text(encoding="utf-8")

    print("Running ORU pipeline...")

    # NEW: run the full pipeline, which returns a dict
    result = run_oru_pipeline(hl7_text)

    patient = result.get("patient", {}) or {}
    clinical_summary = result.get("clinical_summary", "") or ""
    structured_observations = result.get("structured_observations", []) or []
    fhir_bundle = result.get("fhir_bundle", {}) or {}

    # Print patient info (if available)
    if patient:
        print("\n=== Patient ===")
        pid = patient.get("id", "")
        name = " ".join(
            [patient.get("first_name", "").strip(), patient.get("last_name", "").strip()]
        ).strip()
        dob = patient.get("dob", "")
        sex = patient.get("sex", "")

        print(f"ID:   {pid}")
        print(f"Name: {name}")
        print(f"DOB:  {dob}")
        print(f"Sex:  {sex}")

    # Clinical summary
    print("\n=== Clinical Summary ===")
    print(clinical_summary)

    # Structured observations
    print("\n=== Structured Observations (JSON) ===")
    print(json.dumps(structured_observations, indent=2))

    # FHIR bundle
    print("\n=== FHIR Bundle (JSON) ===")
    print(json.dumps(fhir_bundle, indent=2))


if __name__ == "__main__":
    main()
