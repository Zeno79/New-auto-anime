from asyncio import gather, create_task, sleep as asleep, Event
from asyncio.subprocess import PIPE
from os import path as ospath
from aiofiles import open as aiopen
from aiofiles.os import remove as aioremove
from traceback import format_exc
from base64 import urlsafe_b64encode
from time import time
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot import bot, bot_loop, Var, ani_cache, ffQueue, ffLock, ff_queued
from .database import db
from .func_utils import encode, editMessage, sendMessage, convertBytes
from .text_utils import TextEditor
from .ffencoder import FFEncoder
from .tguploader import TgUploader
from .reporter import rep

btn_formatter = {
    '1080': '𝟭𝟬𝟴𝟬𝗽', 
    '720': '𝟳𝟮𝟬𝗽',
    '480': '𝟰𝟴𝟬𝗽',
    '360': '𝟯𝟲𝟬𝗽'
}

async def process_telegram_file(file_id, chat_id):
    try:
        # Download file from Telegram
        msg = await bot.get_messages(chat_id, file_id)
        file_path = await bot.download_media(msg.document or msg.video)

        # Start processing
        aniInfo = TextEditor(file_path)
        await aniInfo.load_anilist()
        post_msg = await bot.send_photo(
            Var.MAIN_CHANNEL,
            photo=await aniInfo.get_poster(),
            caption=await aniInfo.get_caption()
        )
        await asleep(1.5)
        stat_msg = await sendMessage(
            Var.MAIN_CHANNEL, f"‣ <b>File Name:</b> <b><i>{file_path}</i></b>\n\n<i>Queued to Encode...</i>"
        )

        # Queue and process file
        post_id = post_msg.id
        ffEvent = Event()
        ff_queued[post_id] = ffEvent
        if ffLock.locked():
            await editMessage(stat_msg, f"‣ <b>File Name:</b> <b><i>{file_path}</i></b>\n\n<i>Queued to Encode...</i>")
        await ffQueue.put(post_id)
        await ffEvent.wait()

        await ffLock.acquire()
        btns = []
        for qual in Var.QUALS:
            filename = await aniInfo.get_upname(qual)
            await editMessage(stat_msg, f"‣ <b>File Name:</b> <b><i>{filename}</i></b>\n\n<i>Encoding...</i>")
            try:
                out_path = await FFEncoder(stat_msg, file_path, filename, qual).start_encode()
            except Exception as e:
                await rep.report(f"Error: {e}, Retry!", "error")
                await stat_msg.delete()
                ffLock.release()
                return

            await editMessage(stat_msg, f"‣ <b>File Name:</b> <b><i>{filename}</i></b>\n\n<i>Uploading...</i>")
            try:
                msg = await TgUploader(stat_msg).upload(out_path, qual)
            except Exception as e:
                await rep.report(f"Error: {e}, Retry!", "error")
                await stat_msg.delete()
                ffLock.release()
                return

            msg_id = msg.id
            link = f"https://telegram.me/{(await bot.get_me()).username}?start={await encode('get-'+str(msg_id * abs(Var.FILE_STORE)))}"
            if post_msg:
                if len(btns) != 0 and len(btns[-1]) == 1:
                    btns[-1].insert(1, InlineKeyboardButton(f"{btn_formatter[qual]} - {convertBytes(msg.document.file_size)}", url=link))
                else:
                    btns.append([InlineKeyboardButton(f"{btn_formatter[qual]} - {convertBytes(msg.document.file_size)}", url=link)])
                await editMessage(post_msg, post_msg.caption.html if post_msg.caption else "", InlineKeyboardMarkup(btns))

        ffLock.release()
        await stat_msg.delete()
        await aioremove(file_path)
    except Exception as error:
        await rep.report(format_exc(), "error")

async def fetch_animes():
    await rep.report("Fetch Animes Started !!", "info")
    while True:
        await asleep(60)
        if ani_cache['fetch_animes']:
            for task in ani_cache['tasks']:
                await process_telegram_file(task['file_id'], task['chat_id'])
