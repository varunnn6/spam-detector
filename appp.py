import numpy as np
import pandas as pd
import streamlit as st
import phonenumbers
import joblib
import requests
import os
import re
from phonenumbers import carrier, geocoder, timezone
from git import Repo
import git
import tempfile

# Streamlit App Title
st.title("Spam Shield 🛡️")

# Files for persistence
USERDATA_FILE = "userdata.txt"
FEEDBACK_FILE = "feedback.txt"
SPAM_FILE = "spam_numbers.txt"

# Initialize session state for user data and feedback
if 'userdata' not in st.session_state:
    st.session_state.userdata = {}
if 'feedback' not in st.session_state:
    st.session_state.feedback = []
if 'current_page' not in st.session_state:
    st.session_state.current_page = "Home"

# Initialize spam numbers
if 'spam_numbers' not in st.session_state:
    st.session_state.spam_numbers = set()
    if os.path.exists(SPAM_FILE):
        with open(SPAM_FILE, 'r') as f:
            st.session_state.spam_numbers.update(line.strip() for line in f if line.strip())

# Function to commit and push changes to GitHub
def commit_and_push(file_path, commit_message):
    try:
        # Use a temporary directory to clone the repo
        with tempfile.TemporaryDirectory() as temp_dir:
            # Clone the repository
            repo_url = st.secrets["github"]["repo_url"]
            token = st.secrets["github"]["token"]
            auth_url = repo_url.replace("https://", f"https://{token}@")
            repo = Repo.clone_from(auth_url, temp_dir)

            # Copy the updated file to the cloned repo
            import shutil
            dest_path = os.path.join(temp_dir, os.path.basename(file_path))
            shutil.copyfile(file_path, dest_path)

            # Stage the file
            repo.index.add([os.path.basename(file_path)])

            # Commit changes
            repo.index.commit(commit_message)

            # Push to GitHub
            origin = repo.remote(name='origin')
            origin.push()

        st.success(f"Successfully updated {file_path} in GitHub repository.")
    except Exception as e:
        st.error(f"Failed to push to GitHub: {str(e)}")

# Load user data from file at startup
def load_userdata():
    userdata = {}
    try:
        with open(USERDATA_FILE, 'r') as f:
            for line in f:
                if line.strip():
                    name, phone = line.strip().split(',')
                    userdata[phone] = name
    except FileNotFoundError:
        # Create the file if it doesn't exist
        with open(USERDATA_FILE, 'w') as f:
            pass
    return userdata

# Save user data to file and push to GitHub
def save_userdata(userdata):
    try:
        with open(USERDATA_FILE, 'w') as f:
            for phone, name in userdata.items():
                f.write(f"{name},{phone}\n")
        commit_and_push(USERDATA_FILE, "Update userdata.txt with new user data")
    except Exception as e:
        st.error(f"Failed to save userdata: {str(e)}")

# Load feedback from file at startup
def load_feedback():
    feedback = []
    try:
        with open(FEEDBACK_FILE, 'r') as f:
            feedback = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        # Create the file if it doesn't exist
        with open(FEEDBACK_FILE, 'w') as f:
            pass
    return feedback

# Save feedback to file and push to GitHub
def save_feedback(feedback):
    try:
        with open(FEEDBACK_FILE, 'w') as f:
            for entry in feedback:
                f.write(f"{entry}\n")
        commit_and_push(FEEDBACK_FILE, "Update feedback.txt with new feedback")
    except Exception as e:
        st.error(f"Failed to save feedback: {str(e)}")

# Load data into session state at startup
st.session_state.userdata = load_userdata()
st.session_state.feedback = load_feedback()

# Load Trained Machine Learning Model and Vectorizer
@st.cache_resource
def load_model_and_vectorizer():
    model = joblib.load('spam_classifier.pkl')
    vectorizer = joblib.load('tfidf_vectorizer.pkl')
    return model, vectorizer

model, vectorizer = load_model_and_vectorizer()

