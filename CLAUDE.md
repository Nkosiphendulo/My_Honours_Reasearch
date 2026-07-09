# CLAUDE.md

## Project overview
- This project is a Streamlit-based co-design platform for campus innovation work.
- It uses local-safe fallback storage by default and can connect to Supabase when credentials are provided.

## Data rules
- Never store direct identifiers such as names, emails, or phone numbers.
- Use the anonymised participant code as the primary identifier.
- Sanitize free text before persistence.

## Run locally
- Install dependencies with `pip install -r requirements.txt`
- Start the app with `streamlit run app.py`
