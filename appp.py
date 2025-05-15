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

# Custom CSS to prevent header wrapping
st.markdown("""
<style>
    .no-wrap-header h2 {
        white-space: nowrap !important;
        overflow: hidden;
        text-overflow: ellipsis;
    }
</style>
""", unsafe_allow_html=True)

# Initialize Firebase Firestore
try:
    if not firebase_admin._apps:
        cred_dict = json.loads(st.secrets["firebase"]["credentials"])
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
    db = firestore.client()
except Exception as e:
    db = None
    st.session_state.userdata = st.session_state.get('userdata', {})
    st.session_state.feedback = st.session_state.get('feedback', [])
    st.session_state.spam_numbers = st.session_state.get('spam_numbers', {})
    st.error(f"Failed to connect to Firestore: {str(e)}. Using local session state. Check your Firebase credentials in Streamlit Cloud secrets.")

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
        users_ref = db.collection('users').limit(100)
        docs = users_ref.stream()
        for doc in docs:
            data = doc.to_dict()
            phone = doc.id
            name = data.get('name', 'Unknown')
            userdata[phone] = name
    except Exception as e:
        st.error(f"Error loading user data: {str(e)}")
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
        batch.commit()
    except Exception as e:
        st.error(f"Error saving user data: {str(e)}")

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
        st.error(f"Error loading feedback: {str(e)}")
    return feedback

# Save feedback to Firestore asynchronously
def save_feedback(feedback):
    if not db:
        st.session_state.feedback = feedback
        return
    try:
        feedback_ref = db.collection('feedback')
        batch = db.batch()
        for doc in feedback_ref.stream():
            batch.delete(doc.reference)
        for i, entry in enumerate(feedback):
            doc_ref = feedback_ref.document(str(i))
            batch.set(doc_ref, {'entry': entry})
        batch.commit()
    except Exception as e:
        st.error(f"Error saving feedback: {str(e)}")

# Load spam numbers from Firestore (limit to 500 entries)
def load_spam_numbers():
    if not db:
        return st.session_state.spam_numbers
    spam_numbers = {}
    try:
        spam_ref = db.collection('spam_numbers').limit(500)
        docs = spam_ref.stream()
        for doc in docs:
            data = doc.to_dict()
            phone = doc.id
            report_count = data.get('report_count', 1)
            spam_numbers[phone] = report_count
    except Exception as e:
        st.error(f"Error loading spam numbers: {str(e)}")
    return spam_numbers

# Save a spam number to Firestore with transaction for atomicity
# Ensure Firestore security rules allow writes to 'spam_numbers', e.g.:
# match /spam_numbers/{document=**} {
#   allow read: if true;
#   allow write: if true; // Or 'if request.auth != null' with authentication
# }
def save_spam_number(phone):
    if not db:
        if phone in st.session_state.spam_numbers:
            st.session_state.spam_numbers[phone] += 1
        else:
            st.session_state.spam_numbers[phone] = 1
        return st.session_state.spam_numbers[phone]
    
    try:
        spam_ref = db.collection('spam_numbers').document(phone)
        @firestore.transactional
        def update_spam_count(transaction):
            snapshot = spam_ref.get(transaction=transaction)
            if snapshot.exists:
                current_count = snapshot.to_dict().get('report_count', 1)
                new_count = current_count + 1
                transaction.update(spam_ref, {'report_count': new_count})
            else:
                new_count = 1
                transaction.set(spam_ref, {'report_count': new_count})
            return new_count
        
        transaction = db.transaction()
        new_count = update_spam_count(transaction)
        # Verify the write succeeded
        doc = spam_ref.get()
        if doc.exists and doc.to_dict().get('report_count') == new_count:
            return new_count
        else:
            raise ValueError("Firestore write verification failed")
    except Exception as e:
        st.error(f"Failed to report number to Firestore: {str(e)}. Ensure Firestore security rules allow writes to 'spam_numbers' and credentials are valid.")
        return st.session_state.spam_numbers.get(phone, 0)  # Return current count without increment

