# main.py -- Smart AI Version (Tasks + XP + OpenAI chat + Bengali TTS + token auth)
import os, uuid
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from apscheduler.schedulers.background import BackgroundScheduler
from tinydb import TinyDB, Query
from datetime import datetime
from gtts import gTTS
from dotenv import load_dotenv
import requests

load_dotenv()

# CONFIG
AUDIO_DIR = "audio"
os.makedirs(AUDIO_DIR, exist_ok=True)
DB_FILE = "tasks.json"
db = TinyDB(DB_FILE)
meta = db.table('meta')

API_TOKEN = os.getenv("API_TOKEN", "")  # set in env for production
OPENAI_KEY = os.getenv("OPENAI_API_KEY", "")

app = FastAPI(title="Solo-Leveling Smart AI Coach")
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/audio", StaticFiles(directory=AUDIO_DIR), name="audio")

# Auth helper
def verify_api_key(x_api_key: str = Header(None)):
    if not API_TOKEN:
        return True  # dev mode
    if not x_api_key or x_api_key != API_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True

# Player stats
def get_player():
    recs = meta.search(Query().type == 'player')
    if recs:
        return recs[0]
    rec = {"type":"player","xp":0,"level":1,"last_level_up":None}
    meta.insert(rec)
    return rec

def xp_to_level(xp):
    return xp // 100 + 1

def update_player(delta_xp=0):
    p = get_player()
    new_xp = max(0, p.get('xp',0) + int(delta_xp))
    new_level = xp_to_level(new_xp)
    if new_level > p.get('level',1):
        meta.update({'xp': new_xp, 'level': new_level, 'last_level_up': datetime.now().isoformat(timespec='seconds')}, Query().type == 'player')
    else:
        meta.update({'xp': new_xp, 'level': new_level}, Query().type == 'player')
    return {"xp": new_xp, "level": new_level}

# TTS helper (Bengali)
def make_tts(text: str) -> str:
    fname = f"{uuid.uuid4().hex}.mp3"
    path = os.path.join(AUDIO_DIR, fname)
    try:
        tts = gTTS(text=text, lang='bn')
        tts.save(path)
        return f"/audio/{fname}"
    except Exception as e:
        print("TTS error:", e)
        return ""

# Tasks
def add_task_record(title, due_iso, est_min=30, priority=1):
    rec = {
        "title": title,
        "due": due_iso,
        "est_min": int(est_min),
        "priority": int(priority),
        "done": False,
        "nudges": 0,
        "created_at": datetime.now().isoformat(timespec='seconds'),
        "xp_reward": 10,
        "audio": "",
    }
    return db.insert(rec)

def check_overdue():
    now = datetime.now()
    Task = Query()
    for item in db.all():
        try:
            due = datetime.fromisoformat(item['due'])
        except Exception:
            continue
        if not item.get('done') and due <= now:
            nudges = item.get('nudges', 0) + 1
            db.update({'nudges': nudges}, doc_ids=[item.doc_id])
            if nudges == 1:
                msg = f"স্মরণ করিয়ে দিচ্ছি: '{item['title']}' কাজটি এখনও বাকি আছে। দয়া করে সেটি সম্পন্ন করুন।"
            elif nudges == 2:
                msg = f"একটু কড়া বলছি — '{item['title']}' এখনই করুন। আপনার Solo-Leveling মিশন অসম্পূর্ণ রয়ে গেছে।"
            elif nudges == 3:
                msg = f"আর দেরি করা যাবে না — '{item['title']}' এখনই শেষ করুন, না হলে XP কমবে।"
            else:
                penalty = 5
                update_player(-penalty)
                msg = f"সতর্কতা: '{item['title']}' অনেক দিন বাকি থাকায় আপনার {penalty} XP কাটা হলো। এখনই কাজটি করুন!"
            audio_url = make_tts(msg)
            db.update({'audio': audio_url}, doc_ids=[item.doc_id])
            print("Nudge:", item.doc_id, msg)

scheduler = BackgroundScheduler()
scheduler.add_job(check_overdue, 'interval', seconds=60)
scheduler.start()

