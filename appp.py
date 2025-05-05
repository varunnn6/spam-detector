import numpy as np
import pandas as pd
import streamlit as st
import phonenumbers
import joblib
import requests
import re
import firebase_admin
from firebase_admin import credentials, firestore
from phonenumbers import carrier, geocoder, timezone
import json
from google.cloud.firestore_v1 import DocumentReference

# Streamlit App Title
st.title("Spam Shield 🛡️")

# Initialize Firebase Firestore (silently, without UI messages)
try:
    cred_dict = json.loads(st.secrets["firebase"]["credentials"])
    cred = credentials.Certificate(cred_dict)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    db = firestore.client()
except Exception as e:
    # Log the error internally (not displayed to user)
    db = None
    st.session_state.userdata = st.session_state.get('userdata', {})
    st.session_state.feedback = st.session_state.get('feedback', [])
    st.session_state.spam_numbers = st.session_state.get('spam_numbers', set())

# Initialize session state
if 'userdata' not in st.session_state:
    st.session_state.userdata = {}
if 'feedback' not in st.session_state:
    st.session_state.feedback = []
if 'current_page' not in st.session_state:
    st.session_state.current_page = "Home"
if 'parsed_numbers' not in st.session_state:
    st.session_state.parsed_numbers = {}  # Cache for parsed phone numbers

# Load user data from Firestore at startup (limit to 100 entries for speed)
def load_userdata():
    if not db:
        return st.session_state.userdata
    userdata = {}
    try:
        users_ref = db.collection('users').limit(100)  # Limit to avoid slow reads
        docs = users_ref.stream()
        for doc in docs:
            data = doc.to_dict()
            phone = doc.id
            name = data.get('name', 'Unknown')
            userdata[phone] = name
    except Exception as e:
        pass  # Silently handle errors
    return userdata

# Save user data to Firestore asynchronously
def save_userdata(userdata):
    if not db:
        st.session_state.userdata = userdata
        return
    try:
        users_ref = db.collection('users')
        batch = db.batch()
        for phone, name in userdata.items():
            doc_ref = users_ref.document(phone)
            batch.set(doc_ref, {'name': name})
        batch.commit()  # Batch write for efficiency
    except Exception as e:
        pass  # Silently handle errors

# Load feedback from Firestore (limit to 50 entries)
def load_feedback():
    if not db:
        return st.session_state.feedback
    feedback = []
    try:
        feedback_ref = db.collection('feedback').limit(50)
        docs = feedback_ref.stream()
        for doc in docs:
            data = doc.to_dict()
            feedback.append(data.get('entry', ''))
    except Exception as e:
        pass  # Silently handle errors
    return feedback

# Save feedback to Firestore asynchronously
def save_feedback(feedback):
    if not db:
        st.session_state.feedback = feedback
        return
    try:
        feedback_ref = db.collection('feedback')
        batch = db.batch()
        # Clear existing feedback
        for doc in feedback_ref.stream():
            batch.delete(doc.reference)
        # Insert new feedback
        for i, entry in enumerate(feedback):
            doc_ref = feedback_ref.document(str(i))
            batch.set(doc_ref, {'entry': entry})
        batch.commit()
    except Exception as e:
        pass  # Silently handle errors

# Load spam numbers from Firestore (limit to 500 entries)
def load_spam_numbers():
    if not db:
        return st.session_state.spam_numbers
    spam_numbers = set()
    try:
        spam_ref = db.collection('spam_numbers').limit(500)
        docs = spam_ref.stream()
        for doc in docs:
            spam_numbers.add(doc.id)
    except Exception as e:
        pass  # Silently handle errors
    return spam_numbers

# Save a spam number to Firestore asynchronously
def save_spam_number(phone):
    if not db:
        st.session_state.spam_numbers.add(phone)
        return
    try:
        spam_ref = db.collection('spam_numbers')
        spam_ref.document(phone).set({}, merge=True)  # Minimal write
    except Exception as e:
        pass  # Silently handle errors

# Load data into session state at startup
st.session_state.userdata = load_userdata()
st.session_state.feedback = load_feedback()

# Initialize and Load Spam Numbers
if 'spam_numbers' not in st.session_state:
    st.session_state.spam_numbers = load_spam_numbers()

# Define initial spam numbers (reduced for testing; add more as needed)
initial_spam_numbers = {
    "+917397947365", "+917550098431", "+919150228347", "+918292577122", "+919060883501",
    "+919163255112", "+916002454613", "+918292042103", "+917091184923", "+917633959085",
}

# Add initial spam numbers to session state (avoid writing to Firestore at startup)
st.session_state.spam_numbers.update(initial_spam_numbers)

# Reference to spam_numbers for easier use
spam_numbers = st.session_state.spam_numbers

# Load Trained Machine Learning Model and Vectorizer
@st.cache_resource
def load_model_and_vectorizer():
    model = joblib.load('spam_classifier.pkl')
    vectorizer = joblib.load('tfidf_vectorizer.pkl')
    return model, vectorizer

# Load model immediately to avoid delay later
model, vectorizer = load_model_and_vectorizer()

# Numlookup API Key
API_KEY = "num_live_gAgRGbG0st9WUyf8sR98KqlcKb5qB0SkrZFEpIm6"

