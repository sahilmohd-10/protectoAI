import streamlit as st
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

data = {
    "Career": ["Data Scientist", "Web Developer", "AI Engineer", "UI/UX Designer"],
    "Required_Skills": [
        "Python, Statistics, Machine Learning, Data Visualization",
        "HTML, CSS, JavaScript, React",
        "Python, Deep Learning, NLP, TensorFlow",
        "Design Thinking, Figma, UX Research, Creativity"
    ]
}
df = pd.DataFrame(data)
print(df)