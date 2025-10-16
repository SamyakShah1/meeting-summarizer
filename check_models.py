import os
import sqlite3
from datetime import datetime
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv
import whisper
import google.generativeai as genai
from moviepy.editor import VideoFileClip

# Load environment variables from your .env file
load_dotenv()

# Initialize the Flask application
app = Flask(__name__)

# --- Database Setup ---
DB_FILE = "summaries.db"

def init_db():
    """Initializes the SQLite database and creates the table if it doesn't exist."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            transcript TEXT NOT NULL,
            summary TEXT NOT NULL,
            timestamp DATETIME NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

# --- Google Gemini Configuration ---
google_api_key = os.getenv("GOOGLE_API_KEY")
if not google_api_key:
    raise ValueError("Google API key not found. Make sure it's in your .env file.")
genai.configure(api_key=google_api_key)

# --- Local Whisper Model Loading ---
print("Loading Whisper model...")
try:
    whisper_model = whisper.load_model("base")
    print("Whisper model loaded successfully.")
except Exception as e:
    print(f"Error loading whisper model: {e}")
    whisper_model = None

# Create a directory to temporarily store uploaded files
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

@app.route('/')
def index():
    """Renders the main upload page and displays the summary history."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row # This allows accessing columns by name
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM summaries ORDER BY timestamp DESC")
    summaries = cursor.fetchall()
    conn.close()
    return render_template('index.html', summaries=summaries)

@app.route('/summarize', methods=['POST'])
def summarize_handler():
    filepath = None
    audio_filepath = None

    if 'file' not in request.files:
        return jsonify({"error": "No file part in the request"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400

    try:
        if file:
            filename = file.filename
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            # --- Video File Handling ---
            if filename.lower().endswith(('.mp4', '.mov', '.avi', '.mkv')):
                print(f"Video file detected: {filename}. Extracting audio...")
                video_clip = VideoFileClip(filepath)
                audio_filepath = os.path.join(app.config['UPLOAD_FOLDER'], "extracted_audio.mp3")
                video_clip.audio.write_audiofile(audio_filepath)
                video_clip.close()
                processing_path = audio_filepath
            else:
                processing_path = filepath
            
            # --- ASR: Local Transcription using Whisper ---
            print("Starting transcription...")
            result = whisper_model.transcribe(processing_path, fp16=False)
            transcript_text = result["text"]
            print("Transcription complete.")

            # --- LLM: Summarization using Google Gemini ---
            print("Starting summarization...")
            
            # Get the custom prompt from the form data
            user_prompt = request.form.get('prompt', 'Summarize the following transcript:') # Default prompt if none is provided
            
            # Combine the user's prompt with the transcript
            full_prompt = f"{user_prompt}\n\nTranscript:\n---\n{transcript_text}"
            
            gemini_model = genai.GenerativeModel('gemini-flash-latest')
            response = gemini_model.generate_content(full_prompt)
            summary_text = response.text
            print("Summarization complete.")

            # --- Save to Database ---
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO summaries (filename, transcript, summary, timestamp) VALUES (?, ?, ?, ?)",
                (filename, transcript_text, summary_text, datetime.now())
            )
            conn.commit()
            conn.close()

            return jsonify({
                "transcript": transcript_text,
                "summary": summary_text
            }), 200

    except Exception as e:
        print(f"An error occurred: {e}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500
    
    finally:
        # --- Cleanup Temporary Files ---
        if filepath and os.path.exists(filepath):
            os.remove(filepath)
        if audio_filepath and os.path.exists(audio_filepath):
            os.remove(audio_filepath)

if __name__ == '__main__':
    init_db() # Initialize the database when the app starts
    app.run(debug=True, port=5000)