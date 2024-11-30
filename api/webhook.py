# api/webhook.py
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import google.generativeai as genai
from youtube_transcript_api import YouTubeTranscriptApi
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response
import json
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI
app = FastAPI(docs_url=None, redoc_url=None)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"Incoming request: {request.method} {request.url}")
    try:
        response = await call_next(request)
        logger.info(f"Response status: {response.status_code}")
        return response
    except Exception as e:
        logger.error(f"Request failed: {str(e)}")
        raise

# Load environment variables
load_dotenv()

# Configure Google AI
genai.configure(api_key=os.environ["GEMINI_API_KEY"])

# Configure the AI model
generation_config = {
    "temperature": 0.5,
    "top_p": 0.95,
    "top_k": 40,
    "max_output_tokens": 8192,
    "response_mime_type": "text/plain",
}

model = genai.GenerativeModel(
    model_name="gemini-1.5-flash-8b",
    generation_config=generation_config,
)

def extract_video_id(url: str) -> str:
    """Extract the video ID from a YouTube URL."""
    parsed_url = urlparse(url)
    
    if parsed_url.netloc == 'youtu.be':
        return parsed_url.path[1:]
    
    if parsed_url.netloc in ('youtube.com', 'www.youtube.com'):
        if parsed_url.path == '/watch':
            return parse_qs(parsed_url.query)['v'][0]
        elif parsed_url.path.startswith(('/embed/', '/v/')):
            return parsed_url.path.split('/')[2]
    
    raise ValueError("Invalid YouTube URL. Please check and try again.")

async def get_transcript_and_tutorial(url: str) -> str:
    """Fetch transcript and generate tutorial"""
    try:
        video_id = extract_video_id(url)
        transcript = YouTubeTranscriptApi.get_transcript(video_id)
        transcript_text = " ".join([entry['text'] for entry in transcript])
        
        chat_session = model.start_chat(history=[])
        prompt = f"Create a comprehensive tutorial based on the provided transcript. Begin by analyzing the content of the transcript thoroughly to identify its core themes, key concepts, and main points. Break down the information into logical sections or chapters that flow in a structured and coherent manner. Ensure each section focuses on one main idea or topic to maintain clarity and engagement. Use simple and precise language to explain complex ideas. Start each section with an overview of the objectives and end with a summary or key takeaways. Include actionable steps or exercises after each topic to reinforce learning and provide practical applications. Conclude with a recap of the entire tutorial, highlighting the main points and encouraging readers to apply their newfound knowledge. Ensure the tutorial is easy to navigate by using subheadings and providing a logical progression of topics. Use plain formatting only. Transcript: {transcript_text}"
        response = chat_session.send_message(prompt)
        
        return response.text
    except Exception as e:
        return f"Error processing request! \n\n{str(e)}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command"""
    welcome_message = (
        "👋 Welcome! I create tutorials from YouTube videos.\n\n"
        "Simply send me a YouTube URL, and I'll:\n"
        "1. Extract the video transcript\n"
        "2. Generate an actionable tutorial\n\n"
        "Try it now by sending a YouTube URL!"
    )
    await update.message.reply_text(welcome_message)

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle URL messages"""
    status_message = await update.message.reply_text("Processing your request... This may take a minute. 🐵")
    
    try:
        url = update.message.text
        tutorial = await get_transcript_and_tutorial(url)
        
        max_length = 4000
        chunks = [tutorial[i:i+max_length] for i in range(0, len(tutorial), max_length)]
        
        await status_message.delete()
        
        for chunk in chunks:
            await update.message.reply_text(chunk)
    except Exception as e:
        await status_message.edit_text(f"Error: {str(e)}")

# Initialize the bot application
application = Application.builder().token(os.environ["TELEGRAM_BOT_TOKEN"]).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))

# Add a root route handler
@app.get("/")
async def root():
    return {"status": "Bot webhook is running"}

@app.post("/api/webhook")
async def webhook(request: Request):
    """Handle incoming webhook requests from Telegram"""
    try:
        data = await request.json()
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
        return Response(status_code=200)
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        return Response(status_code=200)  # Still return 200 to prevent Telegram from retrying

@app.get("/api/webhook")
async def webhook_info():
    """Health check endpoint"""
    return {"status": "ok"}