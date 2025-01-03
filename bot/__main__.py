from asyncio import create_task, all_tasks, gather, sleep as asleep
from aiofiles import open as aiopen
from pyrogram import idle
from pyrogram.filters import command, user
from os import execl, kill
from sys import executable
from signal import SIGKILL

from bot import bot, Var, bot_loop, sch, LOGS, ffQueue, ffLock, ffpids_cache, ff_queued
from bot.modules.up_posts import upcoming_animes
from bot.core.func_utils import clean_up, new_task

@bot.on_message(command('restart') & user(Var.ADMINS))
@new_task
async def restart_command(client, message):
    """Handle restart command."""
    rmessage = await message.reply('<i>Restarting...</i>')
    if sch.running:
        sch.shutdown(wait=False)
    await clean_up()
    if ffpids_cache:
        for pid in ffpids_cache:
            try:
                LOGS.info(f"Killing Process ID: {pid}")
                kill(pid, SIGKILL)
            except (OSError, ProcessLookupError):
                LOGS.error(f"Failed to kill process: {pid}")
                continue
    await (await create_subprocess_exec('python3', 'update.py')).wait()
    async with aiopen(".restartmsg", "w") as f:
        await f.write(f"{rmessage.chat.id}\n{rmessage.id}\n")
    execl(executable, executable, "-m", "bot")

async def restart():
    """Handle bot restart after the process reloads."""
    if ospath.isfile(".restartmsg"):
        with open(".restartmsg") as f:
            chat_id, msg_id = map(int, f)
        try:
            await bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text="<i>Restarted!</i>")
        except Exception as e:
            LOGS.error(e)

async def queue_loop():
    """Manage encoding queue."""
    LOGS.info("Queue Loop Started!")
    while True:
        if not ffQueue.empty():
            post_id = await ffQueue.get()
            await asleep(1.5)
            ff_queued[post_id].set()
            await asleep(1.5)
            async with ffLock:
                ffQueue.task_done()
        await asleep(10)

async def main():
    """Main bot loop."""
    sch.add_job(upcoming_animes, "cron", hour=0, minute=30)
    await bot.start()
    await restart()
    LOGS.info("Auto Anime Bot Started!")
    sch.start()
    bot_loop.create_task(queue_loop())
    await idle()
    LOGS.info("Auto Anime Bot Stopped!")
    await bot.stop()
    tasks = [task for task in all_tasks() if task is not asyncio.current_task()]
    for task in tasks:
        task.cancel()
    await clean_up()
    LOGS.info("Finished AutoCleanUp!")

if __name__ == '__main__':
    bot_loop.run_until_complete(main())
