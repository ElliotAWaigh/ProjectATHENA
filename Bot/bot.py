from multi_stage_processor import MultiStageProcessor

class Bot:
    def __init__(self):
        self.processor = MultiStageProcessor()
        self.active = True

    def receive_input(self, input_text):
        if not input_text.strip():
            print("Goodbye!")
            self.run
            #self.active = False
            return

        response, continue_conversation = self.processor.process_query(input_text)
        print(response)
        if not continue_conversation:
            #print("Goodbye!")
            self.run
            #self.active = False

    def run(self):
        print("Welcome to the Bot. Type something to start...")
        while self.active:
            user_input = input("You: ")
            self.receive_input(user_input)