# Routes
@app.get("/", response_class=HTMLResponse)
def index():
    return RedirectResponse(url="/static/index.html")

@app.post("/api/add_task")
async def api_add_task(data: dict, authorized: bool = verify_api_key):
    title = data.get('title')
    due = data.get('due')
    if not title or not due:
        return JSONResponse({"error": "title and due required"}, status_code=400)
    try:
        _ = datetime.fromisoformat(due)
    except Exception:
        return JSONResponse({"error": "due must be ISO format like 2025-11-07T21:30:00"}, 400)
    doc_id = add_task_record(title, due, data.get('est_min',30), data.get('priority',1))
    confirm = f"নতুন কাজ যোগ করা হয়েছে: {title}. আমি আপনাকে মনে করিয়ে দেব।"
    audio = make_tts(confirm)
    db.update({'audio': audio}, doc_ids=[doc_id])
    return {"status": "ok", "doc_id": doc_id, "audio": audio}

@app.get("/api/list")
def api_list(authorized: bool = verify_api_key):
    return {"tasks": db.all()}

@app.post("/api/complete")
def api_complete(data: dict, authorized: bool = verify_api_key):
    doc_id = data.get('doc_id')
    if doc_id is None:
        return JSONResponse({"error":"doc_id required"}, status_code=400)
    try:
        recs = db.get(doc_id=int(doc_id))
        if not recs:
            return JSONResponse({"error":"invalid doc_id"}, status_code=400)
        xp = int(recs.get('xp_reward', 10))
        db.update({'done': True}, doc_ids=[int(doc_id)])
    except Exception:
        return JSONResponse({"error":"invalid doc_id"}, status_code=400)

    player_before = get_player()
    level_before = player_before.get('level',1)
    stats = update_player(xp)
    level_after = stats['level']
    if level_after > level_before:
        msg = f"শাবাশ! আপনি {xp} XP পেয়েছেন। মোট XP এখন {stats['xp']}। আপনি লেভেল {level_after}-এ উঠলেন — অভিনন্দন!"
    else:
        msg = f"শাবাশ! আপনি {xp} XP পেয়েছেন। মোট XP এখন {stats['xp']}। লেভেল: {stats['level']}।"
    audio = make_tts(msg)
    return {"status":"completed", "audio": audio, "xp_gained": xp, "stats": stats}

@app.get("/api/stats")
def api_stats(authorized: bool = verify_api_key):
    p = get_player()
    return {"xp": p.get('xp',0), "level": p.get('level',1), "last_level_up": p.get('last_level_up')}

# OpenAI chat (optional)
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
@app.post("/api/ask")
def api_ask(data: dict, authorized: bool = verify_api_key):
    prompt = data.get('prompt','')
    lang = data.get('lang','bn')
    if not prompt:
        return JSONResponse({"error":"prompt required"}, status_code=400)
    if not OPENAI_KEY:
        resp = f"আমি অনলাইনে নেই—আপনি বললেন: {prompt[:300]}"
        audio = make_tts(resp) if lang.startswith('bn') else ""
        return {"answer": resp, "audio": audio, "note":"No OpenAI key configured."}
    headers = {"Authorization": f"Bearer {OPENAI_KEY}"}
    body = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role":"system","content":"You are a helpful assistant that answers concisely in Bengali."},
            {"role":"user","content": prompt}
        ],
        "max_tokens": 300,
        "temperature": 0.6
    }
    try:
        r = requests.post(OPENAI_URL, json=body, headers=headers, timeout=15)
        r.raise_for_status()
        j = r.json()
        ans = j['choices'][0]['message']['content'].strip()
        audio = make_tts(ans) if lang.startswith('bn') else ""
        return {"answer": ans, "audio": audio}
    except Exception as e:
        print("OpenAI error:", e)
        return {"error":"openai_error", "detail": str(e)}

@app.get("/api/audio/{fname}")
def get_audio(fname: str, authorized: bool = verify_api_key):
    path = os.path.join(AUDIO_DIR, fname)
    if os.path.exists(path):
        return FileResponse(path, media_type="audio/mpeg")
    return JSONResponse({"error":"not found"}, status_code=404)