# Load data into session state at startup
st.session_state.userdata = load_userdata()
st.session_state.feedback = load_feedback()

# Initialize and Load Spam Numbers
if 'spam_numbers' not in st.session_state:
    st.session_state.spam_numbers = load_spam_numbers()

# Define initial spam numbers with report counts (for testing)
initial_spam_numbers = {
    "+917397947365": 3, "+917550098431": 2, "+919150228347": 5, "+918292577122": 1, "+919060883501": 4,
    "+919163255112": 2, "+916002454613": 3, "+918292042103": 1, "+917091184923": 2, "+917633959085": 3,
    "+919693115624": 1, "+918337079723": 2, "+919608381483": 3, "+918838591478": 4, "+917250968907": 1,
    "+916200662711": 2, "+917369089716": 3, "+919088970355": 1, "+917667394441": 2, "+918807044585": 3,
    "+917352384386": 1, "+918340444510": 2, "+919874460525": 3, "+916289657859": 4, "+916002485411": 1,
    "+917909021203": 2, "+916002454615": 3, "+916383283037": 1, "+917449664537": 2, "+919741170745": 3,
    "+918789709789": 1, "+916205600945": 2, "+916002545812": 3, "+916206416578": 1, "+916901837050": 2,
    "+917044518143": 3, "+918478977217": 1, "+919123303151": 2, "+919330172957": 3, "+919268002125": 1,
    "+919088524731": 2, "+919135410272": 3, "+917484019313": 1, "+917479066971": 2, "+919811637369": 3,
    "+917718732612": 1, "+919399126358": 2, "+919090598938": 3, "+919088353903": 1, "+919093956065": 2,
    "+919407302916": 3, "+917505749890": 1, "+919433656320": 2, "+916290315431": 3, "+918979703265": 1,
    "+918551058079": 2, "+916289742275": 3, "+918877673872": 1, "+918357988848": 2, "+919354003963": 3,
    "+918478984451": 1, "+919653658918": 2, "+918979035541": 3, "+918697969426": 1, "+919414039565": 2,
    "+918617436699": 3, "+918513937114": 1, "+917044269512": 2, "+917449958313": 3, "+918670869956": 1,
    "+919144317215": 2, "+917984872576": 3, "+919335133710": 1, "+919330204120": 2, "+918218991896": 3,
    "+917699709165": 1, "+917699709161": 2, "+918849244894": 3, "+916294274312": 1, "+918514003884": 2,
    "+919674129982": 3, "+919144234677": 1, "+918481858603": 2, "+918514007134": 3, "+917007976390": 1,
    "+919931788848": 2, "+918867887132": 3, "+919546095125": 1, "+918335916573": 2, "+916202545132": 3,
    "+918850565921": 1, "+917033780636": 2, "+919454304627": 3, "+918409687843": 1, "+916289693761": 2,
    "+918902164005": 3, "+918604050209": 1, "+919330780675": 2, "+916203163947": 3, "+919093349748": 1,
    "+919073753239": 2, "+919834464651": 3, "+919340112087": 1, "+917360849405": 2, "+919950071842": 3,
    "+917903785368": 1, "+919987166461": 2, "+917408553440": 3, "+916289932825": 1, "+919603663119": 2,
    "+916200151797": 3, "+918343833796": 1, "+918310211662": 2, "+919093672697": 3, "+919657837583": 1,
    "+919088163475": 2, "+918609168861": 3, "+918513938098": 1, "+918830681203": 2, "+918208769851": 3,
    "+916282501341": 1, "+919798001380": 2, "+917498383512": 3, "+918609421406": 1, "+916289779668": 2,
    "+919992923927": 3, "+919992443651": 1, "+919330297159": 2, "+918345958566": 3, "+918927297419": 1,
    "+917223804777": 2, "+917837844941": 3, "+919340852370": 1, "+919340852365": 2, "+919490584696": 3,
    "+919128648444": 1, "+918708959318": 2, "+917464005751": 3, "+919014293267": 1, "+918709948480": 2,
    "+919088385153": 3, "+918269858278": 1, "+919211344423": 2, "+917759963120": 3, "+919890392825": 1,
    "+916395686313": 2, "+919798853892": 3, "+918002694366": 1, "+918689831418": 2, "+918696065048": 3,
    "+918918557298": 1, "+918515831303": 2, "+918768812814": 3, "+918168813388": 1, "+916205802536": 2,
    "+919328446819": 3, "+919144530689": 1, "+917076891749": 2, "+919776030244": 3, "+919330363299": 1,
    "+916297694538": 2, "+919159160470": 3, "+916289887928": 1
}

