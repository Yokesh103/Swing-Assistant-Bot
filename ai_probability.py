# ai_probability.py
import joblib, os, pandas as pd
from sklearn.ensemble import RandomForestClassifier

MODEL_FILE = "ai_model.pkl"

def load_ai_model():
    return joblib.load(MODEL_FILE) if os.path.exists(MODEL_FILE) else None

def predict_prob(model, features):
    if model is None:
        return None
    df = pd.DataFrame([features])
    p = model.predict_proba(df)[0, 1] * 100
    return round(float(p), 2)
