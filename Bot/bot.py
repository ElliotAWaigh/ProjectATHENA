from multi_stage_processor import MultiStageProcessor
from voice_recognition import create_voice_recognition

class Bot:
    def __init__(self):
        self.processor = MultiStageProcessor()
        self.active = True
        self.voice_recognition = create_voice_recognition()

    def receive_input(self, input_text):
        if not input_text.strip():
            return

        response, continue_conversation = self.processor.process_query(input_text)
        print(response)
        if not continue_conversation:
            self.run()

    def run(self):
        print("Welcome to the Bot. Speak a command or type something to start...")

        while self.active:
            user_input = self.voice_recognition.listen()

            if user_input == "END_SESSION":
                self.active = False

            elif user_input:
                self.receive_input(user_input)