# Add initial spam numbers to session state (avoid writing to Firestore at startup)
for phone, count in initial_spam_numbers.items():
    if phone not in st.session_state.spam_numbers:
        st.session_state.spam_numbers[phone] = count

# Reference to spam_numbers for easier use
spam_numbers = st.session_state.spam_numbers

# Load Trained Machine Learning Model and Vectorizer
@st.cache_resource
def load_model_and_vectorizer():
    model = joblib.load('spam_classifier.pkl')
    vectorizer = joblib.load('tfidf_vectorizer.pkl')
    return model, vectorizer

# Load model immediately to avoid delay later
try:
    model, vectorizer = load_model_and_vectorizer()
except FileNotFoundError:
    st.error("Machine learning model or vectorizer files not found. Please ensure 'spam_classifier.pkl' and 'tfidf_vectorizer.pkl' are in the project directory.")
    model, vectorizer = None, None

# Numlookup API Key
API_KEY = "num_live_1DP975acU1UFuYM0qR8oKUWFMDZxq6cz7fx8Qs8P"

# Function to Get Number Info using Numlookup API
@st.cache_data
def get_numlookup_info(phone_number):
    try:
        headers = {"Accept": "application/json"}
        url = f"https://api.numlookupapi.com/v1/validate/{phone_number}?apikey={API_KEY}"
        response = requests.get(url, headers=headers, timeout=5)
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

# JavaScript to automatically close the sidebar after a button is clicked
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

# Home Page with Tabs
if page == "Home":
    tab1, tab2 = st.tabs(["Introduction", "Verify Your Number"])

    with tab1:
        st.header("Welcome to Spam Shield ⚔️")
        st.write("""
            **Spam Shield** is your go-to platform for protecting yourself from spam calls and messages. With a single web app, you can:

            ✅: Verify your phone number to build trust with others.  
            🔎: Check Phone Number information.  
            ❓: Check if phone number and message is spam.  
            🚩: Report spam numbers to help keep the community safe.  

            Join us in making communication safer and more reliable 🫂☺️!
        """)

    with tab2:
        st.subheader("Verify Your Number ✅")
        st.write("Add your name and phone number to be marked as a verified user, helping others trust your number!")
        name = st.text_input("Your Name", key="name_input")
        phone = st.text_input("Your Phone Number (e.g., +91XXXXXXXXXX)", key="phone_input_home")
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

