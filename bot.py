import asyncio
import os
import time
import subprocess
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telethon import TelegramClient, events
from FastTelethon import ParallelTransferrer

# Credentials
API_ID = 38352841
API_HASH = "02962cfd6b25235c0ebb0baba6eb1e14"
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8844358381:AAFAloCuU6-N3NBgNipjUd3WlaL9l0fLqTY")

bot = TelegramClient("m3u8_uploader_bot", API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# Dummy Server for Render Free Tier
class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot Active!")

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), SimpleHTTPRequestHandler)
    server.serve_forever()

async def progress(current, total, event, start_time):
    now = time.time()
    diff = now - start_time
    if round(diff % 2) == 0 or current >= total:
        percentage = (current / total) * 100 if total > 0 else 0
        speed = current / diff if diff > 0 else 0
        text = (
            f"⚡ **M3U8 Parallel Engine Active**\n\n"
            f"📊 **Progress:** {percentage:.2f}%\n"
            f"🚀 **Speed:** {speed / (1024*1024):.2f} MB/s\n"
            f"📁 **Uploaded:** {current / (1024*1024):.1f} MB / {total / (1024*1024):.1f} MB"
        )
        try:
            await event.edit(text)
        except Exception:
            pass

@bot.on(events.NewMessage(pattern=r"^/start"))
async def start_handler(event):
    await event.reply(
        "👋 **M3U8 Video Downloader & Uploader Bot**\n\n"
        "Send command in this format:\n"
        "`/upload M3U8_URL | File Name | Target_Chat_ID`"
    )

@bot.on(events.NewMessage(pattern=r"^/upload"))
async def upload_handler(event):
    try:
        raw_text = event.message.text.split(" ", 1)[1]
        args = [a.strip() for a in raw_text.split("|")]
        m3u8_url = args[0]
        file_name = args[1] if len(args) > 1 else "video.mp4"
        target_chat = args[2] if len(args) > 2 else event.chat_id
    except Exception:
        await event.reply("❌ **Format:** `/upload M3U8_URL | File Name | Target_Chat_ID`")
        return

    if not file_name.endswith(".mp4"):
        file_name += ".mp4"

    status = await event.reply("📥 **[1/2] Downloading Stream via FFmpeg...**")
    temp_file = os.path.join(os.getcwd(), f"temp_{int(time.time())}.mp4")

    # Command with Timeout and Custom Classplus Headers
    cmd = (
        f'ffmpeg -y '
        f'-headers "Origin: https://web.classplusapp.com\r\nReferer: https://web.classplusapp.com/\r\nUser-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64)\r\n" '
        f'-i "{m3u8_url}" '
        f'-c copy -bsf:a aac_adtstoasc "{temp_file}"'
    )

    # Execute via Shell with 15-minute max timeout
    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=900)
    except asyncio.TimeoutError:
        await status.edit("❌ **Download Timed Out! (Stream takes too long or link died)**")
        return
    except Exception as e:
        await status.edit(f"❌ **FFmpeg Error:** `{e}`")
        return

    if not os.path.exists(temp_file) or os.path.getsize(temp_file) == 0:
        error_log = stderr.decode()[-300:] if stderr else "Unknown Error"
        await status.edit(f"❌ **Download Failed!**\n\n`{error_log}`")
        return

    await status.edit("⚡ **[2/2] Initializing Fast Parallel Upload to Telegram...**")

    uploader = ParallelTransferrer(bot, connection_count=4)
    start_time = time.time()

    async def prog_cb(current, total):
        await progress(current, total, status, start_time)

    try:
        input_file = await uploader.upload_file(temp_file, progress_callback=prog_cb)
        dest_id = int(target_chat) if str(target_chat).lstrip('-').isdigit() else target_chat
        
        await bot.send_file(
            dest_id,
            file=input_file,
            caption=f"🎥 **{file_name}**\n\n⚡ *Uploaded via M3U8 Bot*",
            supports_streaming=True
        )
        await status.edit("✅ **Video Uploaded Successfully!**")
    except Exception as e:
        await status.edit(f"❌ **Upload Error:** `{e}`")
    finally:
        if os.path.exists(temp_file):
            os.remove(temp_file)

if __name__ == "__main__":
    threading.Thread(target=run_web_server, daemon=True).start()
    print("Bot started successfully...")
    bot.run_until_disconnected()
