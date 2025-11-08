# Solo-Leveling Smart AI Coach

This is the Smart AI version: Tasks + Bengali TTS reminders + XP/Level + optional OpenAI chat.
Files included:
- main.py
- static/index.html (simple phone-friendly UI)
- requirements.txt
- Dockerfile
- audio/ (generated at runtime)

## Quick start (local)
1. unzip and go into folder
2. python -m venv venv
3. source venv/bin/activate  # Windows: venv\Scripts\activate
4. pip install -r requirements.txt
5. uvicorn main:app --host 0.0.0.0 --port 8000
6. Open http://127.0.0.1:8000

## Deploy on Render (quick)
- Create a GitHub repo and push these files.
- On Render: New → Web Service → connect repo
- Build command: pip install -r requirements.txt
- Start command: uvicorn main:app --host 0.0.0.0 --port $PORT
- Add Environment Variables on Render:
  - API_TOKEN = a secret token (optional but recommended)
  - OPENAI_API_KEY = your OpenAI API key (optional for chat)

## Notes
- gTTS requires internet to generate audio files.
- Clean up audio/ occasionally to avoid storage growth.