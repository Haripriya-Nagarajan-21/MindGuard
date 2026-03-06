import json
import pickle
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

# Load intents
with open("data/intents.json") as f:
    intents = json.load(f)

sentences = []
labels = []

for intent in intents["intents"]:
    for pattern in intent["patterns"]:
        sentences.append(pattern)
        labels.append(intent["tag"])

# NLP: text → numbers
vectorizer = TfidfVectorizer()
X = vectorizer.fit_transform(sentences)

# Train ML model
model = LogisticRegression()
model.fit(X, labels)

# Save model
pickle.dump(model, open("model/chatbot_model.pkl", "wb"))
pickle.dump(vectorizer, open("model/vectorizer.pkl", "wb"))

print("✅ Chatbot model trained successfully")