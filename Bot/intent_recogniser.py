import os
import json
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

class IntentRecognizer:
    """
    ATHENA Intent Recognition System
    ---------------------------------
    Uses TF-IDF vectorization + cosine similarity to match user input
    against known intents defined in config/intents.json.

    Each intent includes a list of example phrases. This allows
    semantic recognition of user intent even if phrasing differs.
    """

    def __init__(self, intent_file="config/intents.json", threshold=0.6):
        self.intent_file = intent_file
        self.threshold = threshold
        self.intents = self._load_intents()
        self.vectorizer = self._train_vectorizer()

    def _load_intents(self):
        """
        Loads intent definitions from JSON file.
        Each intent should look like:
        {
            "open_app": ["open app", "launch", "start program"],
            "calendar_check": ["show my schedule", "what's on today"]
        }
        """
        if not os.path.exists(self.intent_file):
            raise FileNotFoundError(f"Intent file not found: {self.intent_file}")

        with open(self.intent_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not data:
            raise ValueError("Intents file is empty or invalid.")
        return data

    def _train_vectorizer(self):
        """
        Fit the TF-IDF vectorizer on all intent phrases.
        """
        corpus = [phrase for patterns in self.intents.values() for phrase in patterns]
        vectorizer = TfidfVectorizer(ngram_range=(1, 2))
        vectorizer.fit(corpus)
        return vectorizer

    def predict_intent(self, user_input):
        """
        Returns the most likely intent and its confidence score.
        If below threshold, returns None.
        """
        user_vec = self.vectorizer.transform([user_input.lower()])
        best_intent, best_score = None, 0.0

        for intent, examples in self.intents.items():
            example_vecs = self.vectorizer.transform(examples)
            sim = cosine_similarity(user_vec, example_vecs)
            score = np.max(sim)
            if score > best_score:
                best_intent, best_score = intent, score

        if best_score < self.threshold:
            return None, best_score
        return best_intent, best_score

    def retrain(self, new_intents_path=None):
        """
        Reloads and retrains on updated intent data.
        """
        if new_intents_path:
            self.intent_file = new_intents_path
        self.intents = self._load_intents()
        self.vectorizer = self._train_vectorizer()
        print("Intent model retrained successfully.")


if __name__ == "__main__":
    # Example standalone test
    recognizer = IntentRecognizer(intent_file="config/intents.json")
    while True:
        query = input("You: ").strip()
        if query.lower() in ["quit", "exit"]:
            break
        intent, confidence = recognizer.predict_intent(query)
        if intent:
            print(f"Intent → {intent} (confidence: {confidence:.2f})")
        else:
            print(f"Unclear intent (confidence: {confidence:.2f}) — please rephrase.")
