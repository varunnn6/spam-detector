import numpy as np
import pandas as pd
import streamlit as st
import phonenumbers
import joblib
import requests
from phonenumbers import carrier, geocoder, timezone

# File paths (loaded from the repository via Streamlit Cloud)
USERDATA_FILE = "userdata.txt"
FEEDBACK_FILE = "feedback.txt"
SPAM_FILE = "spam_numbers.txt"

# Initialize session state for data persistence and navigation
if 'userdata' not in st.session_state:
    st.session_state.userdata = {}
if 'feedback' not in st.session_state:
    st.session_state.feedback = []
if 'spam_numbers' not in st.session_state:
    st.session_state.spam_numbers = set()
if 'current_page' not in st.session_state:
    st.session_state.current_page = "Home"  # Default page

# Load data from files at startup
def load_userdata():
    userdata = {}
    try:
        with open(USERDATA_FILE, 'r') as f:
            for line in f:
                if line.strip():
                    name, phone = line.strip().split(',')
                    userdata[phone] = name
    except FileNotFoundError:
        pass  # File might not exist initially
    userdata.update(st.session_state.userdata)
    return userdata

def load_feedback():
    feedback = []
    try:
        with open(FEEDBACK_FILE, 'r') as f:
            feedback = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        pass  # File might not exist initially
    feedback.extend(st.session_state.feedback)
    return list(set(feedback))  # Remove duplicates

def load_spam_numbers():
    spam_numbers = set()
    try:
        with open(SPAM_FILE, 'r') as f:
            spam_numbers.update(line.strip() for line in f if line.strip())
    except FileNotFoundError:
        pass  # File might not exist initially
    spam_numbers.update(st.session_state.spam_numbers)
    return spam_numbers

# Custom CSS for dark theme and styling
st.markdown("""
    <style>
        /* Import modern font */
        @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;700&display=swap');

        /* Global styles for dark theme */
        .stApp {
            background: linear-gradient(135deg, #2b1055, #7597de);
            font-family: 'Montserrat', sans-serif;
            color: #ffffff;
        }
        /* Navigation bar styling */
        .nav-bar {
            background-color: #1a0d3d;
            padding: 10px 0;
            width: 100%;
            display: flex;
            justify-content: center;
            gap: 30px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.3);
        }
        /* Custom styling for navigation buttons */
        .nav-bar div.stButton > button {
            color: #ffffff !important;
            font-size: 18px;
            font-weight: bold;
            text-decoration: none !important;
            padding: 10px 15px;
            border-radius: 5px;
            border: none;
            background-color: transparent;
            transition: all 0.3s ease;
        }
        .nav-bar div.stButton > button:hover {
            color: #FFDAB9 !important; /* Peach color on hover */
            font-size: 20px; /* Slightly larger size on hover */
            background-color: #3b1a7a;
        }
        .nav-bar div.stButton > button.active {
            background-color: #ff4d4d;
            color: #ffffff !important;
            font-size: 18px; /* Ensure active button doesn't increase size */
        }
        /* Header styling (for Home page) */
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 20px;
            background: transparent;
        }
        .header-title {
            font-size: 36px;
            font-weight: bold;
            color: #ffffff;
        }
        .header-link {
            font-size: 18px;
            color: #ffffff !important;
            font-weight: bold;
            text-decoration: none;
            padding: 10px 20px;
            border: 1px solid #ffffff;
            border-radius: 25px;
            transition: all 0.3s ease;
        }
        .header-link:hover {
            background-color: #ffffff;
            color: #2b1055 !important;
        }
        /* Main content styling for Home page */
        .hero-section {
            padding: 50px;
            text-align: left;
        }
        .hero-text {
            font-size: 48px;
            font-weight: bold;
            line-height: 1.2;
            color: #ffffff;
        }
        .hero-text span {
            color: #ff4d4d;
        }
        .sub-hero-text {
            font-size: 28px;
            font-weight: normal;
            color: #ffffff;
            margin-top: 20px;
        }
        /* Subheader styling */
        .subheader {
            color: #ff4d4d;
            font-size: 24px;
            font-family: 'Montserrat', sans-serif;
            margin-top: 20px;
            margin-bottom: 10px;
        }
        /* Input fields styling */
        .stTextInput > div > div > input,
        .stTextArea > div > div > textarea {
            background-color: #3b1a7a !important;
            color: #ffffff !important;
            border: 1px solid #7597de !important;
            border-radius: 5px;
        }
        /* Box styling for sections (like Contact button) */
        .content-box {
            border: 1px solid #ffffff;
            border-radius: 25px;
            padding: 20px;
            margin-top: 20px;
        }
        /* Button styling for other buttons */
        .stButton:not(.nav-bar .stButton) > button {
            background-color: #ff4d4d;
            color: #ffffff;
            border: none;
            padding: 10px 20px;
            border-radius: 5px;
            font-size: 16px;
            cursor: pointer;
            transition: background-color 0.3s ease;
        }
        .stButton:not(.nav-bar .stButton) > button:hover {
            background-color: #e63b3b;
        }
        /* Result styling */
        .result-not-spam {
            background-color: #1a4d3d;
            color: #a3e6c9;
            padding: 10px;
            border-radius: 5px;
            margin-top: 10px;
            font-weight: bold;
        }
        .result-spam {
            background-color: #4d1a1a;
            color: #e6a3a3;
            padding: 10px;
            border-radius: 5px;
            margin-top: 10px;
            font-weight: bold;
        }
        /* Note styling */
        .note {
            color: #b0b0b0;
            font-style: italic;
            margin-top: 5px;
        }
        /* Fade-in animation */
        @keyframes fadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
        }
        .fade-in {
            animation: fadeIn 1s ease-in;
        }
    </style>
""", unsafe_allow_html=True)

