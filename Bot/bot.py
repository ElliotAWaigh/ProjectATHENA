# bot.py
import random
from multi_stage_processor import MultiStageProcessor
from voice_recognition import create_voice_recognition
import Tools.welcome

class Bot:
    def __init__(self):
        try:
            self.processor = MultiStageProcessor()
        except Exception as e:
            print(f"[Bot] Failed to initialize processor: {e}")
            self.processor = None

        self.active = True
        self.voice_recognition = create_voice_recognition()

    def receive_input(self, input_text):
        if not input_text.strip():
            return "ATHENA: I didn't catch that. Could you please repeat?"
        if not self.processor:
            return "ATHENA: Core processor not initialized."
        try:
            response, continue_conversation = self.processor.process_query(input_text)
            return response
        except Exception as e:
            return f"ATHENA: There was an error processing your request: {e}"

    def run(self):
        welcome_message = random.choice([Tools.welcome.Hello_Name, Tools.welcome.Hello_sir])
        welcome_message()

        control_method = input("Would you like to use voice control, text control, or Telegram control? (Enter 'voice', 'text', or 'telegram'): ").strip().lower()

        if control_method == 'voice':
            self.run_voice_control()
        elif control_method == 'text':
            self.run_text_control()
        elif control_method == 'telegram':
            self.run_telegram_control()
        else:
            print("Invalid input. Please enter 'voice', 'text', or 'telegram'.")
            self.run()

    def run_voice_control(self):
        print("Voice control activated. Speak a command to start...")
        while self.active:
            user_input = self.voice_recognition.listen()
            if user_input == "END_SESSION":
                self.active = False
            elif user_input:
                print(self.receive_input(user_input))

    def run_text_control(self):
        print("Text control activated. Type something to start...")
        while self.active:
            user_input = input("You: ").strip()
            if user_input.lower() == "quit":
                self.active = False
            elif user_input:
                print(self.receive_input(user_input))

    def run_telegram_control(self):
        from Tools.telegram_bot import run_telegram_bot
        run_telegram_bot(self)

def process_input_from_telegram(input_text):
    bot = Bot()
    return bot.receive_input(input_text)

if __name__ == '__main__':
    Bot().run()
