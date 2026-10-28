import os
import time
import subprocess
from fastapi import FastAPI, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import requests

app = FastAPI(title="ASMO AI Studio Backend")

# Serve rendered video clips publicly so Meta/TikTok can download them
os.makedirs("clips", exist_ok=True)
app.mount("/clips", StaticFiles(directory="clips"), name="clips")

class ScheduleRequest(BaseModel):
    source_url: str
    title: str
    caption: str
    page_id: str
    page_token: str
    server_base_url: str  # Your live Render URL

@app.get("/")
def health():
    return {"status": "online", "engine": "ASMO Video Processor Active"}

def process_and_publish_video(req: ScheduleRequest):
    clip_id = f"clip_{int(time.time())}"
    raw_video = f"clips/{clip_id}_raw.mp4"
    final_video = f"clips/{clip_id}_916.mp4"

    try:
      # 1. Download a 30-second highlight from stream using yt-dlp
      print(f"Downloading stream highlight from {req.source_url}...")
      download_cmd = [
          "yt-dlp",
          "--download-sections", "*00:01:00-00:01:30",
          "-f", "mp4/best[height<=720]",
          "-o", raw_video,
          req.source_url
      ]
      subprocess.run(download_cmd, check=True)

      # 2. FFmpeg 9:16 Vertical Center-Crop with Blurred Background Padding
      print("Rendering 9:16 vertical video with FFmpeg...")
      ffmpeg_cmd = [
          "ffmpeg", "-y", "-i", raw_video,
          "-filter_complex",
          "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25:5[bg];"
          "[0:v]scale=1080:-1[fg];"
          "[bg][fg]overlay=(W-w)/2:(H-h)/2[outv]",
          "-map", "[outv]",
          "-map", "0:a?",
          "-c:v", "libx264", "-preset", "fast", "-crf", "22",
          "-c:a", "aac", "-b:a", "128k",
          final_video
      ]
      subprocess.run(ffmpeg_cmd, check=True)

      # 3. Direct Public Video URL for Meta/TikTok to ingest
      public_video_url = f"{req.server_base_url}/clips/{clip_id}_916.mp4"
      print(f"Video ready at: {public_video_url}")

      # 4. Schedule to Meta (Facebook Page & Instagram Reels)
      scheduled_time = int(time.time()) + 900  # 15 minutes in future
      print(f"Scheduling to Meta Page ID: {req.page_id}...")

      meta_url = f"https://graph.facebook.com/v19.0/{req.page_id}/videos"
      payload = {
          "file_url": public_video_url,
          "description": f"{req.title}\n\n{req.caption}",
          "published": "false",
          "scheduled_publish_time": str(scheduled_time),
          "access_token": req.page_token
      }
      res = requests.post(meta_url, data=payload)
      print("Meta Response:", res.json())

    except Exception as e:
      print(f"Error in video pipeline: {str(e)}")

@app.post("/api/schedule-reel")
def schedule_reel(req: ScheduleRequest, background_tasks: BackgroundTasks):
    background_tasks.add_task(process_and_publish_video, req)
    return {
        "status": "QUEUED",
        "message": "Video is being clipped, cropped to 9:16, and dispatched to Meta Business Suite!",
        "estimated_time": "60 seconds"
  }
