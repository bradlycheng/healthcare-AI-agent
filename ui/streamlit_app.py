# ui/streamlit_app.py

import sys
import json
from pathlib import Path

import streamlit as st

# Make sure we can import from app/
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT_DIR))

from app.agent import run_oru_pipeline  # type: ignore


st.title("Offline HL7 ORU → FHIR Agent (v1)")

st.write(
    "Paste an HL7 ORU^R01 message below or upload a .hl7 file. "
    "The agent will parse it, generate FHIR Observations, and produce a clinical summary."
)

uploaded_file = st.file_uploader("Upload HL7 file", type=["hl7", "txt"])
hl7_input = st.text_area("Or paste HL7 text here", height=200)

run_button = st.button("Run Agent")

if run_button:
    if uploaded_file is not None:
        hl7_text = uploaded_file.read().decode("utf-8", errors="ignore")
    else:
        hl7_text = hl7_input

    if not hl7_text.strip():
        st.error("Please provide HL7 text (via upload or paste).")
    else:
        with st.spinner("Running agent..."):
            try:
                result = run_oru_pipeline(hl7_text)
            except Exception as e:
                st.error(f"Error running pipeline: {e}")
            else:
                st.subheader("Clinical Summary")
                st.write(result.get("clinical_summary", ""))

                st.subheader("Parsed ORU (internal representation)")
                st.json(result.get("parsed_oru", {}))

                st.subheader("FHIR Bundle (JSON)")
                st.json(result.get("fhir_bundle", {}))
