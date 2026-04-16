import os
import requests
import sounddevice as sd
import queue
import json
import subprocess
from vosk import Model, KaldiRecognizer
import re

TOKEN_FILE = "device_token.txt"

# ---------------------------
# CONFIG
# ---------------------------
API_URL = "http://13.233.245.117:3000/api/messages/device"
CRED_FILE = "cred.txt"

# 🔥 YOUR WORKING AUDIO DEVICE
AUDIO_DEVICE = "plughw:2,0"

HEADERS = {
    "X-Device-Token": "1776232357931",
    "Content-Type": "application/json"
}

# ---------------------------
# AUTH TOKEN HANDLING
# ---------------------------
#def get_auth_token():
#    if not os.path.exists(CRED_FILE):
#        open(CRED_FILE, "w").close()
#
#    with open(CRED_FILE, "r") as f:
#       lines = f.readlines()
#
#    for line in lines:
#        if line.startswith("auth_token="):
#            token = line.strip().split("=", 1)[1]
#            if token:
#                return token
#
#    token = input("Enter your auth token: ").strip()
#
#    with open(CRED_FILE, "w") as f:
#        f.write(f"auth_token={token}")
#
#    return token


def get_device_token():
    if not os.path.exists(TOKEN_FILE):
        open(TOKEN_FILE, "w").close()

    with open(TOKEN_FILE, "r") as f:
        token = f.read().strip()

    if token:
        return token

    # If no token, ask user
    token = input("Enter Device Token: ").strip()

    with open(TOKEN_FILE, "w") as f:
        f.write(token)

    return token


def update_device_token():
    print("\n DEVICE REGISTRATION MODE")

    new_token = input("Enter NEW Device Token: ").strip()

    with open(TOKEN_FILE, "w") as f:
        f.write(new_token)

    HEADERS["X-Device-Token"] = new_token  # ✅ update live

    speak("Device registered successfully")

    print("Device token updated successfully!")
    
    

# ---------------------------
# GPIO BUTTON SETUP
# ---------------------------
import RPi.GPIO as GPIO

BUTTON_PIN = 17  # GPIO17 (Pin 11)

def setup_button():
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

def check_button():
    if GPIO.input(BUTTON_PIN) == GPIO.LOW:
        print(" Button pressed!")
        speak("entering registration mode")
        update_device_token()
        
        import time
        time.sleep(1)   # debouncing delay


# ---------------------------
# TEXT TO SPEECH (FIXED)
# ---------------------------

def clean_text(text):
    # Remove *, #, _, `, etc.
    text = re.sub(r'[*_#`~]', '', text)
    
    # Replace new line with pauses
    text = text.replace("\n", ". ")

    # Remove extra spaces
    text = re.sub(r'\s+', ' ', text)
    
    text = re.sub(r'[^\w\s.,!?]', '',text)

    return text.strip()


def speak(text):
    text = clean_text(text)
    print("System:", text)

    sentences = text.split(".")
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        try:
            # Generate speech and send to the correct audio device
            cmd = f'espeak-ng "{sentence}" --stdout | aplay -D {AUDIO_DEVICE}'
            subprocess.run(cmd, shell=True)
        except Exception as e:
            print("❌ Speech error:", e)


# ---------------------------
# BACKEND COMMUNICATION
# ---------------------------
def process_text(text):
    payload = {"message": text}

    try:
        response = requests.post(API_URL, headers=HEADERS, json=payload, timeout=5)
        print("Raw response:", response.text)

        if response.status_code == 200:
            data = response.json()

            if isinstance(data.get("data"), dict):
                msg = data["data"].get("message")
                if msg:
                    return msg

            if data.get("message"):
                return data["message"]

        return "Server returned invalid response"

    except:
        #  OFFLINE MODE
        print("⚠️ Backend offline, using local brain")

        text = text.lower()

        if "fever" in text:
            return "You may have fever. Please drink fluids and rest."
        elif "headache" in text:
            return "Headache can be due to stress or dehydration."
        elif "hello" in text:
            return "Hello, I am your Care Connect assistant."
        else:
            return "Server is down. Please try again later."


# ---------------------------
# SPEECH SETUP
# ---------------------------
q = queue.Queue()

def callback(indata, frames, time, status):
    if status:
        print(status)
    q.put(bytes(indata))


def init_speech():
    device_info = sd.query_devices(kind='input')
    samplerate = int(device_info['default_samplerate'])

    print("Using samplerate:", samplerate)

    model = Model("vosk-model-small-en-us-0.15")
    recognizer = KaldiRecognizer(model, samplerate)

    return samplerate, recognizer


def listen_and_convert(samplerate, recognizer):
    with sd.RawInputStream(
        samplerate=samplerate,
        blocksize=8000,
        dtype='int16',
        channels=1,
        latency='low',
        callback=callback
    ):
        print("Listening...")

        while True:
            data = q.get()

            if recognizer.AcceptWaveform(data):
                result = json.loads(recognizer.Result())
                text = result.get("text", "")

                if text:
                    return text

            else:
                partial = json.loads(recognizer.PartialResult())
                if partial.get("partial"):
                    print("Hearing:", partial.get("partial"))


# ---------------------------
# CHAT LOOP
# ---------------------------
def chat_once(samplerate, recognizer):
    text = listen_and_convert(samplerate, recognizer)

    if not text:
        return

    print("You said:", text)

    if "exit" in text.lower():
        speak("Goodbye")
        exit()

    response = process_text(text)
    speak(response)


# ---------------------------
# MAIN
# ---------------------------
def main():
    device_token = get_device_token()

    HEADERS["X-Device-Token"] = device_token

    setup_button()   # ✅ initialize button
    
    samplerate, recognizer = init_speech()

    speak("System is ready")

    while True:
        check_button()   # ✅ keep checking button
        chat_once(samplerate, recognizer)      # one interaction


if __name__ == "__main__":
    main()
