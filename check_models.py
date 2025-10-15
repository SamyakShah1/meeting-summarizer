import os
from dotenv import load_dotenv
import google.generativeai as genai

# Load environment variables to get your key
load_dotenv()

# Configure the API with your key
google_api_key = os.getenv("GOOGLE_API_KEY")
if not google_api_key:
    raise ValueError("Google API key not found in .env file.")
genai.configure(api_key=google_api_key)

print("Fetching available models...\n")

# List all models and filter for the ones that support 'generateContent'
for model in genai.list_models():
    if 'generateContent' in model.supported_generation_methods:
        print(model.name)