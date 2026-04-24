import pyrogram
from pyrogram import Client, filters
from pyrogram.errors import UserAlreadyParticipant, InviteHashExpired
from pyrogram.types import Message

import time
import os
import threading
import re

# --------------- Configuration ---------------
bot_token = os.environ.get("TOKEN", "")
api_hash = os.environ.get("HASH", "")
api_id = os.environ.get("ID", "")
ss = os.environ.get("STRING", "")

bot = Client("mybot", api_id=api_id, api_hash=api_hash, bot_token=bot_token)
acc = Client("myacc", api_id=api_id, api_hash=api_hash, session_string=ss)

# --------------- Helper: custom progress callback ---------------
def make_progress_callback(status_filename):
    """Returns a progress function that writes the percentage to status_filename."""
    def progress(current, total):
        with open(status_filename, "w") as f:
            f.write(f"{current * 100 / total:.1f}%")
    return progress

# --------------- Download status checker (runs in thread) ---------------
def downstatus(statusfile, message):
    while True:
        if os.path.exists(statusfile):
            break
    time.sleep(3)
    while os.path.exists(statusfile):
        with open(statusfile, "r") as f:
            txt = f.read()
        try:
            bot.edit_message_text(message.chat.id, message.id, f"__Downloaded__ : **{txt}**")
            time.sleep(10)
        except:
            time.sleep(5)

# --------------- Upload status checker ---------------
def upstatus(statusfile, message):
    while True:
        if os.path.exists(statusfile):
            break
    time.sleep(3)
    while os.path.exists(statusfile):
        with open(statusfile, "r") as f:
            txt = f.read()
        try:
            bot.edit_message_text(message.chat.id, message.id, f"__Uploaded__ : **{txt}**")
            time.sleep(10)
        except:
            time.sleep(5)

# --------------- Default start command ---------------
@bot.on_message(filters.command(["start"]))
async def start(bot: Client, m: Message):
    await m.reply_text(
        "**I am a simple save restricted bot.**\n\n"
        "Send one or more message links (public/private) to clone/download here.\n"
        "Must join: @Bypass_restricted"
    )

# --------------- Bulk info (placeholder) ---------------
@bot.on_message(filters.command(["bulk"]))
async def bulk_info(bot: Client, m: Message):
    await m.reply_text("Send multiple links in one message – I will forward each one.")

