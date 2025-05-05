import numpy as np
import pandas as pd
import streamlit as st
import phonenumbers
import joblib
import requests
import re
import psycopg2
from phonenumbers import carrier, geocoder, timezone

# Streamlit App Title
st.title("Spam Shield 🛡️")

# Initialize Supabase connection using Streamlit secrets
try:
    conn = psycopg2.connect(
        dbname=st.secrets["supabase"]["dbname"],
        user=st.secrets["supabase"]["user"],
        password=st.secrets["supabase"]["password"],
        host=st.secrets["supabase"]["host"],
        port=st.secrets["supabase"]["port"]
    )
except Exception as e:
    st.error(f"Failed to connect to Supabase: {str(e)}")
    st.stop()

# Initialize session state for user data and feedback
if 'userdata' not in st.session_state:
    st.session_state.userdata = {}
if 'feedback' not in st.session_state:
    st.session_state.feedback = []
if 'current_page' not in st.session_state:
    st.session_state.current_page = "Home"

# Load user data from Supabase at startup
def load_userdata():
    userdata = {}
    try:
        c = conn.cursor()
        c.execute("SELECT phone, name FROM users")
        for phone, name in c.fetchall():
            userdata[phone] = name
        c.close()
    except Exception as e:
        st.error(f"Failed to load userdata: {str(e)}")
    return userdata

# Save user data to Supabase
def save_userdata(userdata):
    try:
        c = conn.cursor()
        for phone, name in userdata.items():
            c.execute("INSERT INTO users (phone, name) VALUES (%s, %s) ON CONFLICT (phone) DO UPDATE SET name = %s", 
                      (phone, name, name))
        conn.commit()
        c.close()
    except Exception as e:
        st.error(f"Failed to save userdata: {str(e)}")

# Load feedback from Supabase at startup
def load_feedback():
    feedback = []
    try:
        c = conn.cursor()
        c.execute("SELECT entry FROM feedback")
        feedback = [row[0] for row in c.fetchall()]
        c.close()
    except Exception as e:
        st.error(f"Failed to load feedback: {str(e)}")
    return feedback

# Save feedback to Supabase
def save_feedback(feedback):
    try:
        c = conn.cursor()
        # Clear existing feedback
        c.execute("DELETE FROM feedback")
        # Insert new feedback
        for entry in feedback:
            c.execute("INSERT INTO feedback (entry) VALUES (%s)", (entry,))
        conn.commit()
        c.close()
    except Exception as e:
        st.error(f"Failed to save feedback: {str(e)}")

# Load spam numbers from Supabase at startup
def load_spam_numbers():
    spam_numbers = set()
    try:
        c = conn.cursor()
        c.execute("SELECT phone FROM spam_numbers")
        spam_numbers.update(row[0] for row in c.fetchall())
        c.close()
    except Exception as e:
        st.error(f"Failed to load spam numbers: {str(e)}")
    return spam_numbers

# Save a spam number to Supabase
def save_spam_number(phone):
    try:
        c = conn.cursor()
        c.execute("INSERT INTO spam_numbers (phone) VALUES (%s) ON CONFLICT (phone) DO NOTHING", (phone,))
        conn.commit()
        c.close()
    except Exception as e:
        st.error(f"Failed to save spam number: {str(e)}")

# Load data into session state at startup
st.session_state.userdata = load_userdata()
st.session_state.feedback = load_feedback()

# Initialize and Load Spam Numbers
if 'spam_numbers' not in st.session_state:
    st.session_state.spam_numbers = load_spam_numbers()