# Horizontal Navigation Bar with Buttons
st.markdown('<div class="nav-bar fade-in">', unsafe_allow_html=True)
col1, col2, col3 = st.columns([1, 1, 1])

with col1:
    if st.button("Home", key="nav_home"):
        st.session_state.current_page = "Home"
    # Add 'active' class to the button if it's the current page
    if st.session_state.current_page == "Home":
        st.markdown(
            '<style>.nav-bar div[data-testid="stButton"][id*="nav_home"] > button { background-color: #ff4d4d; }</style>',
            unsafe_allow_html=True
        )

with col2:
    if st.button("Services", key="nav_services"):
        st.session_state.current_page = "Services"
    if st.session_state.current_page == "Services":
        st.markdown(
            '<style>.nav-bar div[data-testid="stButton"][id*="nav_services"] > button { background-color: #ff4d4d; }</style>',
            unsafe_allow_html=True
        )

with col3:
    if st.button("Feedback", key="nav_feedback"):
        st.session_state.current_page = "Feedback"
    if st.session_state.current_page == "Feedback":
        st.markdown(
            '<style>.nav-bar div[data-testid="stButton"][id*="nav_feedback"] > button { background-color: #ff4d4d; }</style>',
            unsafe_allow_html=True
        )

st.markdown('</div>', unsafe_allow_html=True)

# Function to parse phone number
def parse_phone_number(phone_number):
    try:
        parsed_number = phonenumbers.parse(phone_number)
        if not phonenumbers.is_valid_number(parsed_number):
            return None, "Unknown", "Unknown", "Unknown", False
        formatted_number = phonenumbers.format_number(parsed_number, phonenumbers.PhoneNumberFormat.E164)
        local_provider = carrier.name_for_number(parsed_number, "en")
        region = geocoder.description_for_number(parsed_number, "en")
        time_zone = timezone.time_zones_for_number(parsed_number)[0] if timezone.time_zones_for_number(parsed_number) else "Unknown"
        return formatted_number, local_provider, region, time_zone, True
    except phonenumbers.NumberParseException:
        return None, "Unknown", "Unknown", "Unknown", False

# Function to get info from Numlookup API
def get_numlookup_info(phone_number):
    api_key = st.secrets.get("NUMLOOKUP_API_KEY", "your_api_key_here")
    url = f"https://www.numlookupapi.com/api/v1/validate/{phone_number}?apikey={api_key}"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            return (
                data.get("carrier", "Unknown"),
                data.get("location", "Unknown"),
                data.get("line_type", "Unknown"),
                data.get("country_name", "Unknown")
            )
        return "Unknown", "Unknown", "Unknown", "Unknown"
    except requests.RequestException:
        return "Unknown", "Unknown", "Unknown", "Unknown"