# --------------- Main handler ---------------
@bot.on_message(filters.text)
def save(client: Client, message: Message):
    text = message.text

    # 1. Join private chat using invite link
    if "https://t.me/+" in text or "https://t.me/joinchat/" in text:
        try:
            with acc:
                acc.join_chat(text)
            bot.send_message(message.chat.id, "**Successfully joined the chat**", reply_to_message_id=message.id)
        except UserAlreadyParticipant:
            bot.send_message(message.chat.id, "**Already a member**", reply_to_message_id=message.id)
        except InviteHashExpired:
            bot.send_message(message.chat.id, "**Invite link has expired.**", reply_to_message_id=message.id)
        return  # stop here, no message links processed

    # 2. Extract all valid t.me message links (works with ?thread=... etc.)
    links = re.findall(r'https://t\.me/(?:c/)?[^/\s]+/\d+', text)
    if not links:
        return  # no links, do nothing

    total = len(links)
    bot.send_message(message.chat.id, f"Found {total} link(s). Processing…", reply_to_message_id=message.id)

    for i, link in enumerate(links, start=1):
        datas = link.split("/")
        msgid = int(datas[-1])

        # ----- PRIVATE CHAT (https://t.me/c/...) -----
        if "https://t.me/c/" in link:
            chatid = int("-100" + datas[-2])

            try:
                with acc:
                    msg = acc.get_messages(chatid, msgid)
                if msg is None:
                    bot.send_message(message.chat.id, f"❌ Message not found for link: {link}")
                    continue

                # If it's a text message, just forward the text
                if "text" in str(msg):
                    bot.send_message(message.chat.id, msg.text, entities=msg.entities,
                                     reply_to_message_id=message.id)
                    continue

                # --- Download & re-upload for media / files ---
                sid = f"{message.id}_{i}"
                down_file = f"{sid}downstatus.txt"
                up_file = f"{sid}upstatus.txt"

                # Start download
                smsg = bot.send_message(message.chat.id, f"⬇️ Downloading {i}/{total}...", reply_to_message_id=message.id)
                dosta = threading.Thread(target=downstatus, args=(down_file, smsg), daemon=True)
                dosta.start()
                file = acc.download_media(msg, progress=make_progress_callback(down_file))
                os.remove(down_file)

                # Start upload
                upsta = threading.Thread(target=upstatus, args=(up_file, smsg), daemon=True)
                upsta.start()

                # Send the media
                if "Document" in str(msg):
                    try:
                        with acc:
                            thumb = acc.download_media(msg.document.thumbs[0].file_id)
                    except:
                        thumb = None
                    bot.send_document(
                        message.chat.id, file,
                        thumb=thumb,
                        caption=msg.caption,
                        caption_entities=msg.caption_entities,
                        reply_to_message_id=message.id,
                        progress=make_progress_callback(up_file)
                    )
                    if thumb: os.remove(thumb)

                elif "Video" in str(msg):
                    try:
                        with acc:
                            thumb = acc.download_media(msg.video.thumbs[0].file_id)
                    except:
                        thumb = None
                    bot.send_video(
                        message.chat.id, file,
                        duration=msg.video.duration,
                        width=msg.video.width,
                        height=msg.video.height,
                        thumb=thumb,
                        caption=msg.caption,
                        caption_entities=msg.caption_entities,
                        reply_to_message_id=message.id,
                        progress=make_progress_callback(up_file)
                    )
                    if thumb: os.remove(thumb)

                elif "Animation" in str(msg):
                    bot.send_animation(message.chat.id, file, reply_to_message_id=message.id)

                elif "Sticker" in str(msg):
                    bot.send_sticker(message.chat.id, file, reply_to_message_id=message.id)

                elif "Voice" in str(msg):
                    bot.send_voice(message.chat.id, file, caption=msg.caption,
                                   reply_to_message_id=message.id)

                elif "Audio" in str(msg):
                    try:
                        with acc:
                            thumb = acc.download_media(msg.audio.thumbs[0].file_id)
                    except:
                        thumb = None
                    bot.send_audio(message.chat.id, file, caption=msg.caption,
                                   caption_entities=msg.caption_entities,
                                   reply_to_message_id=message.id)
                    if thumb: os.remove(thumb)

                elif "Photo" in str(msg):
                    bot.send_photo(message.chat.id, file, caption=msg.caption,
                                   caption_entities=msg.caption_entities,
                                   reply_to_message_id=message.id)

                # Cleanup
                os.remove(file)
                if os.path.exists(up_file):
                    os.remove(up_file)
                bot.delete_messages(message.chat.id, [smsg.id])

            except Exception as e:
                bot.send_message(message.chat.id, f"⚠️ Failed to process {link}: {e}")

        # ----- PUBLIC CHAT (https://t.me/username/...) -----
        else:
            username = datas[-2]
            try:
                msg = bot.get_messages(username, msgid)
                if msg is None:
                    bot.send_message(message.chat.id, f"❌ Message not found for link: {link}")
                    continue

                # Public chats – just resend using file IDs (no download)
                if "Document" in str(msg):
                    bot.send_document(message.chat.id, msg.document.file_id,
                                      caption=msg.caption,
                                      caption_entities=msg.caption_entities,
                                      reply_to_message_id=message.id)
                elif "Video" in str(msg):
                    bot.send_video(message.chat.id, msg.video.file_id,
                                   caption=msg.caption,
                                   caption_entities=msg.caption_entities,
                                   reply_to_message_id=message.id)
                elif "Animation" in str(msg):
                    bot.send_animation(message.chat.id, msg.animation.file_id,
                                       reply_to_message_id=message.id)
                elif "Sticker" in str(msg):
                    bot.send_sticker(message.chat.id, msg.sticker.file_id,
                                     reply_to_message_id=message.id)
                elif "Voice" in str(msg):
                    bot.send_voice(message.chat.id, msg.voice.file_id,
                                   caption=msg.caption,
                                   caption_entities=msg.caption_entities,
                                   reply_to_message_id=message.id)
                elif "Audio" in str(msg):
                    bot.send_audio(message.chat.id, msg.audio.file_id,
                                   caption=msg.caption,
                                   caption_entities=msg.caption_entities,
                                   reply_to_message_id=message.id)
                elif "text" in str(msg):
                    bot.send_message(message.chat.id, msg.text, entities=msg.entities,
                                     reply_to_message_id=message.id)
                elif "Photo" in str(msg):
                    bot.send_photo(message.chat.id, msg.photo.file_id,
                                   caption=msg.caption,
                                   caption_entities=msg.caption_entities,
                                   reply_to_message_id=message.id)

            except Exception as e:
                bot.send_message(message.chat.id, f"⚠️ Failed to process {link}: {e}")

        # Small delay to avoid hitting Telegram rate limits
        time.sleep(2)

# --------------- Run the bot ---------------
bot.run()