# Add Initial Spam Numbers
initial_spam_numbers = {
    "+917397947365", "+917550098431", "+919150228347", "+918292577122", "+919060883501",
    "+919163255112", "+916002454613", "+918292042103", "+917091184923", "+917633959085",
    "+919693115624", "+918337079723", "+919608381483", "+918838591478", "+917250968907",
    "+916200662711", "+917369089716", "+919088970355", "+917667394441", "+918807044585",
    "+917352384386", "+918340444510", "+919874460525", "+916289657859", "+916002485411",
    "+917909021203", "+916002454615", "+916383283037", "+917449664537", "+919741170745",
    "+918789709789", "+916205600945", "+916002545812", "+916206416578", "+916901837050",
    "+917044518143", "+918478977217", "+919123303151", "+919330172957", "+919268002125",
    "+919088524731", "+919135410272", "+917484019313", "+917479066971", "+919811637369",
    "+917718732612", "+919399126358", "+919090598938", "+919088353903", "+919093956065",
    "+919407302916", "+917505749890", "+919433656320", "+916290315431", "+918979703265",
    "+918551058079", "+916289742275", "+918877673872", "+918357988848", "+919354003963",
    "+918478984451", "+919653658918", "+918979035541", "+918697969426", "+919414039565",
    "+918617436699", "+918513937114", "+917044269512", "+917449958313", "+918670869956",
    "+919144317215", "+917984872576", "+919335133710", "+919330204120", "+918218991896",
    "+917699709165", "+917699709161", "+918849244894", "+916294274312", "+918514003884",
    "+919674129982", "+919144234677", "+918481858603", "+918514007134", "+917007976390",
    "+919931788848", "+918867887132", "+919546095125", "+918335916573", "+916202545132",
    "+918850565921", "+917033780636", "+919454304627", "+918409687843", "+916289693761",
    "+918902164005", "+918604050209", "+919330780675", "+916203163947", "+919093349748",
    "+919073753239", "+919834464651", "+919340112087", "+917360849405", "+919950071842",
    "+917903785368", "+919987166461", "+917408553440", "+916289932825", "+919603663119",
    "+916200151797", "+918343833796", "+918310211662", "+919093672697", "+919657837583",
    "+919088163475", "+918609168861", "+918513938098", "+918830681203", "+918208769851",
    "+916282501341", "+919798001380", "+917498383512", "+918609421406", "+916289779668",
    "+919992923927", "+919992443651", "+919330297159", "+918345958566", "+918927297419",
    "+917223804777", "+917837844941", "+919340852370", "+919340852365", "+919490584696",
    "+919128648444", "+918708959318", "+917464005751", "+919014293267", "+918709948480",
    "+919088385153", "+918269858278", "+919211344423", "+917759963120", "+919890392825",
    "+916395686313", "+919798853892", "+918002694366", "+918689831418", "+918696065048",
    "+918918557298", "+918515831303", "+918768812814", "+918168813388", "+916205802536",
    "+919328446819", "+919144530689", "+917076891749", "+919776030244", "+919330363299",
    "+916297694538", "+919159160470", "+916289887928"
}
# Add initial spam numbers to Supabase if not already present
for number in initial_spam_numbers:
    save_spam_number(number)
st.session_state.spam_numbers.update(initial_spam_numbers)

# Reference to spam_numbers for easier use
spam_numbers = st.session_state.spam_numbers

# Load Trained Machine Learning Model and Vectorizer
@st.cache_resource
def load_model_and_vectorizer():
    model = joblib.load('spam_classifier.pkl')
    vectorizer = joblib.load('tfidf_vectorizer.pkl')
    return model, vectorizer

model, vectorizer = load_model_and_vectorizer()

# Numlookup API Key
API_KEY = "num_live_gAgRGbG0st9WUyf8sR98KqlcKb5qB0SkrZFEpIm6"

# Function to Get Number Info using Numlookup API
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

# Function to Parse and Validate Phone Number
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
                save_userdata(st.session_state.userdata)
                st.success(f"Thank you, {name}! Your number {formatted_phone} is now verified.")
            else:
                st.error("Invalid phone number. Please enter a valid number.")
        else:
            st.warning("Please enter both name and phone number.")

# Services Page
elif page == "Services":
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

    st.subheader("📝 Report a Spam Number")
    feedback_phone = st.text_input("Enter a Spam Number to Report:", key="report_input")
    if st.button("Submit Report"):
        if not feedback_phone.strip():
            st.warning("Please enter a valid phone number to report.")
        else:
            formatted_feedback, _, _, _, is_valid = parse_phone_number(feedback_phone)
            if is_valid:
                st.session_state.spam_numbers.add(formatted_feedback)
                save_spam_number(formatted_feedback)
                st.success(f"Phone number {formatted_feedback} has been reported as spam and saved.")
            else:
                st.error("Invalid phone number. Please enter a valid number.")

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

# Close the database connection when the app shuts down
def on_shutdown():
    conn.close()

# Register the shutdown function
import atexit
atexit.register(on_shutdown)
