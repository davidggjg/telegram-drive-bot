import os, asyncio, tempfile
from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.types import Message
from drive import upload_stream_to_drive, check_storage

load_dotenv()

API_ID   = int(os.getenv('API_ID'))
API_HASH = os.getenv('API_HASH')
TOKEN    = os.getenv('TELEGRAM_TOKEN')
ALLOWED  = [int(x) for x in os.getenv('ALLOWED_USERS', '').split(',') if x]

app = Client("bot_session", api_id=API_ID, api_hash=API_HASH, bot_token=TOKEN)

def is_allowed(uid): return not ALLOWED or uid in ALLOWED

def format_size(b):
    if b < 1e6: return f"{b/1e3:.1f} KB"
    if b < 1e9: return f"{b/1e6:.1f} MB"
    return f"{b/1e9:.2f} GB"

def format_time(s):
    if s < 60: return f"{int(s)}ש׳"
    if s < 3600: return f"{int(s//60)}ד׳ {int(s%60)}ש׳"
    return f"{int(s//3600)}ש {int((s%3600)//60)}ד׳"

@app.on_message(filters.command("start"))
async def start(client, message: Message):
    await message.reply_text(
        "🚀 **ברוך הבא לבוט העלאת קבצים!**\n\n"
        "שלח לי כל קובץ ואני אעלה אותו לגוגל דרייב.\n"
        "✅ תמיכה בקבצים עד **4GB**\n\n"
        "📊 /storage - בדוק אחסון"
    )

@app.on_message(filters.command("storage"))
async def storage_cmd(client, message: Message):
    msg = await message.reply_text("⏳ בודק אחסון...")
    data = check_storage()
    bar = '🟩' * int(data['percent']/5) + '⬜' * (20 - int(data['percent']/5))
    emoji = '✅' if data['percent'] < 80 else '⚠️' if data['percent'] < 95 else '🔴'
    await msg.edit_text(
        f"{emoji} **מצב אחסון:**\n\n{bar}\n\n"
        f"📦 בשימוש: `{data['used_gb']} GB`\n"
        f"✅ פנוי: `{data['free_gb']} GB`\n"
        f"💾 סה\"כ: `{data['total_gb']} GB`\n"
        f"📊 `{data['percent']}%` מלא"
    )

@app.on_message(filters.document | filters.photo | filters.video | filters.audio | filters.voice)
async def handle_file(client, message: Message):
    if not is_allowed(message.from_user.id):
        await message.reply_text("⛔ אין לך הרשאה.")
        return

    msg = message
    tg_file, filename, mimetype = None, None, 'application/octet-stream'

    if msg.document:
        tg_file = msg.document
        filename = msg.document.file_name or 'קובץ'
        mimetype = msg.document.mime_type or mimetype
    elif msg.photo:
        tg_file = msg.photo
        filename = f"תמונה_{msg.id}.jpg"
        mimetype = 'image/jpeg'
    elif msg.video:
        tg_file = msg.video
        filename = msg.video.file_name or f"וידאו_{msg.id}.mp4"
        mimetype = msg.video.mime_type or 'video/mp4'
    elif msg.audio:
        tg_file = msg.audio
        filename = msg.audio.file_name or f"שמע_{msg.id}.mp3"
        mimetype = msg.audio.mime_type or 'audio/mpeg'
    elif msg.voice:
        tg_file = msg.voice
        filename = f"הקלטה_{msg.id}.ogg"
        mimetype = 'audio/ogg'

    size_str = format_size(tg_file.file_size)
    status = await msg.reply_text(
        f"⬇️ **מוריד קובץ...**\n📄 `{filename}`\n📦 {size_str}"
    )

    tmp_path = None
    try:
        storage = check_storage()
        if storage['percent'] > 98:
            await status.edit_text("🔴 **הדרייב מלא!**")
            return

        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[-1]) as tmp:
            tmp_path = tmp.name

        start_time = asyncio.get_event_loop().time()
        last_update = [0]

        async def progress(current, total):
            now = asyncio.get_event_loop().time()
            if now - last_update[0] < 3:
                return
            last_update[0] = now
            pct = int(current / total * 100)
            bar = '🟩' * (pct//10) + '⬜' * (10 - pct//10)
            elapsed = now - start_time
            speed = current / elapsed if elapsed > 0 else 0
            remaining = (total - current) / speed if speed > 0 else 0
            await status.edit_text(
                f"⬇️ **מוריד...**\n{bar} {pct}%\n"
                f"📦 {format_size(current)} / {format_size(total)}\n"
                f"⚡ {format_size(int(speed))}/ש׳\n"
                f"⏱ נותר: {format_time(remaining)}"
            )

        await msg.download(tmp_path, progress=progress)

        await status.edit_text(
            f"⬆️ **מעלה לדרייב...**\n📄 `{filename}`\n📦 {size_str}"
        )

        upload_start = asyncio.get_event_loop().time()
        last_pct = [-1]

        def sync_progress(pct):
            if pct - last_pct[0] < 10:
                return
            last_pct[0] = pct
            bar = '🟩' * (pct//10) + '⬜' * (10 - pct//10)
            asyncio.run_coroutine_threadsafe(
                status.edit_text(f"⬆️ **מעלה לדרייב...**\n{bar} {pct}%\n📄 `{filename}`"),
                asyncio.get_event_loop()
            )

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, lambda: upload_stream_to_drive(tmp_path, filename, mimetype, sync_progress)
        )

        await status.edit_text(
            f"✅ **עלה בהצלחה!**\n\n"
            f"📄 `{result['name']}`\n"
            f"📦 {size_str}\n\n"
            f"🔗 [פתח בדרייב]({result['webViewLink']})",
            disable_web_page_preview=True
        )

    except Exception as e:
        await status.edit_text(f"❌ **שגיאה:**\n`{str(e)}`")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

app.run()
