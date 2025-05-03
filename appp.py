import numpy as np
import pandas as pd
import streamlit as st
import phonenumbers
import joblib
import requests
from phonenumbers import carrier, geocoder, timezone

# File paths
USERDATA_FILE = "userdata.txt"
FEEDBACK_FILE = "feedback.txt"
SPAM_FILE = "spam_numbers.txt"

# Load session state
if 'userdata' not in st.session_state:
    st.session_state.userdata = {}
if 'feedback' not in st.session_state:
    st.session_state.feedback = []
if 'spam_numbers' not in st.session_state:
    st.session_state.spam_numbers = set()

# Load functions
def load_userdata():
    data = {}
    try:
        with open(USERDATA_FILE, 'r') as f:
            for line in f:
                if line.strip():
                    name, phone = line.strip().split(',')
                    data[phone] = name
    except FileNotFoundError:
        pass
    data.update(st.session_state.userdata)
    return data

def load_feedback():
    fb = []
    try:
        with open(FEEDBACK_FILE, 'r') as f:
            fb = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        pass
    fb.extend(st.session_state.feedback)
    return list(set(fb))

def load_spam_numbers():
    s = set()
    try:
        with open(SPAM_FILE, 'r') as f:
            s.update(line.strip() for line in f if line.strip())
    except FileNotFoundError:
        pass
    s.update(st.session_state.spam_numbers)
    return s

# Load ML model
@st.cache_resource
def load_model_and_vectorizer():
    model = joblib.load('spam_classifier.pkl')
    vectorizer = joblib.load('tfidf_vectorizer.pkl')
    return model, vectorizer

model, vectorizer = load_model_and_vectorizer()

# Phone parsing
def parse_phone_number(number):
    try:
        parsed = phonenumbers.parse(number)
        if not phonenumbers.is_valid_number(parsed):
            return None, "Unknown", "Unknown", "Unknown", False
        formatted = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        provider = carrier.name_for_number(parsed, "en")
        region = geocoder.description_for_number(parsed, "en")
        tz = timezone.time_zones_for_number(parsed)
        time_zone = tz[0] if tz else "Unknown"
        return formatted, provider, region, time_zone, True
    except:
        return None, "Unknown", "Unknown", "Unknown", False

# Numlookup API (optional)
def get_numlookup_info(phone_number):
    api_key = st.secrets.get("NUMLOOKUP_API_KEY", "your_api_key_here")
    url = f"https://www.numlookupapi.com/api/v1/validate/{phone_number}?apikey={api_key}"
    try:
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            d = r.json()
            return d.get("carrier", "Unknown"), d.get("location", "Unknown"), d.get("line_type", "Unknown"), d.get("country_name", "Unknown")
    except:
        pass
    return "Unknown", "Unknown", "Unknown", "Unknown"

# Load data at startup
userdata = load_userdata()
st.session_state.userdata = userdata
feedback = load_feedback()
st.session_state.feedback = feedback
spam_numbers = load_spam_numbers()
st.session_state.spam_numbers = spam_numbers

# Navigation
query_params = st.query_params
page = query_params.get("page", "Home")

# Header Navigation
st.markdown("""
<style>
.nav-bar {
    background: #1a0d3d;
    padding: 10px;
    display: flex;
    justify-content: center;
    gap: 30px;
}
.nav-link {
    color: white !important;
    font-weight: bold;
    font-size: 18px;
    text-decoration: none;
}
.nav-link:hover {
    color: #FFDAB9 !important;
}
.nav-link.active {
    color: #ff4d4d !important;
}
</style>
<div class="nav-bar">
    <a href="?page=Home" class="nav-link {home}">Home</a>
    <a href="?page=Services" class="nav-link {services}">Services</a>
    <a href="?page=Feedback" class="nav-link {feedback}">Feedback</a>
</div>
""".format(
    home="active" if page == "Home" else "",
    services="active" if page == "Services" else "",
    feedback="active" if page == "Feedback" else ""
), unsafe_allow_html=True)

# HOME PAGE
if page == "Home":
    st.title("📞 Spam Shield")
    st.subheader("Stop wasting time on spam calls & messages!")

    name = st.text_input("Your Name")
    phone = st.text_input("Your Phone Number (e.g., +919876543210)")
    if st.button("Submit Verification"):
        if name and phone:
            formatted_phone, _, _, _, valid = parse_phone_number(phone)
            if valid:
                st.session_state.userdata[formatted_phone] = name
                st.success(f"Thanks {name}, your number {formatted_phone} is verified.")
            else:
                st.error("Invalid number.")
        else:
            st.warning("Fill both fields.")

# SERVICES PAGE
elif page == "Services":
    st.header("📲 Phone Number & SMS Checker")

    phone_number = st.text_input("Enter Phone Number:")
    sms_text = st.text_area("Paste SMS Message (Optional)")

    if st.button("Check"):
        if phone_number:
            formatted, local_provider, region, tz, is_valid = parse_phone_number(phone_number)
            if not is_valid:
                st.error("Invalid number")
            else:
                api_provider, location, line_type, country = get_numlookup_info(formatted)
                name = st.session_state.userdata.get(formatted, "Unknown")

                classification = "✅ Not Spam"
                if any(formatted.startswith(p) for p in ["+140", "+91140", "140"]):
                    classification = "🚨 Spam"
                if formatted in st.session_state.spam_numbers:
                    classification = "🚨 Spam"
                if local_provider == "Unknown" and api_provider == "Unknown":
                    classification = "🚨 Spam"

                st.write("**Name:**", name)
                st.write("**Formatted Number:**", formatted)
                st.write("**Provider:**", api_provider or local_provider)
                st.write("**Location:**", location or region)
                st.write("**Line Type:**", line_type)
                st.write("**Time Zone:**", tz)
                st.write("**Country:**", country)
                st.info(f"Classification: {classification}")

        if sms_text:
            text = sms_text.lower()
            X = vectorizer.transform([text])
            pred = model.predict(X)[0]
            st.success("✅ Not Spam" if pred == "ham" else "🚨 Spam")

# FEEDBACK PAGE
elif page == "Feedback":
    st.header("🗣️ Share Feedback or Report Spam")

    feedback_text = st.text_area("Your Feedback")
    if st.button("Submit Feedback"):
        if feedback_text.strip():
            st.session_state.feedback.append(feedback_text.strip())
            st.success("Thanks for your feedback!")

    spam_num = st.text_input("Report Spam Number (e.g., +919999999999)")
    if st.button("Report Spam"):
        formatted, *_ = parse_phone_number(spam_num)
        if formatted:
            st.session_state.spam_numbers.add(formatted)
            st.success(f"Reported {formatted} as spam.")
        else:
            st.error("Invalid number.")

    st.download_button("⬇️ Download Verified Users", data="\n".join(f"{v},{k}" for k, v in st.session_state.userdata.items()), file_name="userdata.txt")
    st.download_button("⬇️ Download Feedback", data="\n".join(st.session_state.feedback), file_name="feedback.txt")
    st.download_button("⬇️ Download Spam Numbers", data="\n".join(st.session_state.spam_numbers), file_name="spam_numbers.txt")
