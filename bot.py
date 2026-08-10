import asyncio
import os
import time
import threading
import requests
import m3u8
from concurrent.futures import ThreadPoolExecutor
from http.server import HTTPServer, BaseHTTPRequestHandler
from telethon import TelegramClient, events
from FastTelethon import ParallelTransferrer

# Credentials
API_ID = 38352841
API_HASH = "02962cfd6b25235c0ebb0baba6eb1e14"
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8844358381:AAFAloCuU6-N3NBgNipjUd3WlaL9l0fLqTY")

bot = TelegramClient("m3u8_uploader_bot", API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# Dummy Server for Render Keep-Alive
class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot Active 24/7!")

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), SimpleHTTPRequestHandler)
    server.serve_forever()

# Upload Progress Bar Callback
async def upload_progress(current, total, event, start_time):
    now = time.time()
    diff = now - start_time
    if round(diff % 2) == 0 or current >= total:
        percentage = (current / total) * 100 if total > 0 else 0
        speed = current / diff if diff > 0 else 0
        text = (
            f"⚡ **Telegram Upload Active**\n\n"
            f"📊 **Progress:** {percentage:.2f}%\n"
            f"🚀 **Speed:** {speed / (1024*1024):.2f} MB/s\n"
            f"📁 **Uploaded:** {current / (1024*1024):.1f} MB / {total / (1024*1024):.1f} MB"
        )
        try:
            await event.edit(text)
        except Exception:
            pass

def download_segment(args):
    url, index, headers = args
    try:
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code == 200:
            return index, res.content
    except Exception:
        pass
    return index, None

@bot.on(events.NewMessage(pattern=r"^/start"))
async def start_handler(event):
    await event.reply(
        "👋 **M3U8 Downloader & Uploader Bot**\n\n"
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

    status = await event.reply("🔎 **[1/2] Fetching Stream Playlist...**")
    temp_file = os.path.join(os.getcwd(), f"temp_{int(time.time())}.mp4")

    headers = {
        'Origin': 'https://web.classplusapp.com',
        'Referer': 'https://web.classplusapp.com/',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
    }

    # 1. Parse M3U8 Playlist
    try:
        playlist = m3u8.load(m3u8_url, headers=headers)
        segments = playlist.segments
        
        if not segments and playlist.playlists:
            # Handle Master Playlist
            variant_url = playlist.playlists[0].absolute_uri
            playlist = m3u8.load(variant_url, headers=headers)
            segments = playlist.segments

        if not segments:
            await status.edit("❌ **Invalid M3U8 Stream or URL Expired!**")
            return

        total_segments = len(segments)
        await status.edit(f"📥 **[1/2] Downloading {total_segments} Segments in Parallel...**")

        segment_urls = [(seg.absolute_uri, i, headers) for i, seg in enumerate(segments)]
        downloaded_chunks = {}

        # 2. Multi-threaded parallel downloading (16 Workers)
        loop = asyncio.get_event_loop()
        start_dl_time = time.time()
        
        with ThreadPoolExecutor(max_workers=16) as executor:
            futures = [loop.run_in_executor(None, download_segment, arg) for arg in segment_urls]
            
            done_count = 0
            for future in asyncio.as_completed(futures):
                idx, content = await future
                if content:
                    downloaded_chunks[idx] = content
                done_count += 1

                if time.time() - start_dl_time > 3 or done_count == total_segments:
                    start_dl_time = time.time()
                    progress_pct = (done_count / total_segments) * 100
                    try:
                        await status.edit(
                            f"🚀 **[1/2] Downloading Stream...**\n"
                            f"📊 **Progress:** {progress_pct:.1f}% ({done_count}/{total_segments} chunks)"
                        )
                    except Exception:
                        pass

        # 3. Merge segments into single file
        with open(temp_file, "wb") as f:
            for i in range(total_segments):
                if i in downloaded_chunks:
                    f.write(downloaded_chunks[i])

    except Exception as e:
        await status.edit(f"❌ **Stream Download Error:** `{e}`")
        return

    if not os.path.exists(temp_file) or os.path.getsize(temp_file) < 100 * 1024:
        await status.edit("❌ **Download Failed! Empty File Generated.**")
        return

    await status.edit("⚡ **[2/2] Initializing Fast Parallel Upload to Telegram...**")

    # 4. Fast Upload via Parallel Sockets
    uploader = ParallelTransferrer(bot, connection_count=4)
    start_time = time.time()

    async def prog_cb(current, total):
        await upload_progress(current, total, status, start_time)

    try:
        input_file = await uploader.upload_file(temp_file, progress_callback=prog_cb)
        dest_id = int(target_chat) if str(target_chat).lstrip('-').isdigit() else target_chat
        
        await bot.send_file(
            dest_id,
            file=input_file,
            caption=f"🎥 **{file_name}**\n\n⚡ *Uploaded via Multi-Worker Engine*",
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