# Load ML model and vectorizer
@st.cache_resource
def load_model_and_vectorizer():
    model = joblib.load('spam_classifier.pkl')
    vectorizer = joblib.load('tfidf_vectorizer.pkl')
    return model, vectorizer

model, vectorizer = load_model_and_vectorizer()

# Define spam keywords and trusted sources
SPAM_KEYWORDS = ["won", "click", "link", "prize", "free", "claim", "urgent", "offer", "win", "congratulations", "money", "rupee", "reward", "lottery"]
TRUSTED_SOURCES = ["-SBI", "-HDFC", "-ICICI"]

# Load data at startup
userdata = load_userdata()
st.session_state.userdata = userdata
feedback = load_feedback()
st.session_state.feedback = feedback
spam_numbers = load_spam_numbers()
st.session_state.spam_numbers = spam_numbers

# Render content based on the current page
page = st.session_state.current_page

# Home Page
if page == "Home":
    # Header with title and Contact link
    st.markdown("""
        <div class="header fade-in">
            <div class="header-title">Spam Shield</div>
            <a href="mailto:support@spamshield.com" class="header-link">Contact</a>
        </div>
    """, unsafe_allow_html=True)

    # Hero section with stylized text
    st.markdown("""
        <div class="hero-section fade-in">
            <div class="hero-text">
                Hi,<br>
                SPAM SHIELD IS HERE TO SAVE YOUR TIME RESPONDING TO THE<br>
                <span>SPAM CALLS AND MESSAGES</span>
            </div>
            <div class="sub-hero-text">
                A SINGLE PLATFORM WITH MULTIPLE USE
            </div>
        </div>
    """, unsafe_allow_html=True)
    
    # Verify Your Number section in a box
    st.markdown('<div class="content-box fade-in">', unsafe_allow_html=True)
    st.subheader("Verify Your Number")
    st.write("Add your name and phone number to be marked as a verified user, helping others trust your number!")
    name = st.text_input("Your Name", key="name_input")
    phone = st.text_input("Your Phone Number (e.g., +919876543210)", key="phone_input_home")
    if st.button("Submit Verification"):
        if name and phone:
            formatted_phone, _, _, _, is_valid = parse_phone_number(phone)
            if is_valid:
                st.session_state.userdata[formatted_phone] = name
                st.success(f"Thank you, {name}! Your number {formatted_phone} is now verified.")
                st.info("Note: Data will reset on app restart since the download section has been removed.")
            else:
                st.error("Invalid phone number. Please enter a valid number.")
        else:
            st.warning("Please enter both name and phone number.")
    st.markdown('</div>', unsafe_allow_html=True)