# Add Initial Spam Numbers (unchanged)
initial_spam_numbers = {
    "+917397947365", "+917550098431", "+919150228347", "+918292577122", "+919060883501",
    # ... (your existing spam numbers)
}
st.session_state.spam_numbers.update(initial_spam_numbers)
spam_numbers = st.session_state.spam_numbers

# Numlookup API Key (unchanged)
API_KEY = "num_live_gAgRGbG0st9WUyf8sR98KqlcKb5qB0SkrZFEpIm6"

# Function to Get Number Info using Numlookup API (unchanged)
@st.cache_data
def get_numlookup_info(phone_number):
    try:
        headers = {"Accept": "application/json"}
        url = f"https://api.numlookupapi.com/v1/validate/{phone_number}?apikey={API_KEY}"
        response = requests.get(url, headers=headers)
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

# Function to Parse and Validate Phone Number (unchanged)
def parse_phone_number(phone_number):
    try:
        parsed_number = phonenumbers.parse(phone_number, None)
        if phonenumbers.is_valid_number(parsed_number):
            formatted_number = phonenumbers.format_number(parsed_number, phonenumbers.PhoneNumberFormat.E164)
            service_provider = carrier.name_for_number(parsed_number, "en") or "Unknown"
            region = geocoder.description_for_number(parsed_number, "en") or "Unknown"
            time_zones = timezone.time_zones_for_number(parsed_number) or ["Unknown"]
            return formatted_number, service_provider, region, time_zones[0], True
        else:
            return None, None, None, None, False
    except phonenumbers.NumberParseException:
        return None, None, None, None, False

# Navigation Sidebar (unchanged)
with st.sidebar:
    st.header("Navigation")
    if st.button("Home", key="nav_home"):
        st.session_state.current_page = "Home"
    if st.button("Services", key="nav_services"):
        st.session_state.current_page = "Services"
    if st.button("Feedback", key="nav_feedback"):
        st.session_state.current_page = "Feedback"

