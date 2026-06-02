import base64
import hashlib
import os
import sqlite3
import tempfile
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import speech_recognition as sr
import streamlit as st
from gtts import gTTS


APP_NAME = "Niramaya Care"
BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "niramaya.db"
ASSET_DIR = BASE_DIR / "assets"
STYLE_PATH = ASSET_DIR / "style.css"

LANGUAGE_META = {
    "English": {"code": "en-IN", "tts": "en", "label": "English"},
    "Hindi": {"code": "hi-IN", "tts": "hi", "label": "हिंदी"},
    "Kannada": {"code": "kn-IN", "tts": "kn", "label": "ಕನ್ನಡ"},
}


def get_connection():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def execute(query, params=()):
    with get_connection() as conn:
        conn.execute(query, params)
        conn.commit()


def query_df(query, params=()):
    with get_connection() as conn:
        return pd.read_sql_query(query, conn, params=params)


def load_css():
    if STYLE_PATH.exists():
        st.markdown(f"<style>{STYLE_PATH.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


def create_tables():
    schema = [
        """
        CREATE TABLE IF NOT EXISTS patients (
            patient_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            age INTEGER,
            gender TEXT,
            phone TEXT,
            blood_group TEXT,
            language TEXT,
            allergies TEXT,
            chronic_conditions TEXT,
            emergency_contact TEXT,
            address TEXT,
            created_at TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS vitals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id TEXT,
            systolic INTEGER,
            diastolic INTEGER,
            heart_rate INTEGER,
            oxygen INTEGER,
            temperature REAL,
            glucose INTEGER,
            health_score INTEGER,
            risk_level TEXT,
            recommendations TEXT,
            created_at TEXT,
            FOREIGN KEY(patient_id) REFERENCES patients(patient_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS emergencies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id TEXT,
            alert_type TEXT,
            priority TEXT,
            description TEXT,
            recommended_action TEXT,
            status TEXT,
            created_at TEXT,
            FOREIGN KEY(patient_id) REFERENCES patients(patient_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS voice_commands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id TEXT,
            language TEXT,
            user_text TEXT,
            assistant_text TEXT,
            intent TEXT,
            created_at TEXT,
            FOREIGN KEY(patient_id) REFERENCES patients(patient_id)
        )
        """,
    ]
    for statement in schema:
        execute(statement)


def generate_patient_id(name, phone):
    seed = f"{name}-{phone}-{uuid.uuid4().hex[:8]}".encode("utf-8")
    digest = hashlib.sha1(seed).hexdigest()[:6].upper()
    return f"NIR-{datetime.now().strftime('%y%m')}-{digest}"


def seed_demo_data():
    existing = query_df("SELECT COUNT(*) AS total FROM patients")["total"].iloc[0]
    if existing:
        return

    patients = [
        ("NIR-2606-A1B2C3", "Asha Rao", 42, "Female", "9876543210", "O+", "Kannada", "Penicillin", "Hypertension", "Ravi Rao - 9876500001", "Bengaluru", -8),
        ("NIR-2606-D4E5F6", "Rahul Mehta", 31, "Male", "9867001112", "B+", "Hindi", "None", "Asthma", "Neha Mehta - 9867001113", "Mumbai", -5),
        ("NIR-2606-G7H8I9", "Priya Nair", 56, "Female", "9812345678", "A-", "English", "Sulfa", "Diabetes", "Anil Nair - 9812345000", "Kochi", -3),
        ("NIR-2606-J1K2L3", "Kabir Khan", 67, "Male", "9900123456", "AB+", "Hindi", "None", "Cardiac history", "Sara Khan - 9900123000", "Delhi", -1),
    ]
    for p in patients:
        created = (datetime.now() + timedelta(days=p[-1])).isoformat(timespec="seconds")
        execute(
            """
            INSERT INTO patients VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (*p[:-1], created),
        )

    vital_rows = [
        ("NIR-2606-A1B2C3", 142, 92, 88, 96, 98.2, 118),
        ("NIR-2606-A1B2C3", 136, 86, 82, 97, 98.0, 112),
        ("NIR-2606-D4E5F6", 118, 76, 78, 95, 98.7, 98),
        ("NIR-2606-D4E5F6", 124, 80, 84, 93, 99.0, 104),
        ("NIR-2606-G7H8I9", 132, 84, 92, 94, 99.1, 178),
        ("NIR-2606-G7H8I9", 128, 82, 86, 96, 98.8, 156),
        ("NIR-2606-J1K2L3", 158, 98, 112, 89, 100.2, 138),
        ("NIR-2606-J1K2L3", 148, 94, 104, 91, 99.8, 132),
    ]
    for index, row in enumerate(vital_rows):
        score, risk, recs = calculate_health_score(*row[1:])
        created = (datetime.now() - timedelta(hours=28 - index * 3)).isoformat(timespec="seconds")
        execute(
            """
            INSERT INTO vitals
            (patient_id, systolic, diastolic, heart_rate, oxygen, temperature, glucose, health_score, risk_level, recommendations, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (*row, score, risk, "; ".join(recs), created),
        )

    emergency_rows = [
        ("NIR-2606-J1K2L3", "Oxygen Drop", "Critical", "SpO2 dropped below 90% with elevated pulse.", "Start oxygen support, call emergency response, keep patient seated upright.", "Active", -9),
        ("NIR-2606-A1B2C3", "High BP", "Medium", "Repeated BP readings above target range.", "Rest for 10 minutes, repeat BP, contact clinician if persistent.", "Monitoring", -20),
        ("NIR-2606-D4E5F6", "Asthma SOS", "High", "Patient reported breathlessness through assistant.", "Use prescribed inhaler, monitor SpO2, prepare transfer if symptoms worsen.", "Resolved", -32),
    ]
    for row in emergency_rows:
        created = (datetime.now() + timedelta(hours=row[-1])).isoformat(timespec="seconds")
        execute(
            """
            INSERT INTO emergencies
            (patient_id, alert_type, priority, description, recommended_action, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (*row[:-1], created),
        )

    assistant_rows = [
        ("NIR-2606-A1B2C3", "Kannada", "ನನಗೆ ತಲೆ ನೋವು ಇದೆ", "Please rest, drink water, and monitor your symptoms. Seek care if severe.", "headache"),
        ("NIR-2606-D4E5F6", "Hindi", "मुझे सांस लेने में दिक्कत है", "Sit upright and use your prescribed inhaler. If severe, call emergency services.", "breathing"),
        ("NIR-2606-G7H8I9", "English", "My sugar is high", "Drink water, avoid sugary food, and follow your diabetes care plan.", "diabetes"),
        ("NIR-2606-J1K2L3", "Hindi", "सीने में दर्द है", "This can be urgent. Call emergency services immediately.", "chest_pain"),
    ]
    for index, row in enumerate(assistant_rows):
        created = (datetime.now() - timedelta(hours=18 - index * 4)).isoformat(timespec="seconds")
        execute(
            """
            INSERT INTO voice_commands
            (patient_id, language, user_text, assistant_text, intent, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (*row, created),
        )


def init_database():
    create_tables()
    seed_demo_data()


def get_patients():
    return query_df("SELECT * FROM patients ORDER BY created_at DESC")


def patient_options():
    patients = get_patients()
    if patients.empty:
        return {}
    return {f"{row.name} ({row.patient_id})": row.patient_id for row in patients.itertuples()}


def calculate_health_score(systolic, diastolic, heart_rate, oxygen, temperature, glucose):
    score = 100
    recs = []

    if systolic >= 160 or diastolic >= 100:
        score -= 24
        recs.append("Blood pressure is high. Rest and contact a clinician if it stays elevated")
    elif systolic >= 140 or diastolic >= 90:
        score -= 14
        recs.append("BP is above target. Reduce salt, hydrate, and recheck")
    elif systolic < 90 or diastolic < 60:
        score -= 16
        recs.append("BP is low. Sit or lie down and hydrate")

    if heart_rate > 110 or heart_rate < 50:
        score -= 18
        recs.append("Heart rate is outside the safe range. Monitor closely")
    elif heart_rate > 100:
        score -= 9
        recs.append("Pulse is mildly elevated. Rest and recheck")

    if oxygen < 90:
        score -= 32
        recs.append("Oxygen is critically low. Trigger emergency response")
    elif oxygen < 94:
        score -= 18
        recs.append("Oxygen is low. Sit upright and monitor breathing")

    if temperature >= 101:
        score -= 14
        recs.append("Fever detected. Hydrate and consider medical advice")
    elif temperature < 96:
        score -= 10
        recs.append("Temperature is low. Keep warm and monitor")

    if glucose >= 180:
        score -= 16
        recs.append("Glucose is high. Follow diabetes care plan and hydrate")
    elif glucose < 70:
        score -= 18
        recs.append("Glucose is low. Take fast-acting sugar if conscious")

    score = max(0, min(100, score))
    if score >= 78:
        risk = "Low"
    elif score >= 55:
        risk = "Medium"
    else:
        risk = "High"

    if not recs:
        recs.append("Vitals look stable. Continue healthy routine and scheduled checkups")
    return score, risk, recs


def assistant_response(text, language):
    cleaned = text.lower().strip()
    rules = [
        {
            "intent": "emergency",
            "keys": ["sos", "emergency", "help", "बेहोश", "आपात", "ತುರ್ತು", "ಸಹಾಯ"],
            "en": "I am marking this as an emergency. Call local emergency services now and keep the patient safe until help arrives.",
            "hi": "मैं इसे आपात स्थिति मान रहा हूं। तुरंत स्थानीय आपात सेवा को कॉल करें और मदद आने तक मरीज को सुरक्षित रखें।",
            "kn": "ಇದನ್ನು ತುರ್ತು ಸ್ಥಿತಿ ಎಂದು ಗುರುತಿಸುತ್ತಿದ್ದೇನೆ. ತಕ್ಷಣ ಸ್ಥಳೀಯ ತುರ್ತು ಸೇವೆಗೆ ಕರೆ ಮಾಡಿ ಮತ್ತು ಸಹಾಯ ಬರುವವರೆಗೆ ರೋಗಿಯನ್ನು ಸುರಕ್ಷಿತವಾಗಿಡಿ.",
        },
        {
            "intent": "chest_pain",
            "keys": ["chest pain", "heart pain", "सीने", "छाती", "ಎದೆ ನೋವು", "ಹೃದಯ"],
            "en": "Chest pain can be serious. Stop activity, sit upright, avoid driving, and call emergency services immediately.",
            "hi": "सीने में दर्द गंभीर हो सकता है। काम रोकें, सीधे बैठें, वाहन न चलाएं और तुरंत आपात सेवा को कॉल करें।",
            "kn": "ಎದೆ ನೋವು ಗಂಭೀರವಾಗಿರಬಹುದು. ಚಟುವಟಿಕೆ ನಿಲ್ಲಿಸಿ, ನೇರವಾಗಿ ಕುಳಿತುಕೊಳ್ಳಿ, ವಾಹನ ಚಲಾಯಿಸಬೇಡಿ ಮತ್ತು ತಕ್ಷಣ ತುರ್ತು ಸೇವೆಗೆ ಕರೆ ಮಾಡಿ.",
        },
        {
            "intent": "breathing",
            "keys": ["breath", "breathing", "asthma", "oxygen", "सांस", "ऑक्सीजन", "ಉಸಿರ", "ಆಮ್ಲಜನಕ"],
            "en": "Sit upright, loosen tight clothing, check oxygen if available, and use prescribed inhaler or oxygen support. Seek urgent help if breathlessness is severe.",
            "hi": "सीधे बैठें, तंग कपड़े ढीले करें, उपलब्ध हो तो ऑक्सीजन जांचें और निर्धारित इनहेलर या ऑक्सीजन सपोर्ट लें। सांस ज्यादा फूल रही हो तो तुरंत मदद लें।",
            "kn": "ನೇರವಾಗಿ ಕುಳಿತುಕೊಳ್ಳಿ, ಬಿಗಿಯಾದ ಬಟ್ಟೆ ಸಡಿಲಿಸಿ, ಸಾಧ್ಯವಾದರೆ ಆಮ್ಲಜನಕ ಪರೀಕ್ಷಿಸಿ ಮತ್ತು ಸೂಚಿಸಿದ inhaler ಅಥವಾ oxygen support ಬಳಸಿ. ಉಸಿರಾಟ ತೀವ್ರವಾದರೆ ತುರ್ತು ಸಹಾಯ ಪಡೆಯಿರಿ.",
        },
        {
            "intent": "fever",
            "keys": ["fever", "temperature", "cold", "बुखार", "तापमान", "जुकाम", "ಜ್ವರ", "ತಾಪಮಾನ", "ಶೀತ"],
            "en": "Drink fluids, rest, check temperature every few hours, and consider paracetamol only as directed. Seek care for high fever, confusion, rash, or breathing trouble.",
            "hi": "तरल पदार्थ लें, आराम करें, तापमान जांचते रहें और निर्देशानुसार ही पैरासिटामोल लें। तेज बुखार, भ्रम, दाने या सांस की दिक्कत हो तो डॉक्टर से मिलें।",
            "kn": "ದ್ರವಗಳನ್ನು ಕುಡಿಯಿರಿ, ವಿಶ್ರಾಂತಿ ತೆಗೆದುಕೊಳ್ಳಿ, ತಾಪಮಾನ ಪರೀಕ್ಷಿಸಿ ಮತ್ತು ಸೂಚನೆಯಂತೆ ಮಾತ್ರ paracetamol ತೆಗೆದುಕೊಳ್ಳಿ. ಹೆಚ್ಚಿನ ಜ್ವರ, ಗೊಂದಲ, ಚರ್ಮದ ದದ್ದು ಅಥವಾ ಉಸಿರಾಟದ ತೊಂದರೆ ಇದ್ದರೆ ವೈದ್ಯರನ್ನು ಸಂಪರ್ಕಿಸಿ.",
        },
        {
            "intent": "headache",
            "keys": ["headache", "migraine", "head pain", "सिर दर्द", "माइग्रेन", "ತಲೆ ನೋವು", "ಮೈಗ್ರೇನ್"],
            "en": "Rest in a quiet place, drink water, and avoid screens. Seek urgent care if headache is sudden, severe, after injury, or with weakness or vision changes.",
            "hi": "शांत जगह पर आराम करें, पानी पिएं और स्क्रीन से बचें। अचानक तेज सिरदर्द, चोट के बाद दर्द, कमजोरी या नजर में बदलाव हो तो तुरंत इलाज लें।",
            "kn": "ಶಾಂತ ಸ್ಥಳದಲ್ಲಿ ವಿಶ್ರಾಂತಿ ಮಾಡಿ, ನೀರು ಕುಡಿಯಿರಿ ಮತ್ತು screen ತಪ್ಪಿಸಿ. ತಲೆನೋವು ಅಕಸ್ಮಾತ್ ತೀವ್ರವಾಗಿದ್ದರೆ, ಗಾಯದ ನಂತರ ಬಂದರೆ, ದುರ್ಬಲತೆ ಅಥವಾ ದೃಷ್ಟಿ ಬದಲಾವಣೆ ಇದ್ದರೆ ತುರ್ತು ಚಿಕಿತ್ಸೆ ಪಡೆಯಿರಿ.",
        },
        {
            "intent": "bp",
            "keys": ["bp", "blood pressure", "hypertension", "pressure", "ब्लड प्रेशर", "बीपी", "रक्तचाप", "ಬಿಪಿ", "ರಕ್ತದ ಒತ್ತಡ"],
            "en": "Sit calmly for 5 minutes and recheck BP. If it is very high, or you have chest pain, breathlessness, or weakness, seek emergency care.",
            "hi": "5 मिनट शांत बैठकर BP दोबारा जांचें। अगर BP बहुत ज्यादा है या सीने में दर्द, सांस की दिक्कत या कमजोरी है, तो आपात मदद लें।",
            "kn": "5 ನಿಮಿಷ ಶಾಂತವಾಗಿ ಕುಳಿತು BP ಮತ್ತೆ ಪರೀಕ್ಷಿಸಿ. BP ತುಂಬಾ ಹೆಚ್ಚಿದ್ದರೆ ಅಥವಾ ಎದೆ ನೋವು, ಉಸಿರಾಟ ತೊಂದರೆ, ದುರ್ಬಲತೆ ಇದ್ದರೆ ತುರ್ತು ಸಹಾಯ ಪಡೆಯಿರಿ.",
        },
        {
            "intent": "diabetes",
            "keys": ["sugar", "diabetes", "glucose", "insulin", "शुगर", "डायबिटीज", "ग्लूकोज", "ಸಕ್ಕರೆ", "ಮಧುಮೇಹ", "ಗ್ಲೂಕೋಸ್"],
            "en": "Check glucose, drink water, avoid sugary food, and follow your diabetes plan. If glucose is very high or very low, contact medical support.",
            "hi": "ग्लूकोज जांचें, पानी पिएं, मीठा भोजन न लें और अपनी डायबिटीज योजना का पालन करें। बहुत ज्यादा या बहुत कम शुगर हो तो डॉक्टर से संपर्क करें।",
            "kn": "ಗ್ಲೂಕೋಸ್ ಪರಿಶೀಲಿಸಿ, ನೀರು ಕುಡಿಯಿರಿ, ಸಿಹಿ ಆಹಾರ ತಪ್ಪಿಸಿ ಮತ್ತು diabetes care plan ಅನುಸರಿಸಿ. ಸಕ್ಕರೆ ತುಂಬಾ ಹೆಚ್ಚು ಅಥವಾ ಕಡಿಮೆ ಇದ್ದರೆ ವೈದ್ಯಕೀಯ ಸಹಾಯ ಪಡೆಯಿರಿ.",
        },
        {
            "intent": "medicine",
            "keys": ["medicine", "tablet", "dose", "medication", "दवा", "गोली", "ಮದ್ದು", "ಔಷಧಿ", "ಗೊಳಿ"],
            "en": "Take medicines only as prescribed. I can remind you to record doses, but a clinician should confirm changes or missed-dose decisions.",
            "hi": "दवा केवल डॉक्टर के निर्देशानुसार लें। मैं dose record करने में मदद कर सकता हूं, लेकिन बदलाव या missed dose के लिए डॉक्टर से पूछें।",
            "kn": "ಔಷಧಿಯನ್ನು ವೈದ್ಯರು ಸೂಚಿಸಿದಂತೆ ಮಾತ್ರ ತೆಗೆದುಕೊಳ್ಳಿ. Dose ದಾಖಲಿಸಲು ನಾನು ಸಹಾಯ ಮಾಡುತ್ತೇನೆ, ಆದರೆ ಬದಲಾವಣೆ ಅಥವಾ missed dose ಬಗ್ಗೆ ವೈದ್ಯರನ್ನು ಕೇಳಿ.",
        },
    ]

    lang_key = {"English": "en", "Hindi": "hi", "Kannada": "kn"}[language]
    for rule in rules:
        if any(key in cleaned for key in rule["keys"]):
            return rule[lang_key], rule["intent"]

    fallback = {
        "English": "I understand. Please share your main symptom, duration, and latest vitals if available. For severe symptoms, contact emergency services immediately.",
        "Hindi": "मैं समझ रहा हूं। कृपया अपना मुख्य लक्षण, अवधि और उपलब्ध latest vitals बताएं। गंभीर लक्षण हों तो तुरंत आपात सेवा से संपर्क करें।",
        "Kannada": "ನಾನು ಅರ್ಥಮಾಡಿಕೊಂಡೆ. ದಯವಿಟ್ಟು ಮುಖ್ಯ ಲಕ್ಷಣ, ಎಷ್ಟು ಸಮಯದಿಂದ ಇದೆ, ಮತ್ತು ಲಭ್ಯವಿದ್ದರೆ latest vitals ತಿಳಿಸಿ. ತೀವ್ರ ಲಕ್ಷಣಗಳಿದ್ದರೆ ತಕ್ಷಣ ತುರ್ತು ಸೇವೆಗೆ ಸಂಪರ್ಕಿಸಿ.",
    }
    return fallback[language], "general"


def audio_to_text(uploaded_file, language):
    recognizer = sr.Recognizer()
    suffix = Path(uploaded_file.name).suffix or ".wav"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded_file.getvalue())
        temp_path = tmp.name
    try:
        with sr.AudioFile(temp_path) as source:
          audio = recognizer.record(source)
    
        return recognizer.recognize_google(audio, language=LANGUAGE_META[language]["code"]), None
    except sr.UnknownValueError:
        return "", "Could not understand the uploaded audio. Try a clearer recording."
    except sr.RequestError as exc:
        return "", f"Speech recognition service is unavailable: {exc}"
    except Exception as exc:
        return "", f"Audio processing failed: {exc}"
    finally:
        try:
            os.remove(temp_path)
        except OSError:
            pass


def text_to_speech(text, language):
    try:
        tts = gTTS(text=text, lang=LANGUAGE_META[language]["tts"], slow=False)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
            tts.save(tmp.name)
            audio_bytes = Path(tmp.name).read_bytes()
        os.remove(tmp.name)
        return audio_bytes, None
    except Exception as exc:
        return None, f"Text-to-speech is unavailable: {exc}"


def save_voice_command(patient_id, language, user_text, assistant_text, intent):
    execute(
        """
        INSERT INTO voice_commands (patient_id, language, user_text, assistant_text, intent, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (patient_id, language, user_text, assistant_text, intent, datetime.now().isoformat(timespec="seconds")),
    )


def create_emergency(patient_id, alert_type, priority, description, action, status="Active"):
    execute(
        """
        INSERT INTO emergencies (patient_id, alert_type, priority, description, recommended_action, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (patient_id, alert_type, priority, description, action, status, datetime.now().isoformat(timespec="seconds")),
    )


def render_metric(label, value, hint=""):
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="label">{label}</div>
            <div class="value">{value}</div>
            <div class="hint">{hint}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def hero():
    st.markdown(
        """
        <div class="hero">
          <div class="eyebrow">AI Multilingual Healthcare Command Center</div>
          <h1>Niramaya Care</h1>
          <p>
            A glassmorphism healthcare cockpit with patient profiles, voice-first symptom guidance,
            smart vitals scoring, emergency escalation, and real-time analytics..
          </p>
          <div class="status-pill">Voice Assistant: English | Hindi | Kannada</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def sidebar():
    st.sidebar.title("Niramaya Care")
    st.sidebar.caption("Digital health access, voice guidance, and emergency readiness.")
    pages = [
        "AI Voice Assistant",
        "Patient Registration",
        "Smart Monitoring",
        "Emergency Center",
        "Analytics Dashboard",
    ]
    return st.sidebar.radio("Navigation", pages, label_visibility="collapsed")


def page_voice_assistant():
    hero()
    st.write("")
    options = patient_options()
    if not options:
        st.warning("Register a patient first.")
        return

    col_left, col_right = st.columns([1.28, 0.72], gap="large")
    with col_left:
        st.markdown("### Voice Health Assistant")
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        patient_label = st.selectbox("Patient", list(options.keys()), key="voice_patient")
        language = st.radio("Assistant Language", list(LANGUAGE_META.keys()), horizontal=True)
        uploaded_audio = st.file_uploader("Upload voice command (.wav, .aiff, .flac)", type=["wav", "aiff", "aif", "flac"])

        recognized_text = ""
        if uploaded_audio and st.button("Transcribe Voice Command"):
            with st.spinner("Listening through the care assistant..."):
                recognized_text, error = audio_to_text(uploaded_audio, language)
            if error:
                st.error(error)
            elif recognized_text:
                st.success(f"Recognized: {recognized_text}")
                st.session_state["last_voice_text"] = recognized_text

        default_text = st.session_state.get("last_voice_text", "")
        prompt = st.text_area(
            "Speak or type a health concern",
            value=default_text,
            placeholder="Example: I have chest pain and shortness of breath",
            height=110,
        )

        c1, c2, c3 = st.columns([1, 1, 1])
        send_clicked = c1.button("Ask Assistant", use_container_width=True)
        sos_clicked = c2.button("Trigger SOS", use_container_width=True)
        clear_clicked = c3.button("Clear Chat", use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

        if "chat" not in st.session_state:
            st.session_state["chat"] = []

        if clear_clicked:
            st.session_state["chat"] = []
            st.session_state["last_voice_text"] = ""
            st.rerun()

        patient_id = options[patient_label]
        if sos_clicked:
            prompt = "SOS emergency help"
            create_emergency(
                patient_id,
                "Voice SOS",
                "Critical",
                "Patient triggered SOS from the multilingual assistant.",
                "Call emergency services, notify caregiver, keep patient airway clear, and monitor vitals.",
            )

        if send_clicked or sos_clicked:
            if not prompt.strip():
                st.warning("Please type a health concern or upload an audio command.")
            else:
                answer, intent = assistant_response(prompt, language)
                save_voice_command(patient_id, language, prompt, answer, intent)
                st.session_state["chat"].append({"role": "user", "text": prompt, "language": language})
                st.session_state["chat"].append({"role": "assistant", "text": answer, "language": language, "intent": intent})
                audio, audio_error = text_to_speech(answer, language)
                st.session_state["last_audio"] = audio
                st.session_state["last_audio_error"] = audio_error
                if intent in {"emergency", "chest_pain", "breathing"}:
                    priority = "Critical" if intent in {"emergency", "chest_pain"} else "High"
                    create_emergency(patient_id, f"Voice {intent.replace('_', ' ').title()}", priority, prompt, answer)

        st.markdown("### Conversation")
        if not st.session_state["chat"]:
            st.info("Start with a typed message or upload a short voice command. The assistant will answer and play audio.")
        for item in st.session_state["chat"][-10:]:
            row_class = "chat-user" if item["role"] == "user" else "chat-bot"
            name = "You" if item["role"] == "user" else "Niramaya AI"
            st.markdown(
                f"""
                <div class="chat-row {row_class}">
                  <div class="bubble"><strong>{name}</strong><br>{item["text"]}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        if st.session_state.get("last_audio"):
            st.audio(st.session_state["last_audio"], format="audio/mp3")
        elif st.session_state.get("last_audio_error"):
            st.caption(st.session_state["last_audio_error"])

    with col_right:
        st.markdown("### Assistant Intelligence")
        commands = query_df("SELECT * FROM voice_commands ORDER BY created_at DESC LIMIT 50")
        today = commands[pd.to_datetime(commands["created_at"]).dt.date == datetime.now().date()] if not commands.empty else pd.DataFrame()
        render_metric("Voice Commands", len(commands), "Tracked in SQLite")
        render_metric("Today", len(today), "Assistant interactions")
        top_intent = commands["intent"].mode().iloc[0] if not commands.empty else "none"
        render_metric("Top Intent", top_intent.replace("_", " ").title(), "Rule-based triage")
        st.markdown("### Quick Commands")
        quick_prompts = [
            "I have chest pain",
            "My oxygen is low",
            "मुझे सांस लेने में दिक्कत है",
            "ನನಗೆ ಜ್ವರ ಇದೆ",
        ]
        for quick in quick_prompts:
            st.code(quick, language=None)
        st.markdown('<p class="footer-note">Medical disclaimer: guidance is educational and cannot replace emergency or clinical care.</p>', unsafe_allow_html=True)


def page_patient_registration():
    st.markdown("## Patient Registration")
    st.caption("Create a digital health profile with unique Patient ID and emergency-ready metadata.")
    left, right = st.columns([0.9, 1.1], gap="large")
    with left:
        with st.form("registration_form", clear_on_submit=True):
            name = st.text_input("Full Name")
            age = st.number_input("Age", min_value=0, max_value=120, value=32)
            gender = st.selectbox("Gender", ["Female", "Male", "Other", "Prefer not to say"])
            phone = st.text_input("Phone")
            blood_group = st.selectbox("Blood Group", ["O+", "O-", "A+", "A-", "B+", "B-", "AB+", "AB-"])
            language = st.selectbox("Preferred Language", ["English", "Hindi", "Kannada"])
            allergies = st.text_input("Allergies", placeholder="None / Penicillin / Sulfa")
            chronic = st.text_input("Chronic Conditions", placeholder="Diabetes, Hypertension, Asthma")
            emergency_contact = st.text_input("Emergency Contact")
            address = st.text_area("Address", height=80)
            submitted = st.form_submit_button("Create Digital Health Profile", use_container_width=True)

        if submitted:
            if not name or not phone:
                st.error("Name and phone are required.")
            else:
                patient_id = generate_patient_id(name, phone)
                execute(
                    """
                    INSERT INTO patients VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        patient_id,
                        name,
                        age,
                        gender,
                        phone,
                        blood_group,
                        language,
                        allergies or "None",
                        chronic or "None",
                        emergency_contact,
                        address,
                        datetime.now().isoformat(timespec="seconds"),
                    ),
                )
                st.success(f"Digital Health Profile created: {patient_id}")

    with right:
        st.markdown("### Registered Patients")
        patients = get_patients()
        if patients.empty:
            st.info("No patients registered yet.")
        else:
            st.dataframe(
                patients[["patient_id", "name", "age", "gender", "blood_group", "language", "chronic_conditions"]],
                use_container_width=True,
                hide_index=True,
            )
            selected = st.selectbox("View Digital Health Profile", patients["patient_id"].tolist())
            profile = patients[patients["patient_id"] == selected].iloc[0]
            st.markdown(
                f"""
                <div class="glass-card">
                  <h3>{profile['name']}</h3>
                  <p><strong>Patient ID:</strong> {profile['patient_id']}</p>
                  <p><strong>Blood Group:</strong> {profile['blood_group']} | <strong>Language:</strong> {profile['language']}</p>
                  <p><strong>Conditions:</strong> {profile['chronic_conditions']}</p>
                  <p><strong>Allergies:</strong> {profile['allergies']}</p>
                  <p><strong>Emergency:</strong> {profile['emergency_contact']}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )


def page_monitoring():
    st.markdown("## Smart Health Monitoring")
    st.caption("Enter patient vitals, calculate health score, assign risk, and trigger oxygen-drop alerts.")
    options = patient_options()
    if not options:
        st.warning("Register a patient first.")
        return

    left, right = st.columns([0.9, 1.1], gap="large")
    with left:
        st.markdown("### Vitals Input")
        patient_label = st.selectbox("Patient", list(options.keys()), key="monitor_patient")
        systolic = st.number_input("Systolic BP", 70, 240, 124)
        diastolic = st.number_input("Diastolic BP", 40, 140, 80)
        heart_rate = st.number_input("Heart Rate", 35, 180, 78)
        oxygen = st.number_input("Oxygen SpO2", 50, 100, 97)
        temperature = st.number_input("Temperature F", 92.0, 106.0, 98.6, step=0.1)
        glucose = st.number_input("Glucose mg/dL", 40, 360, 104)
        score, risk, recs = calculate_health_score(systolic, diastolic, heart_rate, oxygen, temperature, glucose)
        st.progress(score / 100, text=f"Health Score: {score}/100")
        risk_class = {"Low": "risk-low", "Medium": "risk-medium", "High": "risk-high"}[risk]
        st.markdown(f'Risk Level: <strong class="{risk_class}">{risk}</strong>', unsafe_allow_html=True)
        for rec in recs:
            st.info(rec)
        if st.button("Save Vitals", use_container_width=True):
            patient_id = options[patient_label]
            execute(
                """
                INSERT INTO vitals
                (patient_id, systolic, diastolic, heart_rate, oxygen, temperature, glucose, health_score, risk_level, recommendations, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    patient_id,
                    systolic,
                    diastolic,
                    heart_rate,
                    oxygen,
                    temperature,
                    glucose,
                    score,
                    risk,
                    "; ".join(recs),
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
            if oxygen < 90:
                create_emergency(
                    patient_id,
                    "Oxygen Drop",
                    "Critical",
                    f"SpO2 recorded at {oxygen}%.",
                    "Start oxygen support, call emergency services, and continuously monitor pulse and consciousness.",
                )
            st.success("Vitals saved and risk assessed.")

    with right:
        vitals = query_df("SELECT * FROM vitals ORDER BY created_at DESC")
        c1, c2, c3 = st.columns(3)
        latest = vitals.iloc[0] if not vitals.empty else None
        with c1:
            render_metric("Latest Score", int(latest["health_score"]) if latest is not None else "-", "Out of 100")
        with c2:
            render_metric("Latest Risk", latest["risk_level"] if latest is not None else "-", "Risk band")
        with c3:
            avg_oxygen = round(vitals["oxygen"].mean(), 1) if not vitals.empty else "-"
            render_metric("Avg Oxygen", avg_oxygen, "SpO2 trend")
        if not vitals.empty:
            chart_df = vitals.sort_values("created_at")
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=chart_df["created_at"], y=chart_df["health_score"], mode="lines+markers", name="Health Score"))
            fig.add_trace(go.Scatter(x=chart_df["created_at"], y=chart_df["oxygen"], mode="lines+markers", name="Oxygen"))
            fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=360)
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(vitals[["patient_id", "systolic", "diastolic", "heart_rate", "oxygen", "health_score", "risk_level", "created_at"]], use_container_width=True, hide_index=True)


def page_emergency():
    st.markdown("## Emergency Response Center")
    st.caption("SOS alerts, oxygen-drop triage, emergency timeline, priority assignment, and recommended actions.")
    options = patient_options()
    left, right = st.columns([0.88, 1.12], gap="large")
    with left:
        st.markdown("### Create Alert")
        if not options:
            st.warning("Register a patient first.")
        else:
            patient_label = st.selectbox("Patient", list(options.keys()), key="emergency_patient")
            alert_type = st.selectbox("Alert Type", ["SOS", "Oxygen Drop", "Chest Pain", "High BP", "Fall Detection", "Medication Issue"])
            priority = st.selectbox("Priority", ["Critical", "High", "Medium", "Low"])
            description = st.text_area("Situation", placeholder="Describe symptoms, vitals, and location", height=110)
            default_action = {
                "SOS": "Call emergency services, notify caregiver, and keep patient safe.",
                "Oxygen Drop": "Start oxygen support, sit patient upright, call emergency response.",
                "Chest Pain": "Stop activity, call emergency services, do not let patient drive.",
                "High BP": "Repeat BP after rest, watch for chest pain, weakness, or confusion.",
                "Fall Detection": "Do not move patient if fracture or head injury is suspected.",
                "Medication Issue": "Verify medicine name, dose, timing, and contact clinician or poison helpline if overdose.",
            }[alert_type]
            action = st.text_area("Recommended Action", value=default_action, height=110)
            if st.button("Launch Emergency Protocol", use_container_width=True):
                create_emergency(options[patient_label], alert_type, priority, description or alert_type, action)
                st.success("Emergency protocol launched and logged.")

    with right:
        emergencies = query_df(
            """
            SELECT e.*, p.name FROM emergencies e
            LEFT JOIN patients p ON e.patient_id = p.patient_id
            ORDER BY e.created_at DESC
            """
        )
        if emergencies.empty:
            st.info("No emergency alerts yet.")
        else:
            c1, c2, c3 = st.columns(3)
            with c1:
                render_metric("Active Alerts", len(emergencies[emergencies["status"] == "Active"]), "Live protocols")
            with c2:
                render_metric("Critical", len(emergencies[emergencies["priority"] == "Critical"]), "Needs immediate action")
            with c3:
                render_metric("Oxygen Drops", len(emergencies[emergencies["alert_type"] == "Oxygen Drop"]), "SpO2 alerts")
            st.markdown("### Timeline")
            for row in emergencies.head(8).itertuples():
                st.markdown(
                    f"""
                    <div class="timeline-item">
                      <strong>{row.priority} - {row.alert_type}</strong><br>
                      <span>{row.created_at} | {row.name or row.patient_id}</span>
                      <p>{row.description}</p>
                      <p><strong>Action:</strong> {row.recommended_action}</p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )


def page_analytics():
    st.markdown("## Healthcare Analytics Dashboard")
    st.caption("KPIs, patient statistics, emergency analytics, and voice assistant intelligence.")
    patients = get_patients()
    vitals = query_df("SELECT * FROM vitals")
    emergencies = query_df("SELECT * FROM emergencies")
    commands = query_df("SELECT * FROM voice_commands")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_metric("Patients", len(patients), "Digital profiles")
    with c2:
        avg_score = round(vitals["health_score"].mean(), 1) if not vitals.empty else "-"
        render_metric("Avg Score", avg_score, "Population health")
    with c3:
        render_metric("Alerts", len(emergencies), "Emergency records")
    with c4:
        render_metric("Voice Uses", len(commands), "Assistant commands")

    chart_a, chart_b = st.columns(2, gap="large")
    with chart_a:
        if not vitals.empty:
            fig = px.histogram(vitals, x="risk_level", color="risk_level", title="Risk Level Distribution", template="plotly_dark")
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=340, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
    with chart_b:
        if not emergencies.empty:
            fig = px.pie(emergencies, names="priority", title="Emergency Priority Mix", hole=0.55, template="plotly_dark")
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", height=340)
            st.plotly_chart(fig, use_container_width=True)

    chart_c, chart_d = st.columns(2, gap="large")
    with chart_c:
        if not commands.empty:
            fig = px.bar(commands.groupby("language", as_index=False).size(), x="language", y="size", title="Voice Commands by Language", template="plotly_dark")
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=340, yaxis_title="Commands")
            st.plotly_chart(fig, use_container_width=True)
    with chart_d:
        if not commands.empty:
            intent_df = commands.groupby("intent", as_index=False).size().sort_values("size", ascending=False)
            fig = px.bar(intent_df, x="size", y="intent", orientation="h", title="Top Assistant Intents", template="plotly_dark")
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=340, xaxis_title="Commands", yaxis_title="")
            st.plotly_chart(fig, use_container_width=True)

    st.markdown("### Data Tables")
    tabs = st.tabs(["Patients", "Vitals", "Emergencies", "Voice Commands"])
    with tabs[0]:
        st.dataframe(patients, use_container_width=True, hide_index=True)
    with tabs[1]:
        st.dataframe(vitals.sort_values("created_at", ascending=False) if not vitals.empty else vitals, use_container_width=True, hide_index=True)
    with tabs[2]:
        st.dataframe(emergencies.sort_values("created_at", ascending=False) if not emergencies.empty else emergencies, use_container_width=True, hide_index=True)
    with tabs[3]:
        st.dataframe(commands.sort_values("created_at", ascending=False) if not commands.empty else commands, use_container_width=True, hide_index=True)


def main():
    st.set_page_config(page_title=APP_NAME, page_icon="🩺", layout="wide", initial_sidebar_state="expanded")
    load_css()
    init_database()
    page = sidebar()

    if page == "AI Voice Assistant":
        page_voice_assistant()
    elif page == "Patient Registration":
        page_patient_registration()
    elif page == "Smart Monitoring":
        page_monitoring()
    elif page == "Emergency Center":
        page_emergency()
    elif page == "Analytics Dashboard":
        page_analytics()

    st.sidebar.divider()
    st.sidebar.caption("Built for hackathon demos. Not a substitute for professional medical care.")


if __name__ == "__main__":
    main()