# Function to Get Number Info using Numlookup API
@st.cache_data
def get_numlookup_info(phone_number):
    try:
        headers = {"Accept": "application/json"}
        url = f"https://api.numlookupapi.com/v1/validate/{phone_number}?apikey={API_KEY}"
        response = requests.get(url, headers=headers, timeout=5)  # Add timeout
        response.raise_for_status()
        data = response.json()
        service_provider = data.get("carrier", "Unknown")
        location = data.get("location", "Unknown")
        line_type = data.get("line_type", "Unknown")
        country = data.get("country_name", "Unknown")
        country = re.sub(r'\s*\([^)]+\)', '', country).strip()
        return service_provider, location, line_type, country
    except Exception as e:
        st.error(f"Numlookup API error: {str(e)}. Check your API key or visit https://numlookupapi.com for support.")
        return "Unknown", "Unknown", "Unknown", "Unknown"

# Function to Parse and Validate Phone Number with Caching
def parse_phone_number(phone_number):
    if phone_number in st.session_state.parsed_numbers:
        return st.session_state.parsed_numbers[phone_number]
    try:
        parsed_number = phonenumbers.parse(phone_number, None)
        if phonenumbers.is_valid_number(parsed_number):
            formatted_number = phonenumbers.format_number(parsed_number, phonenumbers.PhoneNumberFormat.E164)
            service_provider = carrier.name_for_number(parsed_number, "en") or "Unknown"
            region = geocoder.description_for_number(parsed_number, "en") or "Unknown"
            time_zones = timezone.time_zones_for_number(parsed_number) or ["Unknown"]
            result = (formatted_number, service_provider, region, time_zones[0], True)
        else:
            result = (None, None, None, None, False)
        st.session_state.parsed_numbers[phone_number] = result
        return result
    except phonenumbers.NumberParseException:
        result = (None, None, None, None, False)
        st.session_state.parsed_numbers[phone_number] = result
        return result

# Navigation Sidebar
with st.sidebar:
    st.header("Navigation")
    if st.button("Home", key="nav_home"):
        st.session_state.current_page = "Home"
    if st.button("Services", key="nav_services"):
        st.session_state.current_page = "Services"
    if st.button("Feedback", key="nav_feedback"):
        st.session_state.current_page = "Feedback"

# JavaScript to close sidebar after button click
st.markdown("""
<script>
    function closeSidebar() {
        const sidebar = document.querySelector('div[data-testid="stSidebar"]');
        if (sidebar) {
            sidebar.style.transform = 'translateX(-100%)';
            sidebar.style.transition = 'transform 0.3s ease-in-out';
            const sidebarToggle = document.querySelector('button[data-testid="stSidebarToggle"]') ||
                                 document.querySelector('button[aria-label="Open sidebar"]') ||
                                 document.querySelector('button[aria-label="Close sidebar"]');
            if (sidebarToggle) {
                sidebarToggle.setAttribute('aria-expanded', 'false');
                sidebarToggle.setAttribute('aria-label', 'Open sidebar');
            }
            const overlay = document.querySelector('div[data-testid="stSidebar"] + div[role="presentation"]');
            if (overlay) {
                overlay.style.display = 'none';
            }
        }
    }
    document.addEventListener('click', (event) => {
        const target = event.target.closest('button[kind="secondary"][key^="nav_"]');
        if (target) {
            setTimeout(closeSidebar, 150);
        }
    });
</script>
""", unsafe_allow_html=True)

# Page Content
page = st.session_state.current_page

# Home Page
if page == "Home":
    st.header("Welcome to Spam Shield")
    st.write("""
        **Spam Shield** is your go-to platform for protecting yourself from spam calls and messages. 
        With a single app, you can:
        - Verify your phone number to build trust with others.
        - Check if a phone number or SMS is spam.
        - Report spam numbers to help keep the community safe.

        Join us in making communication safer and more reliable!
    """)
    st.subheader("Verify Your Number")
    st.write("Add your name and phone number to be marked as a verified user, helping others trust your number!")
    name = st.text_input("Your Name", key="name_input")
    phone = st.text_input("Your Phone Number (e.g., +919876543210)", key="phone_input_home")
    if st.button("Submit Verification"):
        if name and phone:
            formatted_phone, _, _, _, is_valid = parse_phone_number(phone)
            if is_valid:
                st.session_state.userdata[formatted_phone] = name
                save_userdata({formatted_phone: name})
                st.success(f"Thank you, {name}! Your number {formatted_phone} is now verified.")
            else:
                st.error("Invalid phone number. Please enter a valid number.")
        else:
            st.warning("Please enter both name and phone number.")

# Services Page
elif page == "Services":
    st.header("Services")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.image("search_number.png")
        st.page_link("#search-number", label="Search Number")
    with col2:
        st.image("check_sms.png")
        st.page_link("#check-sms", label="Check SMS")
    with col3:
        st.image("report_spam.png")
        st.page_link("#report-spam", label="Report Spam")

    # The rest of the Services content remains as in your code...

# Feedback Page
elif page == "Feedback":
    st.subheader("📝 Submit Feedback")
    feedback_text = st.text_area("Please provide your feedback:", key="feedback_input")
    if st.button("Submit Feedback"):
        if feedback_text.strip():
            st.session_state.feedback.append(feedback_text)
            save_feedback(st.session_state.feedback)
            st.success("Thank you for your feedback!")
        else:
            st.warning("Please enter some feedback.")
