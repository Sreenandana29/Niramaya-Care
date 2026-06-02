# Niramaya Care

Niramaya Care is a production-ready Streamlit healthcare demo that combines patient registration, a multilingual AI voice health assistant, smart vital monitoring, emergency triage, and healthcare analytics in one SQLite-backed app.

## Features

- Patient registration with a unique Patient ID and digital health profile.
- Hero multilingual voice assistant for English, Hindi, and Kannada.
- Speech-to-text from uploaded audio files using `SpeechRecognition`.
- Rule-based healthcare response engine with symptom intent matching.
- Text-to-speech audio replies with `gTTS`.
- Chatbot interface with command tracking in SQLite.
- BP, heart rate, oxygen, temperature, and glucose monitoring.
- Health score, risk level, and recommendations.
- Emergency response center with SOS and oxygen-drop alerts.
- Analytics dashboard with KPIs, Plotly charts, and assistant usage insights.
- Demo-ready sample data and modern glassmorphism UI.

## Run Locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Voice Assistant Notes

The assistant accepts typed input and uploaded `.wav`, `.aiff`, or `.flac` audio files. Google speech recognition and `gTTS` require internet access. If audio services are unavailable, the app still works with typed chat and clearly shows the issue.

## Project Structure

```text
Niramaya_Care/
├── app.py
├── requirements.txt
├── README.md
├── niramaya.db
└── assets/
    └── style.css
```

## Disclaimer

Niramaya Care is a hackathon and education-focused prototype. It does not replace professional medical diagnosis, emergency services, or clinical care.
