import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.feature_extraction.text import TfidfVectorizer
import numpy as np
import re
from entity_extractor import EntityExtractor
import Tools.football as football

class MultiStageProcessor:
    def __init__(self):
        self.entity_extractor = EntityExtractor()
        self.questions_answers = self.load_questions_answers("question_answer.csv")
        
        if not self.questions_answers:
            raise ValueError("Questions and answers are empty. Please check the CSV file.")

        print(f"Loaded questions and answers: {self.questions_answers}")

        self.vectorizer = TfidfVectorizer(stop_words='english')
        self.questions_matrix = self.vectorizer.fit_transform([self.preprocess_text(q) for q in self.questions_answers.keys()])
        self.state = "waiting"  # Possible states: 'waiting', 'collecting', 'confirming'
        self.collected_data = {}
        self.last_best_match = None
        self.similarity_threshold = 0.7  # 70% similarity threshold

    def load_questions_answers(self, file_path):
        try:
            df = pd.read_csv(file_path)
            if df.empty:
                raise ValueError(f"File {file_path} is empty. Please check the file content.")
            print("CSV loaded successfully.")
            print(df.head())  # Print the first few rows of the dataframe for debugging
            return dict(zip(df['question'], df['answer']))
        except FileNotFoundError:
            print(f"File {file_path} not found. Please check the file location.")
            return {}
        except pd.errors.EmptyDataError:
            print(f"File {file_path} is empty. Please check the file content.")
            return {}

    def preprocess_text(self, text):
        # Convert text to lowercase
        text = text.lower()
        # Remove punctuation
        text = re.sub(r'[^\w\s]', '', text)
        return text

    def find_best_response(self, user_input):
        preprocessed_input = self.preprocess_text(user_input)
        input_vec = self.vectorizer.transform([preprocessed_input])
        similarities = cosine_similarity(input_vec, self.questions_matrix)

        best_idx = np.argmax(similarities)
        best_question = list(self.questions_answers.keys())[best_idx]
        best_answer = self.questions_answers[best_question]
        best_similarity = similarities[0][best_idx]

        # Print all questions, answers, and their similarity scores
        print("Similarity scores for each question:")
        for i, question in enumerate(self.questions_answers.keys()):
            print(f"Question: '{question}', Answer: '{self.questions_answers[question]}', Similarity: {similarities[0][i]}")

        print(f"Best match: '{best_question}' with similarity {best_similarity}")

        return best_question, best_answer, best_similarity

    def process_query(self, user_input):
        if self.state == "waiting":
            matched_question, matched_answer, best_similarity = self.find_best_response(user_input)

            if best_similarity < self.similarity_threshold:
                print(f"Best similarity score {best_similarity} is below threshold {self.similarity_threshold}")
                return "I'm sorry, I didn't understand that. Can you please rephrase?", True

            self.last_best_match = matched_question  # Save this for potential confirmation
            
            if matched_answer == "Context Needed":
                self.state = "collecting"
                required_context, optional_context = self.determine_required_context(matched_question)
                self.collected_data = {}
                return f"I need more information: {', '.join(required_context.keys())}. Optional: {', '.join(optional_context.keys())}", True
            
            self.state = "confirming"
            return f"Did you mean: '{matched_question}'? {matched_answer}", True

        elif self.state == "confirming":
            if 'yes' in user_input.lower():
                response = self.questions_answers.get(self.last_best_match, "Thank you for confirming. We will process your request.")
                self.state = "waiting"
                return response, False
            else:
                self.state = "waiting"
                return "Let's try again. What information are you looking for?", True

        elif self.state == "collecting":
            required_context, optional_context = self.determine_required_context(self.last_best_match)
            entities = self.entity_extractor.extract_entities(user_input, {**required_context, **optional_context})
            self.collected_data.update(entities)
            
            missing_required_entities = [k for k in required_context.keys() if k not in self.collected_data]
            missing_optional_entities = [k for k in optional_context.keys() if k not in self.collected_data]

            if not missing_required_entities:
                # All required context is collected, use defaults for missing optional context if needed
                for opt_entity in missing_optional_entities:
                    self.collected_data[opt_entity] = "default_value"  # Replace with actual default logic if needed
                response = self.perform_action_based_on_context(self.last_best_match, self.collected_data)
                self.state = "waiting"
                self.collected_data = {}
                return response, False
            else:
                return f"Please provide more information about: {', '.join(missing_required_entities)}. Optional: {', '.join(missing_optional_entities)}", True

        return "I'm not sure how to handle this. Can you rephrase?", True

    def determine_required_context(self, question):
        if "Who is the top scorer in BLANK?" in question:
            return football.context_for_goal_scorer()
        elif "Can you show me the stats of" in question:
            return football.context_for_player_stats()
        return {}, {}

    def perform_action_based_on_context(self, question, context):
        if "Who is the top scorer in BLANK?" in question:
            return football.action_for_goal_scorer(context)
        
        elif "Can you show me the stats of" in question:
            return football.action_for_player_stats(context)
        return "I'm sorry, I don't know how to handle that question."