from asyncio import sleep as asleep, Event
from bot import bot, Var, ani_cache, ffQueue, ffLock, ff_queued
from bot.core.func_utils import clean_up, sendMessage, editMessage
from bot.core.text_utils import TextEditor
from bot.core.ffencoder import FFEncoder
from bot.core.tguploader import TgUploader
from bot.core.reporter import rep
from traceback import format_exc
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# Button formatter for video qualities
btn_formatter = {
    '1080': '𝟭𝟬𝟴𝟬𝗽', 
    '720': '𝟳𝟮𝟬𝗽',
    '480': '𝟰𝟴𝟬𝗽',
    '360': '𝟯𝟲𝟬𝗽'
}

async def process_telegram_file(file_id, chat_id):
    """ Process a file from Telegram, encode it, and upload it back. """
    try:
        # Download file from Telegram
        msg = await bot.get_messages(chat_id, file_id)
        file_path = await bot.download_media(msg.document or msg.video)

        # Start processing the file (fetching anime details)
        ani_info = TextEditor(file_path)
        await ani_info.load_anilist()
        post_msg = await bot.send_photo(
            Var.MAIN_CHANNEL,
            photo=await ani_info.get_poster(),
            caption=await ani_info.get_caption()
        )
        await asleep(1.5)
        
        # Status message indicating file is queued for encoding
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
            filename = await ani_info.get_upname(qual)
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
    """ Periodically fetch anime data and process tasks. """
    await rep.report("Fetch Animes Started !!", "info")
    while True:
        await asleep(60)  # Wait 1 minute before checking for new tasks
        if ani_cache['fetch_animes']:
            for task in ani_cache['tasks']:
                await process_telegram_file(task['file_id'], task['chat_id'])

async def add_task(file_id, chat_id):
    """ Add a new task to the task cache for processing. """
    ani_cache['tasks'].append({'file_id': file_id, 'chat_id': chat_id})
    await rep.report(f"Task added for file {file_id} in chat {chat_id}", "info")
