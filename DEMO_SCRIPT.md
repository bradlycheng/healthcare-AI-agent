# 🏥 Healthcare AI Agent: Demo Script

**Project**: Intelligent interface engine that parses HL7 lab results, converts them to FHIR, and uses Generative AI to summarize clinical findings.
**URL**: [http://localhost:8080](http://localhost:8080) (or cloud URL)

---

## 🎬 1. The Hook: "It's Not Just a Parser" (1 minute)

**Goal**: Show that the system understands *meaning*, not just syntax.

1.  Open the **Home Page**.
2.  **Talking Point**: "Healthcare data is notoriously messy. We usually just parse it. But today I want to show you an agent that *understands* it."
3.  Scroll to the **"Try It Live"** section.
4.  Paste this **Messy/Real-world HL7 Message** (copy from below):

    ```text
    MSH|^~\&|LAB|HOSPITAL|EHR|CLINIC|202501181200||ORU^R01|MSG999|P|2.5
    PID|1||99999^^^MRN||Smith^John||19800101|M
    OBR|1|||CBC_PANEL
    OBX|1|NM|GLU^Glucose||245|mg/dL|70-100|H|||F
    OBX|2|TX|NOTE^Clinical Note||Pt non-compliant with meds. Reports excessive thirst and fatigue.||||||F
    ```

5.  Click **"Process Message"**.
6.  **Show the Result**:
    *   Point to the **Clinical Summary**: "See? The AI spotted the high glucose *and* connected it to the 'non-compliant' note to identify uncontrolled diabetes."
    *   Point to **FHIR Bundle**: "And here is the standardized JSON object ready for any app."
    *   **NEW**: Scroll down to see the **HL7 ACK**. "It even generated a valid HL7 Acknowledgement to confirm receipt, just like a real hospital system."

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
