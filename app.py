flask
flask-cors
yt-dlp
faster-whisper
moviepy==1.0.3
numpy
import os
import uuid
import numpy as np
import yt_dlp
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from faster_whisper import WhisperModel
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip

app = Flask(__name__)
CORS(app)

OUTPUT_DIR = "generated_shorts"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Load Whisper AI model for automatic speech-to-text captions
print("Loading AI Speech Transcription Model...")
whisper_model = WhisperModel("base", device="cpu", compute_type="int8")

def download_youtube_video(url):
    video_id = str(uuid.uuid4())[:8]
    output_path = f"temp_{video_id}.mp4"
    ydl_opts = {
        'format': 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': output_path,
        'quiet': True
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    return output_path

def find_viral_timestamps(video_path, clip_duration=25, top_n=3):
    video = VideoFileClip(video_path)
    audio = video.audio
    duration = int(video.duration)
    volumes = []

    # Scan every 1 second for loud hype moments (explosions, reactions, action)
    for t in range(0, max(1, duration - clip_duration), 1):
        sub = audio.subclip(t, t + 1)
        arr = sub.to_soundarray(fps=22050)
        rms = float(np.sqrt(np.mean(arr**2)))
        volumes.append((t, rms))

    volumes.sort(key=lambda x: x[1], reverse=True)
    selected = []
    for ts, vol in volumes:
        if all(abs(ts - s) > clip_duration for s in selected):
            selected.append(ts)
        if len(selected) >= top_n:
            break

    video.close()
    return sorted(selected)

def create_captioned_short(video_path, start_t, duration, caption_color, index):
    video = VideoFileClip(video_path)
    end_t = min(start_t + duration, video.duration)
    clip = video.subclip(start_t, end_t)

    # 1. Crop 16:9 gameplay into 9:16 vertical YouTube Short
    w, h = clip.size
    target_w = int(h * (9 / 16))
    x_center = w / 2
    vertical_clip = clip.crop(x1=x_center - target_w / 2, x2=x_center + target_w / 2)
    vertical_clip = vertical_clip.resize(height=1920)

    # 2. Extract audio & transcribe what people are saying with timestamps
    temp_audio = f"temp_audio_{index}.wav"
    vertical_clip.audio.write_audiofile(temp_audio, verbose=False, logger=None)
    segments, _ = whisper_model.transcribe(temp_audio, word_timestamps=True)

    # 3. Create attractive colored word-by-word captions
    subtitle_clips = []
    for segment in segments:
        for word in segment.words:
            txt = word.word.strip().upper()
            if not txt:
                continue
            txt_clip = (
                TextClip(
                    txt,
                    fontsize=85,
                    color=caption_color,       # e.g., '#FFE600' (Cyber Yellow) or '#FF2A85' (Vice Pink)
                    font="Arial-Bold",
                    stroke_color="black",
                    stroke_width=4,
                    method="caption",
                    size=(vertical_clip.w - 120, None)
                )
                .set_position(("center", vertical_clip.h * 0.72))
                .set_start(word.start)
                .set_end(word.end)
            )
            subtitle_clips.append(txt_clip)

    # 4. Combine video + colored captions and export MP4
    final_video = CompositeVideoClip([vertical_clip] + subtitle_clips)
    out_filename = f"rockstar_viral_short_{uuid.uuid4().hex[:6]}.mp4"
    out_path = os.path.join(OUTPUT_DIR, out_filename)

    final_video.write_videofile(
        out_path,
        codec="libx264",
        audio_codec="aac",
        fps=30,
        verbose=False,
        logger=None
    )

    video.close()
    final_video.close()
    if os.path.exists(temp_audio):
        os.remove(temp_audio)

    return out_filename

@app.route("/api/clip", methods=["POST"])
def generate_clips():
    data = request.json
    url = data.get("url")
    # Default to Cyber Yellow (#FFE600) - highest retention color on Shorts
    caption_color = data.get("color", "#FFE600")
    clip_duration = int(data.get("duration", 25))

    if not url:
        return jsonify({"error": "Please paste a valid video URL"}), 400

    try:
        raw_video = download_youtube_video(url)
        timestamps = find_viral_timestamps(raw_video, clip_duration=clip_duration, top_n=3)
        
        results = []
        for idx, start_t in enumerate(timestamps):
            filename = create_captioned_short(raw_video, start_t, clip_duration, caption_color, idx)
            results.append({
                "clip_number": idx + 1,
                "start_second": start_t,
                "download_url": f"/shorts/{filename}",
                "suggested_title": f"Rockstar DID NOT hold back in GTA 6! 😱🔥 #gta6 #shorts"
            })

        if os.path.exists(raw_video):
            os.remove(raw_video)

        return jsonify({"status": "success", "clips": results})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/shorts/<filename>")
def serve_short(filename):
    return send_from_directory(OUTPUT_DIR, filename)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
flask
flask-cors
yt-dlp
faster-whisper
moviepy==1.0.3
numpy
google-api-python-client
google-auth-oauthlib
google-auth-httplib2
import os
import uuid
import pickle
import numpy as np
import yt_dlp
from flask import Flask, request, jsonify
from flask_cors import CORS
from faster_whisper import WhisperModel
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

app = Flask(__name__)
CORS(app)

# --- CONFIGURATION ---
YOUTUBE_API_KEY = "YOUR_YOUTUBE_DATA_API_KEY"
CLIENT_SECRETS_FILE = "client_secrets.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly"]
OUTPUT_DIR = "autopilot_shorts"
os.makedirs(OUTPUT_DIR, exist_ok=True)

