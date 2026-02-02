import logging
import asyncio
import os
import pty
import subprocess
import re
import struct
import fcntl
import termios
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

# --- CONFIGURATION ---
BOT_TOKEN = "8559425055:AAH2SNChU2RElHJ723Eo_LK_SO-LLYLy_7k" 
ALLOWED_USER_ID = 5143179617       # REPLACE with your numeric ID
CODEX_COMMAND = ["codex", "repl"] # Your command
OUTPUT_DEBOUNCE_SEC = 0.35
MAX_MESSAGE_CHARS = 3500

# --- GLOBAL STATE ---
master_fd = None 
process = None
output_buffer = ""
flush_task = None
buffer_lock = asyncio.Lock()
last_chat_id = None

# Regex to clean up TUI formatting artifacts
ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

# Terminal queries to ignore/auto-reply
QUERY_CURSOR = b'\x1b[6n'
ANSWER_CURSOR = b'\x1b[1;1R'

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)

def set_winsize(fd, row, col, xpix=0, ypix=0):
    """Tell the PTY that it has a specific size (prevent TUI crash)."""
    winsize = struct.pack("HHHH", row, col, xpix, ypix)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)

def chunk_text(text, size):
    for i in range(0, len(text), size):
        yield text[i:i + size]

async def flush_output(bot, chat_id):
    global output_buffer
    async with buffer_lock:
        text = output_buffer
        output_buffer = ""

    text = text.strip()
    if not text:
        return

    for chunk in chunk_text(text, MAX_MESSAGE_CHARS):
        await bot.send_message(
            chat_id=chat_id,
            text=f"```\n{chunk}\n```",
            parse_mode='Markdown'
        )

async def schedule_flush(bot, chat_id):
    global flush_task, last_chat_id
    last_chat_id = chat_id

    if flush_task and not flush_task.done():
        flush_task.cancel()

    async def delayed_flush():
        try:
            await asyncio.sleep(OUTPUT_DEBOUNCE_SEC)
            await flush_output(bot, last_chat_id)
        except asyncio.CancelledError:
            return

    flush_task = asyncio.create_task(delayed_flush())

async def read_from_pty(bot, chat_id):
    global master_fd
    try:
        data = os.read(master_fd, 4096)
        if not data: return

        # Handle "Where is cursor?" query
        if QUERY_CURSOR in data:
            os.write(master_fd, ANSWER_CURSOR)
            data = data.replace(QUERY_CURSOR, b'')

        raw_text = data.decode('utf-8', errors='replace')

        # Clean ANSI codes
        clean_text = ANSI_ESCAPE.sub('', raw_text)

        if clean_text:
            async with buffer_lock:
                global output_buffer
                output_buffer += clean_text
            await schedule_flush(bot, chat_id)
    except OSError:
        pass

async def start_codex_process(update, context):
    global master_fd, process
    
    master_fd, slave_fd = pty.openpty()
    
    # CRITICAL FIX: Set terminal size to 80x24 so TUI doesn't panic
    set_winsize(master_fd, 24, 80)
    
    # Set TERM to standard xterm
    env = os.environ.copy()
    env["TERM"] = "xterm-256color" 
    
    process = subprocess.Popen(
        CODEX_COMMAND,
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        start_new_session=True, 
        shell=False,
        close_fds=True,
        env=env
    )
    
    os.close(slave_fd)
    logging.info("Codex process started with fixed window size (80x24).")
    
    loop = asyncio.get_running_loop()
    loop.add_reader(master_fd, lambda: asyncio.create_task(read_from_pty(context.bot, update.effective_chat.id)))

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ALLOWED_USER_ID: return

    text = update.message.text
    global master_fd, process

    if master_fd is None or (process and process.poll() is not None):
        await update.message.reply_text("⚙️ Starting Codex...")
        await start_codex_process(update, context)

    if master_fd:
        try:
            input_bytes = (text + "\n").encode('utf-8')
            os.write(master_fd, input_bytes)
        except OSError as e:
            await update.message.reply_text(f"❌ Error: {e}")

if __name__ == '__main__':
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    msg_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message)
    application.add_handler(msg_handler)
    
    print("Bot is running...")
    application.run_polling()