# JavaScript for sidebar auto-close (unchanged)
st.markdown("""
<script>
    console.log("JavaScript loaded for sidebar auto-close");
    function closeSidebar() {
        const sidebar = document.querySelector('div[data-testid="stSidebar"]');
        if (sidebar) {
            console.log("Sidebar found, closing it");
            sidebar.style.transform = 'translateX(-100%)';
            sidebar.style.transition = 'transform 0.3s ease-in-out';
            const sidebarToggle = document.querySelector('button[data-testid="stSidebarToggle"]') ||
                                 document.querySelector('button[aria-label="Open sidebar"]') ||
                                 document.querySelector('button[aria-label="Close sidebar"]');
            if (sidebarToggle) {
                sidebarToggle.setAttribute('aria-expanded', 'false');
                sidebarToggle.setAttribute('aria-label', 'Open sidebar');
                console.log("Sidebar toggle updated to closed state");
            }
            const overlay = document.querySelector('div[data-testid="stSidebar"] + div[role="presentation"]');
            if (overlay) {
                overlay.style.display = 'none';
                console.log("Overlay hidden");
            }
        } else {
            console.log("Sidebar not found");
        }
    }
    document.addEventListener('click', (event) => {
        const target = event.target.closest('button[kind="secondary"][key^="nav_"]');
        if (target) {
            const buttonKey = target.getAttribute('key');
            console.log(`Button ${buttonKey} clicked`);
            setTimeout(closeSidebar, 150);
        }
    });
    document.addEventListener('DOMContentLoaded', () => {
        console.log("DOM fully loaded, setting up sidebar auto-close");
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
                # Immediately save to file and push to GitHub
                save_userdata(st.session_state.userdata)
                st.success(f"Thank you, {name}! Your number {formatted_phone} is now verified.")
            else:
                st.error("Invalid phone number. Please enter a valid number.")
        else:
            st.warning("Please enter both name and phone number.")

# Services Page
elif page == "Services":
    # Check Phone Number & SMS
    st.subheader("📲 Check if a Phone Number & SMS is Spam")
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
                number_without_country = formatted_number
                if formatted_number.startswith("+91"):
                    number_without_country = formatted_number[3:]
                classification = "✅ Not Spam"
                special_classification = None
                if number_without_country.startswith("14"):
                    st.session_state.spam_numbers.add(formatted_number)
                    classification = "🚨 Spam"
                elif number_without_country.startswith("88265"):
                    st.session_state.spam_numbers.add(formatted_number)
                    classification = "🚨 Spam"
                elif number_without_country.startswith("796512"):
                    st.session_state.spam_numbers.add(formatted_number)
                    classification = "🚨 Spam"
                elif number_without_country.startswith("16"):
                    special_classification = "Government or Regulators"
                    classification = "ℹ️ Not Spam"
                if formatted_number in spam_numbers:
                    classification = "🚨 Spam"
                if formatted_number.startswith("+140") or formatted_number.startswith("140"):
                    st.session_state.spam_numbers.add(formatted_number)
                    classification = "🚨 Spam"
                if local_provider == "Unknown" and api_provider == "Unknown":
                    classification = "🚨 Spam"
                if special_classification:
                    classification = f"{classification} ({special_classification})"
                st.write(f"**Phone Number:** {formatted_number}")
                st.write(f"**Associated Name:** {name}")
                displayed_provider = api_provider if api_provider != "Unknown" else local_provider
                st.write(f"📶 **Service Provider:** {displayed_provider}")
                if displayed_provider != "Unknown":
                    st.write("Note: The provider may have changed due to Mobile Number Portability.")
                st.write(f"🌍 **Region/City:** {location if location != 'Unknown' else region}")
                st.write(f"⏰ **Time Zone:** {time_zone}")
                st.write(f"📞 **Line Type:** {line_type}")
                st.write(f"🌎 **Country:** {country}")
                st.write(f"🔍 **Classification:** {classification}")

    # SMS Spam Detection
    st.subheader("📩 SMS Spam Detector")
    user_message = st.text_area("Enter SMS text:", key="sms_input")
    SPAM_KEYWORDS = [
        "won", "click", "link", "prize", "free", "claim", "urgent", "offer",
        "win", "congratulations", "money", "rupee", "reward", "lottery"
    ]
    TRUSTED_SOURCES = ["-SBI", "-HDFC", "-ICICI"]
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
            st.write(f"🔍 **Classification:** {result}")
            if spam_keyword_count > 0 and result == "🚨 Spam":
                st.write(f"⚠️ *Note:* Classified as spam due to {spam_keyword_count} suspicious keyword(s) detected.")

    # Report a Spam Number
    st.subheader("📝 Report a Spam Number")
    feedback_phone = st.text_input("Enter a Spam Number to Report:", key="report_input")
    if st.button("Submit Report"):
        if not feedback_phone.strip():
            st.warning("Please enter a valid phone number to report.")
        else:
            formatted_feedback, _, _, _, is_valid = parse_phone_number(feedback_phone)
            if is_valid:
                st.session_state.spam_numbers.add(formatted_feedback)
                try:
                    with open(SPAM_FILE, 'a') as f:
                        f.write(f"{formatted_feedback}\n")
                    commit_and_push(SPAM_FILE, f"Add spam number {formatted_feedback} to spam_numbers.txt")
                    st.success(f"Phone number {formatted_feedback} has been reported as spam and saved.")
                except Exception as e:
                    st.error(f"Failed to save spam number: {str(e)}")
            else:
                st.error("Invalid phone number. Please enter a valid number.")

# Feedback Page
elif page == "Feedback":
    st.subheader("📝 Submit Feedback")
    feedback_text = st.text_area("Please provide your feedback:", key="feedback_input")
    if st.button("Submit Feedback"):
        if feedback_text.strip():
            st.session_state.feedback.append(feedback_text)
            # Immediately save to file and push to GitHub
            save_feedback(st.session_state.feedback)
            st.success("Thank you for your feedback!")
        else:
            st.warning("Please enter some feedback.")
