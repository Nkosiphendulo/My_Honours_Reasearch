# Co-Design Platform Specification

## 1. Purpose
Build a Streamlit-based co-design platform that helps students and staff turn campus needs into structured product concepts without ever storing personally identifiable information.

## 2. Structured Product Concept (SPC)
Each generated concept should contain four parts:
1. Problem statement
2. Target user
3. Solution concept
4. Evidence or rationale

## 3. User flow
1. Consent page
2. Co-design workshop page
3. Evaluation page
4. Survey page

## 4. Data governance rules
- Store only anonymised participant codes and derived content.
- Never store names, email addresses, phone numbers, or other direct identifiers.
- Use Row Level Security for all database tables and restrict access to the service role.
- Redact or reject PII in free-text fields before persistence.
