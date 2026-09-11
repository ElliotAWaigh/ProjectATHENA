import os
from pathlib import Path
import random
from vosk import Model, KaldiRecognizer
import pyaudio


class VoiceRecognition:
    def __init__(self, model_path, action_words, end_words, worker_words):
        if not os.path.exists(model_path):
            raise FileNotFoundError(
                f"Vosk model directory not found at: {model_path}\n"
                "Ensure the model folder is present in the Bot directory."
            )

        self.model = Model(model_path)
        self.recognizer = KaldiRecognizer(self.model, 16000)
        self.mic = pyaudio.PyAudio()
        self.stream = self.mic.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=16000,
            input=True,
            frames_per_buffer=16384,  # Increased buffer size to prevent overflow
        )
        self.stream.start_stream()

        self.action_words = action_words
        self.end_words = end_words
        self.worker_words = worker_words

    def listen(self):
        while True:
            try:
                data = self.stream.read(4096, exception_on_overflow=False)  # Handle overflow gracefully

                if self.recognizer.AcceptWaveform(data):
                    text = self.recognizer.Result()
                    sentence = text[14:-3].strip().lower()
                    if sentence:
                        print(sentence)

                    # Skip blank or irrelevant sentences
                    if not sentence:
                        continue

                    if sentence in self.end_words:
                        print("See you next time.")
                        return "END_SESSION"

                    if sentence in self.action_words:
                        response = f"I'm here, {random.choice(self.worker_words)}."
                        print(response)
                        return response

                    # Return the detected sentence for further processing
                    return sentence

            except OSError as e:
                if e.errno == -9981:  # Input overflowed
                    print("Input overflowed, retrying...")
                    continue
                else:
                    raise e


def create_voice_recognition():
    # Resolves directly to: 00ATHENA/Bot/vosk-model-small-en-us-0.15
    base_dir = Path(__file__).resolve().parent
    model_path = str(base_dir / "vosk-model-small-en-us-0.15")

    action_words = ["athena", "computer"]
    end_words = ["stop", "end", "goodbye", "goodnight", "good night"]
    worker_words = ["Boss", "Love", "Sir"]

    return VoiceRecognition(model_path, action_words, end_words, worker_words)