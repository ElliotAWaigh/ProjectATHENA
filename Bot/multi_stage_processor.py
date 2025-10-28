import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.feature_extraction.text import TfidfVectorizer
import numpy as np
import re
from entity_extractor import EntityExtractor
import Tools.football as football
import Tools.calendar_interface as calendar
import Tools.spotify as spotify
import Tools.wakeup as wakeup
import os
import sys

class MultiStageProcessor:
    def __init__(self, required_context=None, optional_context=None):
        self.entity_extractor = EntityExtractor()
        self.questions_answers = self.load_questions_answers(r"E:\Users\Elliot\OneDrive\OneDrive - Queensland University of Technology\00AthenaV2\Bot\question_answer.csv")
        if not self.questions_answers:
            raise ValueError("Questions and answers are empty. Please check the CSV file.")

        self.vectorizer = TfidfVectorizer(stop_words=None, ngram_range=(1, 2))
        self.questions_matrix = self.vectorizer.fit_transform([self.preprocess_text(q) for q in self.questions_answers.keys()])
        self.state = "waiting"
        self.collected_data = {}
        self.last_best_match = None
        self.similarity_threshold = 0.7
        self.max_threshold = 0.9

        self.required_context = required_context or {}
        self.optional_context = optional_context or {}

        self.open_required_queue = []
        self.open_optional_queue = []
        self.closed_required_queue = []
        self.closed_optional_queue = []

        
    def load_questions_answers(self, file_path):
        try:
            df = pd.read_csv(file_path)
            if df.empty:
                raise ValueError(f"File {file_path} is empty.")
            questions_answers = dict(zip(df['question'], df['answer']))
            
            # Debug: Print out loaded questions
            print("Loaded Questions:")
            for question in questions_answers.keys():
                print(f"- {question}")
            
            return questions_answers
        except FileNotFoundError:
            return {}
        except pd.errors.EmptyDataError:
            return {}

    def preprocess_text(self, text):
        return re.sub(r'[^\w\s]', '', text.lower())


    def find_best_response(self, user_input):
        # Preprocess the input
        preprocessed_input = self.preprocess_text(user_input)
        input_vec = self.vectorizer.transform([preprocessed_input])

        # Compute similarities
        similarities = cosine_similarity(input_vec, self.questions_matrix)
        
        # Find the best match
        best_idx = np.argmax(similarities)
        best_similarity = similarities[0][best_idx]
        best_question = list(self.questions_answers.keys())[best_idx]
        best_answer = self.questions_answers[best_question]

        return best_question, best_answer, best_similarity

    

    def process_query(self, user_input):
        if self.state == "waiting":
            matched_question, matched_answer, best_similarity = self.find_best_response(user_input)

            if best_similarity < self.similarity_threshold:
                return "ATHENA: I'm sorry, I didn't understand that. Can you please rephrase?", True

            self.last_best_match = matched_question

            if matched_answer == "Action Needed":
                self.perform_action_required(matched_question)

            if matched_answer == "Context Needed":
                self.state = "collecting"
                req_ctx, opt_ctx, open_req, open_opt, close_req, close_opt = self.determine_required_context(matched_question)
                self.setup_context_queues(open_req, open_opt, close_req, close_opt, req_ctx, opt_ctx)

                required_keys = ', '.join(req_ctx.keys()) if req_ctx else 'No required info'
                optional_keys = ', '.join(opt_ctx.keys()) if opt_ctx else 'No optional info'
                return f"ATHENA: I need more information: {required_keys}. Optional: {optional_keys}", True

            if best_similarity > self.max_threshold:
                self.state = "waiting"
                return matched_answer, False

            if 0.7 <= best_similarity <= self.max_threshold:
                self.state = "confirming"
                return f"ATHENA: Did you mean: '{matched_question}'?", True

        elif self.state == "confirming":
            if 'yes' in user_input.lower():
                response = self.questions_answers.get(self.last_best_match, "ATHENA: Thank you for confirming. We will process your request.")
                self.state = "waiting"
                return response, False
            else:
                return "ATHENA: Let's try again. What information are you looking for?", True

        elif self.state == "collecting":
            return self.handle_collecting_state(user_input)

        return "ATHENA: I'm not sure how to handle this. Can you rephrase?", True

    def setup_context_queues(self, open_req, open_opt, close_req, close_opt, required_context, optional_context):
        # Assign them to instance variables
        self.required_context = required_context
        self.optional_context = optional_context
        
        # Setup your context queues
        self.context_queue = [
            (context, 'open required') for context in open_req
        ] + [
            (context, 'open optional') for context in open_opt
        ] + [
            (context, 'closed required') for context in close_req
        ] + [
            (context, 'closed optional') for context in close_opt
        ]

    def handle_collecting_state(self, user_input):
        if any(phrase in user_input.lower() for phrase in ["that's all", "that's it", "no more"]):
            # Handle end of user input and fill in missing optional data with defaults
            for context, context_type in self.context_queue:
                if 'optional' in context_type and context not in self.collected_data:
                    self.collected_data[context] = "default_value"
            response = self.perform_action_based_on_context(self.last_best_match, self.collected_data)
            self.state = "waiting"
            self.collected_data = {}
            return response, False

        if self.context_queue:
            current_context, context_type = self.context_queue.pop(0)

            # Determine if the current context is open or closed
            if current_context in self.closed_required_queue or current_context in self.closed_optional_queue:
                # Determine the possible values for the current context
                possible_values = self.required_context.get(current_context, []) + self.optional_context.get(current_context, [])
                
                # Process closed-ended questions with the entity extractor
                entities = self.entity_extractor.extract_entities(user_input, {current_context: possible_values})
                
                if entities:
                    self.collected_data.update(entities)
                else:
                    # If no entities were extracted, ask for the same context again
                    self.context_queue.insert(0, (current_context, context_type))
                    return f"ATHENA: Please provide a valid input for: {current_context}", True
            else:
                # Process open-ended questions by directly saving the user input
                self.collected_data[current_context] = user_input.strip()

            if self.context_queue:
                next_context, next_type = self.context_queue[0]  # Peek at the next context in the queue
                if 'required' in next_type:
                    return f"ATHENA: Please provide more information about: {next_context}", True
                else:
                    return f"ATHENA: Do you have more information about: {next_context}? If not, say 'that's all'", True
            else:
                response = self.perform_action_based_on_context(self.last_best_match, self.collected_data)
                self.state = "waiting"
                self.collected_data = {}
                return response, False
        else:
            response = self.perform_action_based_on_context(self.last_best_match, self.collected_data)
            self.state = "waiting"
            self.collected_data = {}
            return response, False

    def get_next_context(self, is_optional=False):
        if not is_optional:
            if self.open_required_queue:
                return self.open_required_queue.pop(0)
            if self.closed_required_queue:
                return self.closed_required_queue.pop(0)
        else:
            if self.open_optional_queue:
                return self.open_optional_queue.pop(0)
            if self.closed_optional_queue:
                return self.closed_optional_queue.pop(0)
        return None
    
    def setup_context_queues(self, open_req, open_opt, close_req, close_opt, required_context, optional_context):
        self.required_context = required_context
        self.optional_context = optional_context
        
        self.open_required_queue = open_req
        self.open_optional_queue = open_opt
        self.closed_required_queue = close_req
        self.closed_optional_queue = close_opt
        
        # Save the context definitions dictionary
        #self.context_definitions = context_definitions
        
        self.collected_data = {}  # Reset collected data when setting up new context-

        # Create the context queue
        self.context_queue = [
            (context, 'required' if context in open_req else 'optional')
            for context in open_req + open_opt
        ] + [
            (context, 'closed required')
            for context in close_req
        ] + [
            (context, 'closed optional')
            for context in close_opt
        ]

    def determine_required_context(self, question):
        if "add a meeting to my calendar" in question.lower():
            return calendar.context_for_add_meeting()
        # Add other context determination logic here
        return {}, {}, [], [], [], []

    def perform_action_based_on_context(self, question, context):
        if "add a meeting to my calendar" in question.lower():
            return calendar.action_for_add_meeting(context)
        # Add other actions based on the context here
        return "I'm sorry, I don't know how to handle that question."
    
    def perform_action_required(self, question):

        spotify_commands = ["play my liked songs", "loop", "pause", "skip", "resume", "volume up", "volume down"] 
        #Play My Liked Songs,Action Needed

        light_commands = ["turn on my lights, turn off my lights"]

        if question.lower() in spotify_commands:
            spotify.action(question)

        if "goodbye" in question.lower():
            quit()

        if "restart" in question.lower():
            os.execv(sys.executable, ['python'] + sys.argv)

        if "boot up" in question.lower():
            wakeup.wakeup()

        



# if the question has 'web search' as question type
# It takes the entire string, REMOVES 'look up'
# Searches that
# Returns

# It will SEPERATELY run everything as if it was a web search question
# Defaults to web search until proven otherwise

# If search is the first thing after 'Hey [Action Word]', process