whisper_model = WhisperModel("base", device="cpu", compute_type="int8")

# 1. AUTHENTICATE YOUR YOUTUBE CHANNEL (Saves login token so it runs hands-free)
def get_authenticated_youtube():
    creds = None
    if os.path.exists("token.pickle"):
        with open("token.pickle", "rb") as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
            creds = flow.run_local_server(port=8080)
        with open("token.pickle", "wb") as token:
            pickle.dump(creds, token)
    return build("youtube", "v3", credentials=creds)

# 2. AUTOMATICALLY FIND VIRAL YOUTUBE VIDEOS
def find_viral_youtube_videos(query="GTA 6 gameplay", max_results=3):
    youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
    search_response = youtube.search().list(
        q=query,
        part="id,snippet",
        maxResults=max_results,
        type="video",
        order="viewCount",        # Pulls highest-view trending videos
        videoDuration="medium"    # 4 to 20 min videos (best for clipping)
    ).execute()

    videos = []
    for item in search_response.get("items", []):
        vid_id = item["id"]["videoId"]
        title = item["snippet"]["title"]
        videos.append({
            "video_id": vid_id,
            "title": title,
            "url": f"https://www.youtube.com/watch?v={vid_id}"
        })
    return videos

# 3. DOWNLOAD SOURCE VIDEO
def download_video(url):
    filename = f"raw_{uuid.uuid4().hex[:8]}.mp4"
    ydl_opts = {
        "format": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": filename,
        "quiet": True
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    return filename

# 4. FIND MOST VIRAL 30-SECOND MOMENT (Audio Energy Spike Detection)
def get_best_30s_timestamp(video_path, clip_duration=30):
    video = VideoFileClip(video_path)
    audio = video.audio
    duration = int(video.duration)
    volumes = []

    for t in range(0, max(1, duration - clip_duration), 1):
        sub = audio.subclip(t, t + 1)
        arr = sub.to_soundarray(fps=22050)
        rms = float(np.sqrt(np.mean(arr**2)))
        volumes.append((t, rms))

    volumes.sort(key=lambda x: x[1], reverse=True)
    video.close()
    return volumes[0][0] if volumes else 0

# 5. CREATE 9:16 VERTICAL SHORT WITH ATTRACTIVE COLORED CAPTIONS
def render_30s_short(video_path, start_t, caption_color="#FFE600"):
    video = VideoFileClip(video_path)
    end_t = min(start_t + 30, video.duration)
    clip = video.subclip(start_t, end_t)

    # Crop 16:9 to 9:16 vertical
    w, h = clip.size
    target_w = int(h * (9 / 16))
    x_center = w / 2
    vertical_clip = clip.crop(x1=x_center - target_w / 2, x2=x_center + target_w / 2)
    vertical_clip = vertical_clip.resize(height=1920)

    # Transcribe speech
    temp_audio = f"audio_{uuid.uuid4().hex[:6]}.wav"
    vertical_clip.audio.write_audiofile(temp_audio, verbose=False, logger=None)
    segments, _ = whisper_model.transcribe(temp_audio, word_timestamps=True)

    subtitle_clips = []
    for segment in segments:
        for word in segment.words:
            txt = word.word.strip().upper()
            if not txt:
                continue
            txt_clip = (
                TextClip(
                    txt,
                    fontsize=88,
                    color=caption_color,
                    font="Arial-Bold",
                    stroke_color="black",
                    stroke_width=4,
                    method="caption",
                    size=(vertical_clip.w - 120, None)
                )
                .set_position(("center", vertical_clip.h * 0.72))
                .set_start(word.start)
                .set_end(word.end)
            )
            subtitle_clips.append(txt_clip)

    final_video = CompositeVideoClip([vertical_clip] + subtitle_clips)
    out_path = os.path.join(OUTPUT_DIR, f"short_{uuid.uuid4().hex[:6]}.mp4")
    final_video.write_videofile(out_path, codec="libx264", audio_codec="aac", fps=30, verbose=False, logger=None)

    video.close()
    final_video.close()
    if os.path.exists(temp_audio):
        os.remove(temp_audio)
    return out_path

# 6. AUTOMATICALLY UPLOAD 30s SHORT TO YOUR YOUTUBE CHANNEL
def upload_short_to_youtube(youtube_service, file_path, title, description):
    body = {
        "snippet": {
            "title": title[:100],
            "description": description,
            "tags": ["GTA6", "GTAVI", "RockstarGames", "ViceCity", "Shorts"],
            "categoryId": "20"  # Category 20 = Gaming
        },
        "status": {
            "privacyStatus": "public",  # Will upload as private until Google Cloud project audit is approved
            "selfDeclaredMadeForKids": False
        }
    }
    media = MediaFileUpload(file_path, chunksize=1024*1024, resumable=True, mimetype="video/mp4")
    request = youtube_service.videos().insert(part="snippet,status", body=body, media_body=media)
    response = request.execute()
    return response.get("id")

# --- FULL AUTOPILOT ENDPOINT FOR BASE44 ---
@app.route("/api/autopilot", methods=["POST"])
def run_autopilot():
    data = request.json or {}
    query = data.get("query", "GTA 6 viral moments")
    caption_color = data.get("color", "#FFE600")  # Cyber Yellow default
    count = int(data.get("count", 2))

    try:
        yt_auth = get_authenticated_youtube()
        viral_sources = find_viral_youtube_videos(query=query, max_results=count)
        uploaded_log = []

        for src in viral_sources:
            raw_file = download_video(src["url"])
            best_start = get_best_30s_timestamp(raw_file, clip_duration=30)
            short_file = render_30s_short(raw_file, best_start, caption_color=caption_color)

            short_title = f"Rockstar went CRAZY with this in GTA 6! 😱🔥 #GTA6 #Shorts"
            short_desc = f"Insane GTA 6 Vice City moment!\n\n#GTA6 #GTAVI #RockstarGames #GamingShorts"

            uploaded_id = upload_short_to_youtube(yt_auth, short_file, short_title, short_desc)

            uploaded_log.append({
                "source_title": src["title"],
                "short_title": short_title,
                "uploaded_video_id": uploaded_id,
                "youtube_url": f"https://youtube.com/shorts/{uploaded_id}"
            })

            if os.path.exists(raw_file):
                os.remove(raw_file)

        return jsonify({"status": "completed", "uploaded_shorts": uploaded_log})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
fluorescent-clip-viral-flow.base44.app
