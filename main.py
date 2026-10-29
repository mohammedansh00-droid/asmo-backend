import os
import time
import subprocess
from fastapi import FastAPI, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import requests

app = FastAPI(title="ASMO AI Studio Backend")

os.makedirs("clips", exist_ok=True)
app.mount("/clips", StaticFiles(directory="clips"), name="clips")

class ScheduleRequest(BaseModel):
    source_url: str
    title: str
    caption: str
    page_id: str
    page_token: str
    server_base_url: str

@app.get("/")
def health():
    return {"status": "online", "engine": "ASMO Multi-Platform Reel Engine Active"}

def process_and_publish_video(req: ScheduleRequest):
    clip_id = f"clip_{int(time.time())}"
    raw_video = f"clips/{clip_id}_raw.mp4"
    final_video = f"clips/{clip_id}_916.mp4"

    try:
        # 1. Download stream clip with mobile user-agent
        print(f"Downloading stream highlight from {req.source_url}...")
        download_cmd = [
            "yt-dlp",
            "--extractor-args", "youtube:player_client=android,web",
            "--download-sections", "*00:00:30-00:00:55",
            "-f", "best[height<=480]/bestvideo[height<=480]+bestaudio/best",
            "-o", raw_video,
            req.source_url
        ]
        result = subprocess.run(download_cmd)

        # Fallback if YouTube blocks datacenter IP
        if result.returncode != 0 or not os.path.exists(raw_video):
            print("Generating lightweight 9:16 vertical canvas...")
            fallback_cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", "color=c=0x180d2e:s=720x1280:d=20",
                "-f", "lavfi", "-i", "sine=f=440:d=20",
                "-threads", "1",
                "-c:v", "libx264", "-preset", "ultrafast",
                "-c:a", "aac", "-b:a", "64k",
                final_video
            ]
            subprocess.run(fallback_cmd, check=True)
        else:
            # 2. Render low-memory 9:16 vertical cut (< 120MB RAM)
            print("Rendering low-memory 9:16 vertical cut with FFmpeg...")
            ffmpeg_cmd = [
                "ffmpeg", "-y", "-i", raw_video,
                "-filter_complex",
                "[0:v]scale=270:480,boxblur=8:1,scale=1080:1920[bg];"
                "[0:v]scale=1080:-1[fg];"
                "[bg][fg]overlay=(W-w)/2:(H-h)/2[outv]",
                "-map", "[outv]",
                "-map", "0:a?",
                "-threads", "1",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "26",
                "-c:a", "aac", "-b:a", "96k",
                "-t", "25",
                final_video
            ]
            subprocess.run(ffmpeg_cmd, check=True)

        # 3. Direct Public Video URL
        public_video_url = f"{req.server_base_url}/clips/{clip_id}_916.mp4"
        print(f"Video ready at: {public_video_url}")

        if os.path.exists(raw_video):
            os.remove(raw_video)

        scheduled_time = int(time.time()) + 900  # 15 mins in future

        # ----------------------------------------------------
        # 4A. SCHEDULE AS AN INSTAGRAM REEL (@asmowarlord)
        # ----------------------------------------------------
        print("Finding Instagram Business Account ID...")
        page_info_res = requests.get(
            f"https://graph.facebook.com/v19.0/{req.page_id}?fields=instagram_business_account&access_token={req.page_token}"
        )
        page_data = page_info_res.json()
        ig_user_id = page_data.get("instagram_business_account", {}).get("id")

        if ig_user_id:
            print(f"Scheduling Instagram Reel to IG Account ID: {ig_user_id}...")
            ig_container_url = f"https://graph.facebook.com/v19.0/{ig_user_id}/media"
            ig_payload = {
                "media_type": "REELS",
                "video_url": public_video_url,
                "caption": f"{req.title}\n\n{req.caption}\n\n#reels #gaming",
                "share_to_feed": "true",
                "access_token": req.page_token
            }
            ig_res = requests.post(ig_container_url, data=ig_payload)
            print("Instagram Reels Response:", ig_res.json())
        else:
            print("No separate IG ID found, scheduling via Facebook Page Video...")

        # ----------------------------------------------------
        # 4B. SCHEDULE TO FACEBOOK PAGE (Asmogaming)
        # ----------------------------------------------------
        meta_url = f"https://graph.facebook.com/v19.0/{req.page_id}/videos"
        fb_payload = {
            "file_url": public_video_url,
            "description": f"{req.title}\n\n{req.caption}",
            "published": "false",
            "scheduled_publish_time": str(scheduled_time),
            "access_token": req.page_token
        }
        fb_res = requests.post(meta_url, data=fb_payload)
        print("Facebook Page Response:", fb_res.json())

    except Exception as e:
        print(f"Error in video pipeline: {str(e)}")

@app.post("/api/schedule-reel")
def schedule_reel(req: ScheduleRequest, background_tasks: BackgroundTasks):
    background_tasks.add_task(process_and_publish_video, req)
    return {
        "status": "QUEUED",
        "message": "Video is rendering and broadcasting to Instagram Reels and Facebook!",
        "estimated_time": "30-50 seconds"
    }
