import numpy as np
import pandas as pd
import streamlit as st
import phonenumbers
import joblib
import requests
import os
import re
from phonenumbers import carrier, geocoder, timezone

# Streamlit App Title
st.title("Spam Shield 📩")

# Load Trained Machine Learning Model and Vectorizer
@st.cache_resource
def load_model_and_vectorizer():
    model = joblib.load('spam_classifier.pkl')
    vectorizer = joblib.load('tfidf_vectorizer.pkl')
    return model, vectorizer

model, vectorizer = load_model_and_vectorizer()

# Initialize and Load Spam Numbers from File
SPAM_FILE = "spam_numbers.txt"
if 'spam_numbers' not in st.session_state:
    st.session_state.spam_numbers = set()
    if os.path.exists(SPAM_FILE):
        with open(SPAM_FILE, 'r') as f:
            st.session_state.spam_numbers.update(line.strip() for line in f if line.strip())

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
st.session_state.spam_numbers.update(initial_spam_numbers)

# Reference to spam_numbers for easier use
spam_numbers = st.session_state.spam_numbers

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
        if displayed_provider != "Unknown":
                st.write("Note: The provider may have changed due to Mobile Number Portability.") 
        service_provider = data.get("carrier", "Unknown")
        location = data.get("location", "Unknown")  # Includes state/city if available
        line_type = data.get("line_type", "Unknown")
        # Clean country name by removing parenthetical text
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

# Load SMS Dataset
@st.cache_data
def load_data():
    df = pd.read_csv("Spam.csv", encoding='latin-1', quotechar='"', on_bad_lines='skip')
    df.columns = ['label', 'Text']
    df['label_enc'] = df['label'].map({'ham': 0, 'spam': 1})
    return df

df = load_data()

# Sidebar - Show Dataset
st.sidebar.header("Dataset Configuration")
if st.sidebar.checkbox("Show Dataset", value=False):
    st.write(df.head())

# Sidebar - Show Spam Numbers
st.sidebar.header("📊 Spam Number Database")
if st.sidebar.checkbox("Show Spam Numbers", value=False):
    st.write(pd.DataFrame(list(spam_numbers), columns=["Spam Phone Numbers"]))

# Main Section: Phone Number & SMS Spam Check
st.subheader("📲 Check if a Phone Number & SMS is Spam")
phone_number = st.text_input("Enter Phone Number (e.g., +919876543210):")

if st.button("Check Number"):
    if not phone_number.strip():
        st.warning("Please enter a phone number.")
    else:
        # Parse and validate phone number
        formatted_number, local_provider, region, time_zone, is_valid = parse_phone_number(phone_number)
        
        if not is_valid:
            st.error("Invalid phone number. Please enter a valid number.")
        else:
            # Get additional info using Numlookup API
            api_provider, location, line_type, country = get_numlookup_info(formatted_number)
            
            # Extract the number part after the country code for prefix checks
            number_without_country = formatted_number
            if formatted_number.startswith("+91"):
                number_without_country = formatted_number[3:]  # Remove "+91"
            
            # Determine classification
            classification = "✅ Not Spam"
            special_classification = None

            # Check for spam based on prefixes (after removing country code)
            if number_without_country.startswith("14"):
                classification = "🚨 Spam"
            elif number_without_country.startswith("88265"):
                classification = "🚨 Spam"
            elif number_without_country.startswith("796512"):
                classification = "🚨 Spam"
            elif number_without_country.startswith("16"):
                special_classification = "Government or Regulators"
                classification = "ℹ️ Not Spam"

            # Additional spam checks (on the full formatted number)
            if formatted_number in spam_numbers:
                classification = "🚨 Spam"
            if formatted_number.startswith("+140") or formatted_number.startswith("140"):
                classification = "🚨 Spam"
            if local_provider == "Unknown" and api_provider == "Unknown":
                classification = "🚨 Spam"  # Simplified logic without score

            # Final classification
            if special_classification:
                classification = f"{classification} ({special_classification})"

            # Display results
            st.write(f"**Phone Number:** {formatted_number}")
            # Show provider with a note about MNP
            displayed_provider = api_provider if api_provider != "Unknown" else local_provider
            st.write(f"📶 **Service Provider:** {displayed_provider}")
            
            st.write(f"🌍 **Region/City:** {location if location != 'Unknown' else region}")
            st.write(f"⏰ **Time Zone:** {time_zone}")
            st.write(f"📞 **Line Type:** {line_type}")
            st.write(f"🌎 **Country:** {country}")
            st.write(f"🔍 **Classification:** {classification}")

# SMS Spam Detection with Refined Rule-Based Filtering
st.subheader("📩 SMS Spam Detector")
user_message = st.text_area("Enter SMS text:")

# Define common spam keywords/phrases
SPAM_KEYWORDS = [
    "won", "click", "link", "prize", "free", "claim", "urgent", "offer",
    "win", "congratulations", "money", "rupee", "reward", "lottery"
]

# Define trusted sources (e.g., banks)
TRUSTED_SOURCES = ["-SBI", "-HDFC", "-ICICI"]

if st.button("Check SMS"):
    if not user_message.strip():
        st.warning("Please enter a message.")
    else:
        # Convert message to lowercase for keyword matching
        message_lower = user_message.lower()
        
        # Check if message is from a trusted source
        is_trusted = any(source in user_message for source in TRUSTED_SOURCES)
        
        # Count spam keywords
        spam_keyword_count = sum(1 for keyword in SPAM_KEYWORDS if keyword in message_lower)
        
        # Vectorize the input using the loaded TF-IDF vectorizer
        user_message_vectorized = vectorizer.transform([user_message])
        prediction = model.predict(user_message_vectorized)[0]
        
        # Refined classification logic
        if is_trusted and spam_keyword_count <= 1:
            result = "✅ Not Spam"  # Trust bank messages with 1 or fewer spam keywords
        elif spam_keyword_count >= 2 or prediction == 1:
            result = "🚨 Spam"  # Spam if 2+ keywords or model predicts spam
        else:
            result = "✅ Not Spam"
        
        # Display the result
        st.write(f"🔍 **Classification:** {result}")
        # Optional: Show details if rule-based check triggered
        if spam_keyword_count > 0 and result == "🚨 Spam":
            st.write(f"⚠️ *Note:* Classified as spam due to {spam_keyword_count} suspicious keyword(s) detected.")

# Report a Spam Number
st.subheader("📝 Report a Spam Number")
feedback_phone = st.text_input("Enter a Spam Number to Report:")

if st.button("Submit Report"):
    if not feedback_phone.strip():
        st.warning("Please enter a valid phone number to report.")
    else:
        formatted_feedback, _, _, _, is_valid = parse_phone_number(feedback_phone)
        if is_valid:
            st.session_state.spam_numbers.add(formatted_feedback)
            with open(SPAM_FILE, 'a') as f:
                f.write(f"{formatted_feedback}\n")
            st.success(f"Phone number {formatted_feedback} has been reported as spam and saved.")
        else:
            st.error("Invalid phone number. Please enter a valid number.")
