import asyncio
import os
import time
import subprocess
from telethon import TelegramClient, events
from FastTelethon import ParallelTransferrer

# Credentials
API_ID = 38352841
API_HASH = "02962cfd6b25235c0ebb0baba6eb1e14"
BOT_TOKEN = "8844358381:AAFAloCuU6-N3NBgNipjUd3WlaL9l0fLqTY"  # BotFather se mila token yahan dalo

bot = TelegramClient("m3u8_uploader_bot", API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# Live Progress Bar
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

    # 1. Download Stream via FFmpeg
    cmd = [
        'ffmpeg', '-y',
        '-headers', 'Origin: https://web.classplusapp.com\r\nReferer: https://web.classplusapp.com/\r\n',
        '-i', m3u8_url,
        '-c', 'copy',
        '-bsf:a', 'aac_adtstoasc',
        temp_file
    ]

    proc = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    await proc.wait()

    if not os.path.exists(temp_file) or os.path.getsize(temp_file) == 0:
        await status.edit("❌ **Download Failed! Link Expired or Invalid.**")
        return

    await status.edit("⚡ **[2/2] Initializing Fast Parallel Upload to Telegram...**")

    # 2. Upload via Fast Multi-Worker Engine
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

print("Bot started successfully...")
bot.run_until_disconnected()
