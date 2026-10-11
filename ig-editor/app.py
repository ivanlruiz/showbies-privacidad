"""Editor de videos de Instagram: descarga, navegación por fotogramas, recorte y export a MP4.
Requisitos: pip install flask yt-dlp  +  ffmpeg en el PATH.  Uso: python app.py -> http://localhost:5000
"""
import json, os, subprocess, uuid
from flask import Flask, request, jsonify, send_file, send_from_directory, abort
import yt_dlp

BASE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(BASE, "videos")
os.makedirs(WORK, exist_ok=True)
app = Flask(__name__)

def path_for(vid):
    if not vid.isalnum():
        abort(400)
    p = os.path.join(WORK, vid + ".mp4")
    if not os.path.exists(p):
        abort(404)
    return p

@app.get("/")
def index():
    return send_from_directory(BASE, "index.html")

@app.post("/api/load")
def load():
    url = (request.json or {}).get("url", "").strip()
    if "instagram.com" not in url:
        return jsonify(error="Pegá un link de Instagram válido"), 400
    vid = uuid.uuid4().hex
    out = os.path.join(WORK, vid + ".mp4")
    opts = {"outtmpl": out, "format": "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b",
            "merge_output_format": "mp4", "quiet": True, "noplaylist": True}
    if os.path.exists(os.path.join(BASE, "cookies.txt")):
        opts["cookiefile"] = os.path.join(BASE, "cookies.txt")
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
    except Exception as e:
        return jsonify(error=f"No se pudo descargar: {e}"), 500
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=r_frame_rate:format=duration", "-of", "json", out],
                           capture_output=True, text=True)
    info = json.loads(probe.stdout or "{}")
    num, den = (info.get("streams", [{}])[0].get("r_frame_rate", "30/1")).split("/")
    fps = float(num) / float(den or 1)
    return jsonify(id=vid, fps=round(fps, 3), duration=float(info.get("format", {}).get("duration", 0)))

@app.get("/api/video/<vid>")
def video(vid):
    return send_file(path_for(vid), mimetype="video/mp4", conditional=True)

@app.post("/api/trim/<vid>")
def trim(vid):
    src = path_for(vid)
    d = request.json or {}
    start, end = float(d.get("start", 0)), float(d.get("end", 0))
    if end <= start:
        return jsonify(error="El fin debe ser mayor al inicio"), 400
    out = os.path.join(WORK, f"{vid}_{uuid.uuid4().hex[:6]}.mp4")
    # Re-encode para corte exacto al fotograma
    cmd = ["ffmpeg", "-y", "-ss", f"{start:.3f}", "-i", src, "-t", f"{end - start:.3f}",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-c:a", "aac",
           "-movflags", "+faststart", out]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        return jsonify(error=r.stderr[-500:]), 500
    return send_file(out, as_attachment=True, download_name="recorte.mp4", mimetype="video/mp4")

if __name__ == "__main__":
    app.run(debug=True, port=5000)
