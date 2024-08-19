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
        print("Welcome to the Bot.")
        
        # Prompt the user to choose the control method
        control_method = input("Would you like to use voice control or text control? (Enter 'voice' or 'text'): ").strip().lower()

        if control_method == 'voice':
            self.run_voice_control()
        elif control_method == 'text':
            self.run_text_control()
        else:
            print("Invalid input. Please enter 'voice' or 'text'.")
            self.run()  # Re-prompt if input is invalid

    def run_voice_control(self):
        print("Voice control activated. Speak a command to start...")

        while self.active:
            user_input = self.voice_recognition.listen()

            if user_input == "END_SESSION":
                self.active = False

            elif user_input:
                self.receive_input(user_input)

    def run_text_control(self):
        print("Text control activated. Type something to start...")

        while self.active:
            user_input = input("You: ").strip()
            
            if user_input.lower() == "quit":
                self.active = False

            elif user_input:
                self.receive_input(user_input)