# Services Page
elif page == "Services":
    # Check Phone Number & SMS section in a box
    st.markdown('<div class="content-box fade-in">', unsafe_allow_html=True)
    st.markdown('<div class="subheader">📲 Check Phone Number & SMS</div>', unsafe_allow_html=True)
    with st.container():
        phone_number = st.text_input("Enter Phone Number (e.g., +919876543210):", key="phone_input_services")
    
    if st.button("Check Number"):
        if not phone_number.strip():
            st.warning("Please enter a phone number.")
        else:
            formatted_number, local_provider, region, time_zone, is_valid = parse_phone_number(phone_number)
            if not is_valid:
                st.error("Invalid phone number. Please enter a valid number.")
            else:
                api_provider, location, line_type, country = get_numlookup_info(formatted_number)
                name = st.session_state.userdata.get(formatted_number, "Unknown")
                classification = "✅ Not Spam"
                special_classification = None
                number_without_country = formatted_number[3:] if formatted_number.startswith("+91") else formatted_number
                if number_without_country.startswith("14") or number_without_country.startswith("88265") or number_without_country.startswith("796512"):
                    classification = "🚨 Spam"
                elif number_without_country.startswith("16"):
                    special_classification = "Government or Regulators"
                    classification = "ℹ️ Not Spam"
                if formatted_number in st.session_state.spam_numbers:
                    classification = "🚨 Spam"
                if formatted_number.startswith("+140") or formatted_number.startswith("140"):
                    classification = "🚨 Spam"
                if local_provider == "Unknown" and api_provider == "Unknown":
                    classification = "🚨 Spam"
                if special_classification:
                    classification = f"{classification} ({special_classification})"
                st.markdown(f'<div class="result-{"spam" if "Spam" in classification else "not-spam"} fade-in">**Phone Number:** {formatted_number}</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="result-{"spam" if "Spam" in classification else "not-spam"} fade-in">**Associated Name:** {name}</div>', unsafe_allow_html=True)
                displayed_provider = api_provider if api_provider != "Unknown" else local_provider
                st.markdown(f'<div class="result-{"spam" if "Spam" in classification else "not-spam"} fade-in">📶 **Service Provider:** {displayed_provider}</div>', unsafe_allow_html=True)
                if displayed_provider != "Unknown":
                    st.markdown('<div class="note fade-in">*Note:* The provider may have changed due to Mobile Number Portability (MNP). Verify with the number’s owner if needed.</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="result-{"spam" if "Spam" in classification else "not-spam"} fade-in">🌍 **Region/City:** {location if location != "Unknown" else region}</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="result-{"spam" if "Spam" in classification else "not-spam"} fade-in">⏰ **Time Zone:** {time_zone}</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="result-{"spam" if "Spam" in classification else "not-spam"} fade-in">📞 **Line Type:** {line_type}</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="result-{"spam" if "Spam" in classification else "not-spam"} fade-in">🌎 **Country:** {country}</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="result-{"spam" if "Spam" in classification else "not-spam"} fade-in">🔍 **Classification:** {classification}</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
    
    # SMS Spam Detector section in a box
    st.markdown('<div class="content-box fade-in">', unsafe_allow_html=True)
    st.markdown('<div class="subheader">📩 SMS Spam Detector</div>', unsafe_allow_html=True)
    with st.container():
        user_message = st.text_area("Enter SMS text:", key="sms_input")
    
    if st.button("Check SMS"):
        if not user_message.strip():
            st.warning("Please enter a message.")
        else:
            message_lower = user_message.lower()
            is_trusted = any(source in user_message for source in TRUSTED_SOURCES)
            spam_keyword_count = sum(1 for keyword in SPAM_KEYWORDS if keyword in message_lower)
            user_message_vectorized = vectorizer.transform([user_message])
            prediction = model.predict(user_message_vectorized)[0]
            if is_trusted and spam_keyword_count <= 1:
                result = "✅ Not Spam"
            elif spam_keyword_count >= 2 or prediction == 1:
                result = "🚨 Spam"
            else:
                result = "✅ Not Spam"
            st.markdown(f'<div class="result-{"spam" if "Spam" in result else "not-spam"} fade-in">🔍 **Classification:** {result}</div>', unsafe_allow_html=True)
            if spam_keyword_count > 0 and result == "🚨 Spam":
                st.markdown(f'<div class="note fade-in">⚠️ *Note:* Classified as spam due to {spam_keyword_count} suspicious keyword(s) detected.</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Report a Spam Number section in a box
    st.markdown('<div class="content-box fade-in">', unsafe_allow_html=True)
    st.markdown('<div class="subheader">📝 Report a Spam Number</div>', unsafe_allow_html=True)
    with st.container():
        feedback_phone = st.text_input("Enter a Spam Number to Report:", key="report_input")
    
    if st.button("Submit Report"):
        if not feedback_phone.strip():
            st.warning("Please enter a valid phone number to report.")
        else:
            formatted_feedback, _, _, _, is_valid = parse_phone_number(feedback_phone)
            if is_valid:
                st.session_state.spam_numbers.add(formatted_feedback)
                st.success(f"Phone number {formatted_feedback} has been reported as spam.")
                st.info("Note: Data will reset on app restart since the download section has been removed.")
            else:
                st.error("Invalid phone number. Please enter a valid number.")
    st.markdown('</div>', unsafe_allow_html=True)

# Feedback Page
elif page == "Feedback":
    # Submit Feedback section in a box
    st.markdown('<div class="content-box fade-in">', unsafe_allow_html=True)
    st.markdown('<div class="subheader">📝 Submit Feedback</div>', unsafe_allow_html=True)
    feedback_text = st.text_area("Please provide your feedback:", key="feedback_input")
    if st.button("Submit Feedback"):
        if feedback_text.strip():
            st.session_state.feedback.append(feedback_text)
            st.success("Thank you for your feedback!")
            st.info("Note: Data will reset on app restart since the download section has been removed.")
        else:
            st.warning("Please enter some feedback.")
    st.markdown('</div>', unsafe_allow_html=True)
