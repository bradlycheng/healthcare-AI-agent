# 🏥 Healthcare AI Agent: Demo Script

**Project**: Intelligent interface engine that parses HL7 lab results, converts them to FHIR, and uses Generative AI to summarize clinical findings.
**URL**: [http://localhost:8080](http://localhost:8080) (or cloud URL)

---

## 🎬 1. The Hook: "It's Not Just a Parser" (1 minute)

**Goal**: Show that the system understands *meaning*, not just syntax.

1.  Open the **Home Page**.
2.  **Talking Point**: "Healthcare data is notoriously messy. We usually just parse it. But today I want to show you an agent that *understands* it."
3.  Scroll to the **"Try It Live"** section.
4.  Paste this **Real-world Vitals Case (Hypertension)** (copy from below):

    ```text
    MSH|^~\&|HIS|MedCenter|LIS|VITALS|202412270815||ORU^R01|MSG009|P|2.5
    PID|1||10009||GORDON^BARBARA||19600101|F
    OBR|1|ORD009|RES009|8716-3^VITAL SIGNS|||202412270815
    OBX|1|NM|8480-6^SYSTOLIC_BP||160|mmHg|90-120|HH|||F
    OBX|2|NM|8462-4^DIASTOLIC_BP||98|mmHg|60-80|H|||F
    OBX|3|NM|8867-4^HEART_RATE||88|bpm|60-100|N|||F
    OBX|4|TX|NOTE^Clinical Note||Uncontrolled Hypertension. Patient non-compliant with meds.||||||F
    ```

5.  Click **"Process Message"**.
6.  **Show the Result**:
    *   **Context**: "This represents a patient with severe blood pressure issues coming in from a triage monitor."
    *   Point to the **Clinical Summary**: "The AI sees the high BP values and the 'non-compliant' note, correctly identifying 'Uncontrolled Hypertension'."
    *   Point to **FHIR Bundle**: "It standardizes these Vitals into a valid FHIR format."
    *   **NEW**: Scroll down to see the **HL7 ACK**. "It generated a valid acknowledgement confirming receipt."

---

## 🔍 2. Resilience: "Garbage In, Safety Out" (30 seconds)

**Goal**: Demonstrate the new validation features.

1.  **Talking Point**: "What happens if we send garbage? Most parsers crash."
2.  Paste **Use the 'Garbage' Payload**:
    ```text
    This is not an HL7 message.
    ```
3.  Click **"Process Message"**.
4.  **Show the Warning**:
    *   It should show a clean **400 Bad Request**: `"Invalid HL7 message. Must start with MSH segment."`
5.  **Talking Point**: "The system validates structure and message type (ORU) before processing, ensuring security and stability."

---

## 🧠 3. Intelligence: "Ask Your Data" (1 minute)

**Goal**: Show the SQL/Query capabilities.

1.  Click **"Dashboard"** in the navigation.
2.  **Talking Point**: "We've processed hundreds of messages. Instead of writing SQL, let's just ask."
3.  Type in the **Query Assistant**:
    > "Show me all patients with high glucose levels."
4.  **Show the Result**:
    *   The system generates the SQL, executes it, and lists the patients.
    *   "It essentially turns natural language into database queries."

---

## 🚀 4. The Future (Closing)

1.  **Talking Point**: "This is a working prototype. The next steps are adding MLLP connectivity and expanding to ADT (Admissions) messages."
2.  "Any questions?"
