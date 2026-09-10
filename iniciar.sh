cd "$(dirname "$0")/app" && python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