# Services Page with Tabs
elif page == "Services":
    tab1, tab2, tab3 = st.tabs(["🔍 Search Number", "💬 Check Spam Message", "🚨 Report Spam"])

    with tab1:
        st.header("Search a Number 🔍")
        phone_input = st.text_input("Enter phone number to check (e.g., +91 1234567890):", key="phone_input_services")
        if st.button("Search", key="search_button"):
            if not phone_input.strip():
                st.warning("Please enter a phone number.")
            else:
                formatted_number, local_provider, region, time_zone, is_valid = parse_phone_number(phone_input)
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
                    report_count = 0
                    is_reported_spam = False
                    if formatted_number in spam_numbers:
                        classification = "🚨 Spam"
                        report_count = spam_numbers[formatted_number]
                        is_reported_spam = True
                    if number_without_country.startswith("14"):
                        st.session_state.spam_numbers[formatted_number] = spam_numbers.get(formatted_number, 0)
                        classification = "🚨 Spam"
                    elif number_without_country.startswith("88265"):
                        st.session_state.spam_numbers[formatted_number] = spam_numbers.get(formatted_number, 0)
                        classification = "🚨 Spam"
                    elif number_without_country.startswith("796512"):
                        st.session_state.spam_numbers[formatted_number] = spam_numbers.get(formatted_number, 0)
                        classification = "🚨 Spam"
                    elif number_without_country.startswith("16"):
                        special_classification = "Government or Regulators"
                        classification = "ℹ️ Not Spam"
                    if formatted_number.startswith("+140") or formatted_number.startswith("140"):
                        st.session_state.spam_numbers[formatted_number] = spam_numbers.get(formatted_number, 0)
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
                    if is_reported_spam:
                        st.write(f"⚠️ **This number has been reported {report_count} times.**")

    with tab2:
        st.markdown('<div class="no-wrap-header">', unsafe_allow_html=True)
        st.header("Check Spam Messages 💬")
        st.markdown('</div>', unsafe_allow_html=True)
        user_message = st.text_area("Enter message text to check:", key="sms_input", height=100)
        SPAM_KEYWORDS = [
            "won", "click", "link", "prize", "free", "claim", "urgent", "offer",
            "win", "congratulations", "money", "rupee", "reward", "lottery"
        ]
        TRUSTED_SOURCES = ["-SBI", "-HDFC", "-ICICI"]
        if st.button("Check Spam", key="check_spam_button"):
            if not user_message.strip():
                st.warning("Please enter a message.")
            else:
                message_lower = user_message.lower()
                is_trusted = any(source in user_message for source in TRUSTED_SOURCES)
                spam_keyword_count = sum(1 for keyword in SPAM_KEYWORDS if keyword in message_lower)
                if model and vectorizer:
                    user_message_vectorized = vectorizer.transform([user_message])
                    prediction = model.predict(user_message_vectorized)[0]
                    if is_trusted and spam_keyword_count <= 1:
                        result = "✅ Not Spam"
                    elif spam_keyword_count >= 2 or prediction == 1:
                        result = "🚨 Spam"
                    else:
                        result = "✅ Not Spam"
                    if "🚨 Spam" in result:
                        st.error("This message is a spam.")
                    if "✅" in result:
                        st.success("This message is not a spam.")
                    st.write(f"🔍 **Classification:** {result}")
                    if spam_keyword_count > 0 and result == "🚨 Spam":
                        st.warning(f"⚠️ *Note:* Classified as spam due to {spam_keyword_count} suspicious keyword(s) detected.")
                else:
                    st.error("Machine learning model not loaded. Cannot classify message.")

    with tab3:
        st.markdown('<div class="no-wrap-header">', unsafe_allow_html=True)
        st.header("Report a Spam Number ⚠️")
        st.markdown('</div>', unsafe_allow_html=True)
        spam_input = st.text_input("Enter phone number to report as spam:", key="report_input")
        if st.button("Report Spam", key="report_spam_button"):
            if not spam_input.strip():
                st.warning("Please enter a valid phone number to report.")
            else:
                formatted_feedback, _, _, _, is_valid = parse_phone_number(spam_input)
                if is_valid:
                    previous_count = st.session_state.spam_numbers.get(formatted_feedback, 0)
                    updated_count = save_spam_number(formatted_feedback)
                    if updated_count > previous_count:
                        st.session_state.spam_numbers[formatted_feedback] = updated_count
                        st.success("🚨 The number is successfully reported")
                        st.info(f"It has been reported {updated_count} times by the people.")
                    else:
                        st.error("Failed to report number. Check Firestore connection and security rules.")
                else:
                    st.error("Invalid phone number. Please enter a valid number.")

# Feedback Page
elif page == "Feedback":
    st.subheader("📝 Submit Feedback")
    feedback_text = st.text_area("Please provide your feedback 😇:", key="feedback_input")
    if st.button("Submit Feedback"):
        if feedback_text.strip():
            st.session_state.feedback.append(feedback_text)
            save_feedback(st.session_state.feedback)
            st.success("Thank you for your feedback!")
        else:
            st.warning("Please enter some feedback.")
