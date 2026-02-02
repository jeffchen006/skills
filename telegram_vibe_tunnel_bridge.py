import logging
from telegram import Update, WebAppInfo, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import sys

# --- CONFIGURATION ---
BOT_TOKEN = "8559425055:AAH2SNChU2RElHJ723Eo_LK_SO-LLYLy_7k"
# Paste your generated Vibe Tunnel URL here (e.g., https://cool-tunnel.vibetunnel.sh)
VIBE_TUNNEL_URL = "https://jeffs-macbook-pro.tailf973f.ts.net/" 

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends the launcher button."""
    user = update.effective_user
    
    # Create a button that opens the Web App
    keyboard = [
        [InlineKeyboardButton(
            text="💻 Open Codex Terminal", 
            web_app=WebAppInfo(url=VIBE_TUNNEL_URL)
        )]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"Hi {user.first_name}! \n\n"
        "Your Codex session is ready. Click below to access the full UI.",
        reply_markup=reply_markup
    )

async def notify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    (Optional) Call this command manually or via script to ping yourself.
    Usage: /notify Job Finished!
    """
    keyboard = [[InlineKeyboardButton("View Result", web_app=WebAppInfo(url=VIBE_TUNNEL_URL))]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message = " ".join(context.args) if context.args else "Process Update"
    await update.message.reply_text(f"🔔 <b>NOTIFICATION:</b>\n{message}", parse_mode="HTML", reply_markup=reply_markup)

if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("notify", notify))
    
    print("Vibe Bridge Bot is running...")
    app.run_polling()