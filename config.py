import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your-secret-key-here'
    MONGO_URI = os.environ.get('MONGO_URI') or 'mongodb+srv://quantumvista:aJoWTicfsSkXwAaX@quantumvista.znokils.mongodb.net/'
    ALLOWED_WIFI_IPS = ['192.168.1.0/24', '10.0.0.0/8']  # Default college WiFi range