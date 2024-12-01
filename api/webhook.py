import os
import logging
import random
import asyncio
from typing import Optional, Dict, Any
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import google.generativeai as genai
from youtube_transcript_api import YouTubeTranscriptApi
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response

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

class ProxyManager:
    _instance: Optional['ProxyManager'] = None
    _lock = asyncio.Lock()
    _proxies_lock = asyncio.Lock()  # Separate lock for proxy operations

    def __init__(self, proxy_list: str):
        """Initialize with comma-separated list of proxies"""
        self.proxies = []
        for proxy in proxy_list.split(','):
            try:
                ip, port, username, password = proxy.strip().split(':')
                self.proxies.append({
                    'http': f'http://{username}:{password}@{ip}:{port}',
                    'https': f'http://{username}:{password}@{ip}:{port}'
                })
            except Exception as e:
                logger.error(f"Invalid proxy format: {proxy} - {str(e)}")
                continue

        if not self.proxies:
            raise ValueError("No valid proxies provided")
        logger.info(f"Initialized ProxyManager with {len(self.proxies)} proxies")

    @classmethod
    async def get_instance(cls) -> 'ProxyManager':
        """Get or create singleton instance"""
        if not cls._instance:
            async with cls._lock:
                if not cls._instance:
                    proxy_list = os.environ.get("PROXY_LIST", "")
                    cls._instance = cls(proxy_list)
        return cls._instance

    async def get_random_proxy(self) -> Dict[str, str]:
        """Thread-safe random proxy selection"""
        async with self._proxies_lock:
            return random.choice(self.proxies)

class ApplicationManager:
    _instance: Optional[Application] = None
    _lock = asyncio.Lock()
    _initialized = False

    @classmethod
    async def get_instance(cls) -> Application:
        """Get or create singleton application instance"""
        if not cls._instance:
            async with cls._lock:
                if not cls._instance:
                    token = os.environ["TELEGRAM_BOT_TOKEN"]
                    cls._instance = Application.builder().token(token).build()
                    await cls._instance.initialize()
                    cls._instance.add_handler(CommandHandler("start", start))
                    cls._instance.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
                    cls._initialized = True
        return cls._instance

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
        max_retries = 10
        last_error = None

        # Get proxy manager instance
        proxy_manager = await ProxyManager.get_instance()

        # Try getting transcript with different proxies
        for attempt in range(max_retries):
            try:
                proxy = await proxy_manager.get_random_proxy()
                logger.info(f"Attempt {attempt + 1}: Using proxy {proxy['http']}")
                transcript = YouTubeTranscriptApi.get_transcript(video_id, proxies=proxy)
                transcript_text = " ".join([entry['text'] for entry in transcript])
                logger.info("Successfully fetched transcript")
                break
            except Exception as e:
                last_error = str(e)
                logger.warning(f"Attempt {attempt + 1} failed: {str(e)}")
                if attempt == max_retries - 1:
                    raise Exception(f"Failed to fetch transcript after {max_retries} attempts. Last error: {last_error}")

        chat_session = model.start_chat(history=[])
        prompt = f"Create a comprehensive tutorial based on the provided transcript. Begin by analyzing the content of the transcript thoroughly to identify its core themes, key concepts, and main points. Break down the information into logical sections or chapters that flow in a structured and coherent manner. Ensure each section focuses on one main idea or topic to maintain clarity and engagement. Use simple and precise language to explain complex ideas. Start each section with an overview and end with a summary or key takeaways. Conclude with a recap of the entire tutorial, highlighting the main points and encouraging readers to apply their newfound knowledge. Include actionable steps or exercises at the end to reinforce learning and provide practical applications. Ensure the tutorial is easy to navigate by using subheadings and providing a logical progression of topics. Use plaintext formatting only. Do not format the headings or subheadings. Use plain numbered lists. Transcript: {transcript_text}"
        response = chat_session.send_message(prompt)
        return response.text
    except Exception as e:
        error_msg = f"Error processing request! \n\n{str(e)}"
        logger.error(error_msg)
        return error_msg

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command"""
    welcome_message = (
        "👋 Hi there! I create tutorials from YouTube videos.\n\n"
        "Simply send me a YouTube URL and I'll do the rest!"
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

@app.post("/api/webhook")
async def webhook(request: Request):
    """Handle incoming webhook requests from Telegram"""
    try:
        data = await request.json()
        logger.info("Received webhook data")

        # Get singleton application instance
        application = await ApplicationManager.get_instance()

        # Process the update
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
        
        logger.info("Successfully processed webhook update")
        return Response(status_code=200)
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        # Return 500 to allow Telegram to retry
        return Response(status_code=500)

@app.get("/api/webhook")
async def webhook_info():
    """Health check endpoint for webhook"""
    return {"status": "ok"}

@app.get("/")
async def root():
    """Root endpoint for health checking"""
    return {"status": "Bot webhook is running"}