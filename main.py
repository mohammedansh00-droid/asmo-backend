import os
import time
import subprocess
from fastapi import FastAPI, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import requests

app = FastAPI(title="ASMO AI Studio Multi-Platform Engine")

os.makedirs("clips", exist_ok=True)
app.mount("/clips", StaticFiles(directory="clips"), name="clips")

class ScheduleRequest(BaseModel):
    source_url: str
    title: str
    caption: str
    page_id: str
    page_token: str
    server_base_url: str
    tiktok_token: str = ""

@app.get("/")
def health():
    return {"status": "online", "engine": "ASMO Full Multi-Platform Broadcaster"}

def process_and_publish_all(req: ScheduleRequest):
    clip_id = f"clip_{int(time.time())}"
    raw_video = f"clips/{clip_id}_raw.mp4"
    final_video = f"clips/{clip_id}_916.mp4"

    try:
        # 1. Download real stream using Android client emulation to bypass YouTube 429
        print(f"Extracting real video from: {req.source_url}...")
        download_cmd = [
            "yt-dlp",
            "--no-check-certificates",
            "--user-agent", "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36",
            "--extractor-args", "youtube:player_client=android,ios",
            "--download-sections", "*00:00:15-00:00:45",
            "-f", "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
            "-o", raw_video,
            req.source_url
        ]
        res = subprocess.run(download_cmd)

        if not os.path.exists(raw_video):
            raise RuntimeError("Could not download video chunk from YouTube stream.")

        # 2. Render real 9:16 vertical video with blurred gameplay backdrop
        print("Rendering 9:16 vertical video with FFmpeg...")
        ffmpeg_cmd = [
            "ffmpeg", "-y", "-i", raw_video,
            "-filter_complex",
            "[0:v]scale=270:480,boxblur=10:1,scale=1080:1920[bg];"
            "[0:v]scale=1080:-1[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)/2[outv]",
            "-map", "[outv]",
            "-map", "0:a?",
            "-threads", "1",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "26",
            "-c:a", "aac", "-b:a", "96k",
            "-t", "30",
            final_video
        ]
        subprocess.run(ffmpeg_cmd, check=True)

        public_video_url = f"{req.server_base_url}/clips/{clip_id}_916.mp4"
        print(f"Real 9:16 video ready at: {public_video_url}")

        if os.path.exists(raw_video):
            os.remove(raw_video)

        scheduled_time = int(time.time()) + 900  # 15 mins in future

        # ----------------------------------------------------
        # PLATFORM 1: FACEBOOK PAGE & REELS (Asmogaming)
        # ----------------------------------------------------
        print("Publishing to Facebook Page & Reels...")
        fb_url = f"https://graph.facebook.com/v19.0/{req.page_id}/videos"
        fb_payload = {
            "file_url": public_video_url,
            "description": f"{req.title}\n\n{req.caption}",
            "published": "false",
            "scheduled_publish_time": str(scheduled_time),
            "access_token": req.page_token
        }
        fb_res = requests.post(fb_url, data=fb_payload).json()
        print("Facebook Result:", fb_res)

        # ----------------------------------------------------
        # PLATFORM 2: INSTAGRAM REELS (@asmowarlord)
        # ----------------------------------------------------
        print("Fetching Instagram Account ID...")
        ig_lookup = requests.get(
            f"https://graph.facebook.com/v19.0/{req.page_id}?fields=instagram_business_account&access_token={req.page_token}"
        ).json()
        ig_user_id = ig_lookup.get("instagram_business_account", {}).get("id")

        if ig_user_id:
            print(f"Creating Instagram Reel Container for ID {ig_user_id}...")
            ig_media_url = f"https://graph.facebook.com/v19.0/{ig_user_id}/media"
            ig_payload = {
                "media_type": "REELS",
                "video_url": public_video_url,
                "caption": f"{req.title}\n\n{req.caption}\n\n#reels #gaming #asmowarlord",
                "share_to_feed": "true",
                "access_token": req.page_token
            }
            ig_res = requests.post(ig_media_url, data=ig_payload).json()
            print("Instagram Reel Container Result:", ig_res)
        else:
            print("Notice: Link Instagram in Graph API Explorer with instagram_content_publish to push directly to Reels tab.")

        # ----------------------------------------------------
        # PLATFORM 3: TIKTOK CONTENT POSTING API
        # ----------------------------------------------------
        if req.tiktok_token:
            print("Posting to TikTok Content Posting API...")
            tt_url = "https://open.tiktokapis.com/v2/post/publish/video/init/"
            tt_headers = {
                "Authorization": f"Bearer {req.tiktok_token}",
                "Content-Type": "application/json; charset=UTF-8"
            }
            tt_payload = {
                "post_info": {
                    "title": f"{req.title} #gaming #shorts #viral",
                    "privacy_level": "SELF_ONLY"  # Safe sandbox draft mode
                },
                "source_info": {
                    "source": "PULL_FROM_URL",
                    "video_url": public_video_url
                }
            }
            tt_res = requests.post(tt_url, headers=tt_headers, json=tt_payload).json()
            print("TikTok Result:", tt_res)

    except Exception as e:
        print(f"Pipeline error: {str(e)}")

@app.post("/api/schedule-reel")
def schedule_reel(req: ScheduleRequest, background_tasks: BackgroundTasks):
    background_tasks.add_task(process_and_publish_all, req)
    return {
        "status": "QUEUED",
        "message": "Real 9:16 video is being extracted and scheduled across all platforms!",
        "estimated_time": "35-50 seconds"
    }
