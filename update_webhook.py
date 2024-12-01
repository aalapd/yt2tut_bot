import os
import sys
import requests
from dotenv import load_dotenv
from urllib.parse import urlparse, urljoin

def is_valid_url(url: str) -> bool:
    """Validate URL format"""
    try:
        result = urlparse(url)
        return all([result.scheme in ['http', 'https'], result.netloc])
    except:
        return False

def update_webhook(new_url: str) -> None:
    """Delete existing webhook and set new one"""
    # Load token
    load_dotenv()
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    
    if not token:
        print("Error: TELEGRAM_BOT_TOKEN not found in environment variables")
        sys.exit(1)

    # Validate URL
    if not is_valid_url(new_url):
        print("Error: Invalid URL format")
        sys.exit(1)

    base_url = f"https://api.telegram.org/bot{token}"
    
    # Delete existing webhook
    delete_response = requests.get(f"{base_url}/deleteWebhook")
    if not delete_response.ok:
        print("Error: Failed to delete existing webhook")
        sys.exit(1)

    # Set new webhook
    webhook_url = urljoin(new_url.rstrip('/'), '/api/webhook')
    set_response = requests.get(f"{base_url}/setWebhook?url={webhook_url}")
    
    if not set_response.ok:
        print(f"Error: Failed to set webhook: {set_response.json().get('description', 'Unknown error')}")
        sys.exit(1)

    # Verify webhook
    verify_response = requests.get(f"{base_url}/getWebhookInfo")
    if verify_response.ok:
        webhook_info = verify_response.json()
        if webhook_info['ok'] and webhook_info['result']['url'] == webhook_url:
            print(f"Success: Webhook updated to {webhook_url}")
        else:
            print("Error: Webhook verification failed")
            sys.exit(1)
    else:
        print("Error: Could not verify webhook")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python update_webhook.py <new_url>")
        sys.exit(1)
    
    update_webhook(sys.argv[1])