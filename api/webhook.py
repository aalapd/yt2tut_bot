# api/webhook.py
import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import google.generativeai as genai
from youtube_transcript_api import YouTubeTranscriptApi
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI
app = FastAPI(docs_url=None, redoc_url=None)

# Load environment variables
load_dotenv()

# Configure proxy settings
PROXY_URL = "socks5h://warp:1080"  # Changed from http to socks5h
PROXIES = {
    "http": PROXY_URL,
    "https": PROXY_URL
}

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
        # Add debug logging
        logger.info(f"Attempting to fetch transcript for video {video_id} using proxy {PROXY_URL}")
        
        transcript = YouTubeTranscriptApi.get_transcript(
            video_id, 
            proxies=PROXIES
        )
        
        logger.info("Successfully fetched transcript")
        transcript_text = " ".join([entry['text'] for entry in transcript])
        
        chat_session = model.start_chat(history=[])
        prompt = f"Create a comprehensive tutorial based on the provided transcript..."  # Your existing prompt
        response = chat_session.send_message(prompt)
        return response.text
    except Exception as e:
        logger.error(f"Error in get_transcript_and_tutorial: {str(e)}")
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

# Create a function to get or create the application
async def get_application():
    """Get or create the Telegram application instance"""
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    
    # Create new application instance
    app = Application.builder().token(token).build()
    
    # Initialize the application
    await app.initialize()
    
    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    
    return app

# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all incoming HTTP requests"""
    logger.info(f"Incoming request: {request.method} {request.url}")
    try:
        response = await call_next(request)
        logger.info(f"Response status: {response.status_code}")
        return response
    except Exception as e:
        logger.error(f"Request failed: {str(e)}")
        raise

# Webhook endpoints
@app.post("/api/webhook")
async def webhook(request: Request):
    """Handle incoming webhook requests from Telegram"""
    try:
        data = await request.json()
        logger.info("Received webhook data")
        
        # Get initialized application instance
        application = await get_application()
        
        # Process the update
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
        
        logger.info("Successfully processed webhook update")
        return Response(status_code=200)
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        return Response(status_code=200)

@app.get("/api/webhook")
async def webhook_info():
    """Health check endpoint for webhook"""
    return {"status": "ok"}

@app.get("/")
async def root():
    """Root endpoint for health checking"""
    return {"status": "Bot webhook is running"}