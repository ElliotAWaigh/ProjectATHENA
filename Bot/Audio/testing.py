from vosk import Model, KaldiRecognizer
import pyaudio
import random

# Load the Model
model = Model(r"C:\Users\Elliot\OneDrive - Queensland University of Technology\00AthenaV2\Bot\vosk-model-small-en-us-0.15")
recogniser = KaldiRecognizer(model, 16000)

# Set up Microphone
mic = pyaudio.PyAudio()
stream = mic.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True, frames_per_buffer=8192)

# Start listening
stream.start_stream()

# Action Words
action_words = ["athena", "computer", "jarvis"]
end_words = ["stop", "end", "goodbye", "goodnight", "good night"]
worker_words = ["Boss", "Love", "Sir"]

# Forever Loop
while True:
    data = stream.read(4096) # Stream of data

    if recogniser.AcceptWaveform(data): # If its readible
        text = recogniser.Result() # Result of text
        sentence = text[14:-3] # Formatted text
        print(sentence) 
        if sentence.lower() in end_words: # Checking for information
            quit()
        if sentence.lower() in action_words:
            print("I'm here,", random.choice(worker_words) + ".")