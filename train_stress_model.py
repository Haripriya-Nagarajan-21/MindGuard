import pandas as pd
import pickle

from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix

print("🔹 Training Stress Prediction Model")

# ---------------- LOAD DATA ----------------
df = pd.read_csv("data/final_stress_dataset.csv")
print("Dataset shape:", df.shape)

# ---------------- FEATURES & TARGET ----------------
X = df.drop("stress_level", axis=1)
y = df["stress_level"]

# ---------------- TRAIN-TEST SPLIT ----------------
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)

print("Training samples:", X_train.shape)
print("Testing samples:", X_test.shape)

# ---------------- TRAIN MODEL ----------------
model = RandomForestClassifier(
    n_estimators=100,
    random_state=42
)
model.fit(X_train, y_train)

print("✅ Model training completed")

# ---------------- EVALUATE MODEL ----------------
y_pred = model.predict(X_test)

accuracy = accuracy_score(y_test, y_pred)
print("Accuracy:", accuracy)

print("\nClassification Report:")
print(classification_report(y_test, y_pred))

print("\nConfusion Matrix:")
print(confusion_matrix(y_test, y_pred))

# ---------------- SAVE MODEL ----------------
pickle.dump(model, open("model/stress_model.pkl", "wb"))
print("✅ Model saved as model/stress_model.pkl")