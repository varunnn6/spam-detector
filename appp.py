# spamshield_twilio.py
# Full Spam Shield with Twilio OTP Integration
#
# Twilio Features:
# - $15.50 free trial credit (500+ SMS)
# - Most reliable SMS delivery
# - Works worldwide
# - Professional service
#
# Requirements:
# pip install streamlit phonenumbers firebase-admin joblib requests pandas twilio

import streamlit as st
import phonenumbers
from phonenumbers import carrier, geocoder, timezone
import joblib
import requests
import re
import json
import random
import time
from datetime import datetime, timedelta
import pandas as pd
import traceback

# Twilio
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

# Firebase
import firebase_admin
from firebase_admin import credentials, firestore

# ----------------------------- Twilio Configuration -----------------------------------
# Your Twilio credentials
TWILIO_ACCOUNT_SID = "AC9058d9d51aa2ac706127161899966c98"
TWILIO_AUTH_TOKEN = "8744fbe276b9dd8a436ddfdb16b1be51"
TWILIO_PHONE_NUMBER = "+12627669058"  # Get this from Twilio Console (your Twilio number)

# Note: You need to get a Twilio phone number from the console
# Go to: https://console.twilio.com/us1/develop/phone-numbers/manage/incoming
# Click "Buy a number" (free with trial) or use your existing number

# Other API keys
NUMLOOKUP_API_KEY = "num_live_1DP975acU1UFuYM0qR8oKUWFMDZxq6cz7fx8Qs8P"

# OTP settings
OTP_LENGTH = 6
OTP_EXPIRY_SECONDS = 120
OTP_RESEND_COOLDOWN = 60

# Model files
MODEL_FILE = "spam_classifier.pkl"
VECTORIZER_FILE = "tfidf_vectorizer.pkl"
FIREBASE_CRED_FILENAME = "serviceAccountKey.json"

# ---------------------------------------------------------------------------------------

st.set_page_config(page_title="Spam Shield 🛡️", layout="wide")

# ----------------------------- Initialize Firebase ------------------------------------
try:
    if not firebase_admin._apps:
        cred = credentials.Certificate(FIREBASE_CRED_FILENAME)
        firebase_admin.initialize_app(cred)
    db = firestore.client()
    firebase_available = True
except Exception as e:
    db = None
    firebase_available = False
    st.warning("⚠️ Warning: Firebase not available. Using local storage only.")
    print("Firebase init error:", e)

# ----------------------------- Session State ------------------------------------------
if 'userdata' not in st.session_state:
    st.session_state.userdata = {}
if 'feedback' not in st.session_state:
    st.session_state.feedback = []
if 'spam_numbers' not in st.session_state:
    st.session_state.spam_numbers = {}
if 'parsed_numbers' not in st.session_state:
    st.session_state.parsed_numbers = {}
if 'current_page' not in st.session_state:
    st.session_state.current_page = "Home"

# OTP session
if 'otp_code' not in st.session_state:
    st.session_state.otp_code = None
if 'otp_sent_time' not in st.session_state:
    st.session_state.otp_sent_time = None
if 'otp_phone' not in st.session_state:
    st.session_state.otp_phone = None
if 'otp_name' not in st.session_state:
    st.session_state.otp_name = None
if 'verified_number' not in st.session_state:
    st.session_state.verified_number = None
if 'resend_allowed_time' not in st.session_state:
    st.session_state.resend_allowed_time = None

# ----------------------------- Twilio Functions ---------------------------------------
def initialize_twilio_client():
    """Initialize Twilio client with credentials"""
    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        return client
    except Exception as e:
        print(f"❌ Failed to initialize Twilio client: {e}")
        return None

def get_twilio_phone_number():
    """
    Get Twilio phone number from account
    If TWILIO_PHONE_NUMBER is not set, try to fetch from account
    """
    if TWILIO_PHONE_NUMBER and TWILIO_PHONE_NUMBER != "+1234567890":
        return TWILIO_PHONE_NUMBER
    
    try:
        client = initialize_twilio_client()
        if client:
            # Try to get first incoming phone number
            numbers = client.incoming_phone_numbers.list(limit=1)
            if numbers:
                phone = numbers[0].phone_number
                print(f"✅ Using Twilio number: {phone}")
                return phone
    except Exception as e:
        print(f"⚠️ Could not fetch Twilio number: {e}")
    
    return None

def send_otp_twilio(phone_number, otp, recipient_name="User"):
    """
    Send OTP via Twilio SMS
    
    Args:
        phone_number: Phone number in E.164 format (e.g., +919876543210)
        otp: OTP code to send
        recipient_name: Name of recipient for personalized message
    
    Returns:
        True if successful, False otherwise
    """
    try:
        # Initialize Twilio client
        client = initialize_twilio_client()
        if not client:
            print("❌ Failed to initialize Twilio client")
            return False
        
        # Get Twilio phone number
        from_number = get_twilio_phone_number()
        if not from_number:
            print("❌ No Twilio phone number configured")
            print("💡 Get a number from: https://console.twilio.com/us1/develop/phone-numbers/manage/incoming")
            return False
        
        # Ensure phone number is in E.164 format
        if not phone_number.startswith('+'):
            phone_number = '+' + phone_number
        
        print(f"📱 Sending OTP via Twilio")
        print(f"   From: {from_number}")
        print(f"   To: {phone_number}")
        print(f"   OTP: {otp}")
        
        # Create message body
        message_body = f"""Hello {recipient_name},

Your Spam Shield verification code is: {otp}

This code will expire in 2 minutes.

Do not share this code with anyone.

- Spam Shield Team"""
        
        # Send SMS
        message = client.messages.create(
            body=message_body,
            from_=from_number,
            to=phone_number
        )
        
        print(f"✅ Twilio SMS sent successfully!")
        print(f"   Message SID: {message.sid}")
        print(f"   Status: {message.status}")
        
        return True
        
    except TwilioRestException as e:
        print(f"❌ Twilio API Error: {e.msg}")
        print(f"   Error Code: {e.code}")
        print(f"   Status: {e.status}")
        
        # Provide helpful error messages
        if e.code == 20003:
            print("💡 Authentication failed - check your Account SID and Auth Token")
        elif e.code == 21211:
            print("💡 Invalid 'To' phone number - check the phone number format")
        elif e.code == 21606:
            print("💡 The 'From' number is not verified - verify your Twilio number")
        elif e.code == 21408:
            print("💡 Permission denied - check if 'To' number can receive SMS")
        elif e.code == 20429:
            print("💡 Too many requests - rate limit exceeded")
        
        return False
        
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        traceback.print_exc()
        return False

def verify_twilio_setup():
    """
    Verify Twilio setup and return status
    Returns: (is_valid, message)
    """
    try:
        client = initialize_twilio_client()
        if not client:
            return False, "Failed to initialize Twilio client"
        
        # Check if we can access account
        account = client.api.accounts(TWILIO_ACCOUNT_SID).fetch()
        
        # Check for phone number
        from_number = get_twilio_phone_number()
        if not from_number:
            return False, "No Twilio phone number found. Please purchase one from Twilio console."
        
        return True, f"Twilio setup valid! Using number: {from_number}"
        
    except TwilioRestException as e:
        return False, f"Twilio error: {e.msg}"
    except Exception as e:
        return False, f"Setup error: {str(e)}"

def check_twilio_balance():
    """Check Twilio account balance"""
    try:
        client = initialize_twilio_client()
        if not client:
            return None
        
        account = client.api.accounts(TWILIO_ACCOUNT_SID).fetch()
        balance = account.balance
        currency = account.balance_currency
        
        print(f"💰 Twilio Balance: {balance} {currency}")
        return float(balance)
        
    except Exception as e:
        print(f"⚠️ Could not fetch balance: {e}")
        return None

# ----------------------------- Utilities ----------------------------------------------
@st.cache_data
def get_numlookup_info(phone_number):
    try:
        headers = {"Accept": "application/json"}
        url = f"https://api.numlookupapi.com/v1/validate/{phone_number}?apikey={NUMLOOKUP_API_KEY}"
        response = requests.get(url, headers=headers, timeout=8)
        response.raise_for_status()
        data = response.json()
        service_provider = data.get("carrier", "Unknown")
        location = data.get("location", "Unknown")
        line_type = data.get("line_type", "Unknown")
        country = data.get("country_name", "Unknown")
        country = re.sub(r'\s*\([^)]+\)', '', country).strip()
        return service_provider, location, line_type, country
    except Exception as e:
        return "Unknown", "Unknown", "Unknown", "Unknown"

def parse_phone_number(phone_number):
    if not phone_number:
        return (None, None, None, None, False)
    if phone_number in st.session_state.parsed_numbers:
        return st.session_state.parsed_numbers[phone_number]
    try:
        candidate = phone_number.strip()
        if candidate.startswith("+"):
            parsed = phonenumbers.parse(candidate, None)
        else:
            try:
                parsed = phonenumbers.parse(candidate, None)
            except phonenumbers.NumberParseException:
                parsed = phonenumbers.parse(candidate, "IN")
        if phonenumbers.is_valid_number(parsed):
            formatted_number = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
            service_provider = carrier.name_for_number(parsed, "en") or "Unknown"
            region = geocoder.description_for_number(parsed, "en") or "Unknown"
            tz_list = timezone.time_zones_for_number(parsed) or ["Unknown"]
            result = (formatted_number, service_provider, region, tz_list[0], True)
        else:
            result = (None, None, None, None, False)
    except Exception:
        result = (None, None, None, None, False)
    st.session_state.parsed_numbers[phone_number] = result
    return result

# ----------------------------- Firestore helpers --------------------------------------
def load_userdata():
    if not db:
        return st.session_state.userdata
    userdata = {}
    try:
        docs = db.collection('users').limit(100).stream()
        for doc in docs:
            userdata[doc.id] = doc.to_dict().get('name', 'Unknown')
    except Exception as e:
        print("load_userdata error:", e)
    return userdata

def save_userdata(userdata):
    if not db:
        st.session_state.userdata.update(userdata)
        return
    try:
        users_ref = db.collection('users')
        batch = db.batch()
        for phone, name in userdata.items():
            doc_ref = users_ref.document(phone)
            batch.set(doc_ref, {'name': name})
        batch.commit()
    except Exception as e:
        st.error(f"Error saving user data: {e}")

def load_feedback():
    if not db:
        return st.session_state.feedback
    feedback = []
    try:
        docs = db.collection('feedback').limit(50).stream()
        for doc in docs:
            feedback.append(doc.to_dict().get('entry', ''))
    except Exception as e:
        print("load_feedback error:", e)
    return feedback

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
            batch.set(feedback_ref.document(str(i)), {'entry': entry})
        batch.commit()
    except Exception as e:
        st.error(f"Error saving feedback: {e}")

def load_spam_numbers():
    if not db:
        return st.session_state.spam_numbers
    spam_numbers = {}
    try:
        docs = db.collection('spam_numbers').limit(500).stream()
        for doc in docs:
            spam_numbers[doc.id] = doc.to_dict().get('report_count', 1)
    except Exception as e:
        print("load_spam_numbers error:", e)
    return spam_numbers

def save_spam_number(phone):
    if not db:
        st.session_state.spam_numbers[phone] = st.session_state.spam_numbers.get(phone, 0) + 1
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
        return new_count
    except Exception as e:
        print("save_spam_number error:", e)
        return st.session_state.spam_numbers.get(phone, 0)

# ----------------------------- Load data ----------------------------------------------
st.session_state.userdata = load_userdata()
st.session_state.feedback = load_feedback()
if not st.session_state.spam_numbers:
    initial_spam_numbers = {
        "+917397947365": 3, "+917550098431": 2, "+919150228347": 5,
        "+918292577122": 1, "+919060883501": 4, "+919163255112": 2,
    }
    st.session_state.spam_numbers = load_spam_numbers()
    for p, c in initial_spam_numbers.items():
        if p not in st.session_state.spam_numbers:
            st.session_state.spam_numbers[p] = c

spam_numbers = st.session_state.spam_numbers

# ----------------------------- Load ML model ------------------------------------------
@st.cache_resource
def load_model_and_vectorizer():
    try:
        model = joblib.load(MODEL_FILE)
        vectorizer = joblib.load(VECTORIZER_FILE)
        return model, vectorizer
    except Exception as e:
        print("Model loading error:", e)
        return None, None

model, vectorizer = load_model_and_vectorizer()

# ----------------------------- OTP helpers --------------------------------------------
def _generate_otp():
    return ''.join(str(random.randint(0,9)) for _ in range(OTP_LENGTH))

def _can_resend():
    t = st.session_state.get('resend_allowed_time', None)
    if t is None:
        return True
    return time.time() >= t

def _resend_seconds_left():
    t = st.session_state.get('resend_allowed_time', None)
    if t is None:
        return 0
    left = int(t - time.time())
    return max(left, 0)

def _otp_seconds_left():
    sent_time = st.session_state.get('otp_sent_time', None)
    if not sent_time:
        return 0
    left = OTP_EXPIRY_SECONDS - int(time.time() - sent_time)
    return max(left, 0)

# ----------------------------- Navigation ---------------------------------------------
with st.sidebar:
    st.header("Navigation")
    if st.button("Home", key="nav_home"):
        st.session_state.current_page = "Home"
    if st.button("Services", key="nav_services"):
        st.session_state.current_page = "Services"
    if st.button("Feedback", key="nav_feedback"):
        st.session_state.current_page = "Feedback"
    st.markdown("---")
    st.write("**Status:**", "✅ Verified" if st.session_state.get('verified_number') else "❌ Not Verified")
    
    # Show Twilio status
    if st.button("🔍 Check Twilio Status"):
        with st.spinner("Checking Twilio..."):
            is_valid, message = verify_twilio_setup()
            if is_valid:
                st.success(message)
                balance = check_twilio_balance()
                if balance is not None:
                    st.info(f"💰 Balance: ${balance:.2f}")
            else:
                st.error(message)

# ----------------------------- Verification Gate --------------------------------------
st.title("Spam Shield 🛡️")
st.markdown("📱 **Powered by Twilio** - Most reliable OTP delivery!")

if st.session_state.get('verified_number'):
    verified = True
else:
    verified = False

if not verified:
    st.subheader("Verify Your Number ✅")
    st.info("📲 We'll send an OTP via Twilio SMS - Works worldwide!")
    
    # Check Twilio setup first
    is_setup_valid, setup_message = verify_twilio_setup()
    if not is_setup_valid:
        st.error(f"⚠️ Twilio Setup Issue: {setup_message}")
        with st.expander("🔧 How to fix"):
            st.markdown("""
            **Steps to complete Twilio setup:**
            
            1. **Get a Twilio Phone Number:**
               - Go to: https://console.twilio.com/us1/develop/phone-numbers/manage/incoming
               - Click "Buy a number" (free with trial)
               - Select a number with SMS capability
               - Copy the number (format: +1234567890)
            
            2. **Update the code:**
               ```python
               TWILIO_PHONE_NUMBER = "+1234567890"  # Your number here
               ```
            
            3. **Your credentials are already set:**
               - Account SID: AC9058d9d51aa2ac706127161899966c98 ✅
               - Auth Token: Configured ✅
            """)
    
    name = st.text_input("Your Name", key="verify_name")
    phone_input = st.text_input("Your Phone Number (with country code, e.g., +919876543210)", 
                                 key="verify_phone",
                                 placeholder="+919876543210")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Send OTP"):
            if not name or not phone_input:
                st.warning("Please enter both name and phone number.")
            else:
                formatted_phone, _, _, _, is_valid = parse_phone_number(phone_input)
                if not is_valid:
                    st.error("Invalid phone number. Please include country code (e.g., +91 for India).")
                else:
                    otp = _generate_otp()
                    with st.spinner("📱 Sending OTP via Twilio..."):
                        sent = send_otp_twilio(formatted_phone, otp, name)
                    
                    if sent:
                        st.session_state.otp_code = otp
                        st.session_state.otp_sent_time = time.time()
                        st.session_state.otp_phone = formatted_phone
                        st.session_state.otp_name = name
                        st.session_state.resend_allowed_time = time.time() + OTP_RESEND_COOLDOWN
                        st.success(f"✅ OTP sent to {formatted_phone} via Twilio!")
                        st.info("💡 Check your phone for SMS. It should arrive within seconds.")
                    else:
                        st.error("❌ Failed to send OTP via Twilio")
                        st.write("**Possible reasons:**")
                        st.write("1. **No Twilio Phone Number**: You need to get a phone number from Twilio console")
                        st.write("2. **Invalid recipient number**: Check phone number format (+country code)")
                        st.write("3. **Trial limitations**: Some numbers require verification in trial mode")
                        st.write("4. **No balance**: Check if you have trial credits")
                        
                        with st.expander("📖 Check console logs for details"):
                            st.info("Look at the terminal/console where Streamlit is running for detailed error messages")
    
    with col2:
        if not _can_resend():
            st.write(f"⏳ Resend available in {_resend_seconds_left()}s")
        else:
            if st.button("Resend OTP"):
                if not st.session_state.get('otp_phone'):
                    st.warning("No OTP request found")
                else:
                    formatted_phone = st.session_state.otp_phone
                    name_stored = st.session_state.otp_name
                    otp2 = _generate_otp()
                    with st.spinner("Resending OTP..."):
                        sent2 = send_otp_twilio(formatted_phone, otp2, name_stored)
                    if sent2:
                        st.session_state.otp_code = otp2
                        st.session_state.otp_sent_time = time.time()
                        st.session_state.resend_allowed_time = time.time() + OTP_RESEND_COOLDOWN
                        st.info("✅ OTP resent successfully")
                    else:
                        st.error("❌ Failed to resend OTP")

    if st.session_state.get('otp_code'):
        st.markdown("---")
        st.write("📱 Enter the 6-digit OTP sent to your phone")
        otp_entered = st.text_input("OTP", key="otp_input_field", type="password", max_chars=6)
        
        if st.button("Verify OTP"):
            if st.session_state.get('otp_sent_time') is None:
                st.error("No OTP has been sent")
            else:
                elapsed = time.time() - st.session_state.otp_sent_time
                if elapsed > OTP_EXPIRY_SECONDS:
                    st.error("⏰ OTP expired - please resend")
                    st.session_state.otp_code = None
                    st.session_state.otp_sent_time = None
                    st.session_state.otp_phone = None
                    st.session_state.otp_name = None
                    st.session_state.resend_allowed_time = None
                else:
                    if otp_entered == st.session_state.otp_code:
                        formatted_phone = st.session_state.otp_phone
                        name_to_save = st.session_state.otp_name
                        
                        try:
                            if db:
                                db.collection('users').document(formatted_phone).set({
                                    'name': name_to_save,
                                    'verified': True,
                                    'verified_at': firestore.SERVER_TIMESTAMP,
                                    'verification_method': 'twilio'
                                })
                            st.session_state.userdata[formatted_phone] = name_to_save
                            save_userdata({formatted_phone: name_to_save})
                            st.success(f"✅ Verified! Welcome, {name_to_save}!")
                            st.balloons()
                        except Exception as e:
                            st.error(f"Verified but save failed: {e}")
                            st.session_state.userdata[formatted_phone] = name_to_save
                        
                        st.session_state.verified_number = formatted_phone
                        st.session_state.otp_code = None
                        st.session_state.otp_sent_time = None
                        st.session_state.otp_phone = None
                        st.session_state.otp_name = None
                        st.session_state.resend_allowed_time = None
                        st.rerun()
                    else:
                        st.error("❌ Incorrect OTP. Please try again.")

        seconds_left = _otp_seconds_left()
        if seconds_left > 0:
            st.info(f"⏰ OTP expires in {seconds_left} seconds")
        else:
            st.warning("⏰ OTP has expired. Please resend.")

    st.stop()

# ----------------------------- Main App -----------------------------------------------
verified_phone = st.session_state.verified_number

if verified_phone:
    st.success(f"✅ Access granted for {verified_phone}")
else:
    st.error("Not verified")
    st.stop()

page = st.session_state.current_page

# Home page
if page == "Home":
    tab1, tab2 = st.tabs(["Introduction", "Your Info"])
    with tab1:
        st.header("Welcome to Spam Shield ⚔️")
        st.write("""
            **Spam Shield** protects against spam calls and messages.
            This version uses Twilio for the most reliable OTP delivery worldwide.
            
            ✅ Professional SMS delivery
            ✅ Works in 200+ countries
            ✅ Highest delivery rates
        """)
    with tab2:
        st.header("Your Verified Info")
        name_for_display = st.session_state.userdata.get(verified_phone, "Unknown")
        st.write(f"**Name:** {name_for_display}")
        st.write(f"**Verified Phone:** {verified_phone}")
        st.write(f"**Verification Method:** Twilio SMS")

# Services page
elif page == "Services":
    tab1, tab2, tab3 = st.tabs(["🔍 Search Number", "💬 Check Spam Message", "🚨 Report Spam"])

    with tab1:
        st.header("Search a Number 🔍")
        phone_input = st.text_input("Enter phone number:", key="services_phone_input")
        if st.button("Search", key="search_button"):
            if not phone_input.strip():
                st.warning("Please enter a phone number")
            else:
                formatted_number, local_provider, region, time_zone, is_valid_n = parse_phone_number(phone_input)
                if not is_valid_n:
                    st.error("Invalid phone number")
                else:
                    api_provider, location, line_type, country = get_numlookup_info(formatted_number)
                    name = st.session_state.userdata.get(formatted_number, "Unknown")
                    classification = "✅ Not Spam"
                    report_count = spam_numbers.get(formatted_number, 0)
                    
                    if formatted_number in spam_numbers:
                        classification = "🚨 Spam"
                    
                    st.write(f"**Phone Number:** {formatted_number}")
                    st.write(f"**Name:** {name}")
                    st.write(f"📶 **Provider:** {api_provider if api_provider != 'Unknown' else local_provider}")
                    st.write(f"🌍 **Region:** {location if location != 'Unknown' else region}")
                    st.write(f"⏰ **Timezone:** {time_zone}")
                    st.write(f"📞 **Line Type:** {line_type}")
                    st.write(f"🌎 **Country:** {country}")
                    st.write(f"🔍 **Classification:** {classification}")
                    if report_count > 0:
                        st.write(f"⚠️ **Reported {report_count} times**")

    with tab2:
        st.header("Check Spam Messages 💬")
        user_message = st.text_area("Enter message:", key="sms_input", height=140)
        SPAM_KEYWORDS = ["won", "click", "link", "prize", "free", "claim", "urgent"]
        TRUSTED_SOURCES = ["-SBI", "-HDFC", "-ICICI"]

        if st.button("Check Spam", key="check_spam_button"):
            if not user_message.strip():
                st.warning("Please enter a message")
            else:
                message_lower = user_message.lower()
                is_trusted = any(source in user_message for source in TRUSTED_SOURCES)
                spam_keyword_count = sum(1 for kw in SPAM_KEYWORDS if kw in message_lower)
                
                if model and vectorizer:
                    try:
                        user_message_vectorized = vectorizer.transform([user_message])
                        prediction = model.predict(user_message_vectorized)[0]
                    except:
                        prediction = 0
                    
                    if is_trusted and spam_keyword_count <= 1:
                        result = "✅ Not Spam"
                    elif spam_keyword_count >= 2 or prediction == 1:
                        result = "🚨 Spam"
                    else:
                        result = "✅ Not Spam"
                else:
                    if spam_keyword_count >= 2:
                        result = "🚨 Spam"
                    else:
                        result = "✅ Not Spam"

                if "🚨 Spam" in result:
                    st.error("This message is spam")
                else:
                    st.success("This message is not spam")
                st.write(f"🔍 **Classification:** {result}")
                if spam_keyword_count > 0 and result == "🚨 Spam":
                    st.warning(f"⚠️ Classified as spam due to {spam_keyword_count} suspicious keyword(s)")

    with tab3:
        st.header("Report a Spam Number ⚠️")
        spam_input = st.text_input("Enter phone number to report as spam:", key="report_input")
        if st.button("Report Spam", key="report_spam_button"):
            if not spam_input.strip():
                st.warning("Please enter a valid phone number to report")
            else:
                formatted_feedback, _, _, _, is_valid_fb = parse_phone_number(spam_input)
                if is_valid_fb:
                    previous_count = st.session_state.spam_numbers.get(formatted_feedback, 0)
                    updated_count = save_spam_number(formatted_feedback)
                    st.session_state.spam_numbers[formatted_feedback] = updated_count
                    if updated_count > previous_count:
                        st.success("🚨 The number has been successfully reported!")
                        st.info(f"It has been reported {updated_count} times by users.")
                    else:
                        st.error("Failed to report number. Check Firestore connection.")
                else:
                    st.error("Invalid phone number. Please enter a valid number.")

# Feedback page
elif page == "Feedback":
    st.header("📝 Submit Feedback")
    feedback_text = st.text_area("Please provide your feedback 😇:", key="feedback_input")
    if st.button("Submit Feedback"):
        if feedback_text.strip():
            st.session_state.feedback.append(feedback_text.strip())
            save_feedback(st.session_state.feedback)
            st.success("Thank you for your feedback! 🙏")
        else:
            st.warning("Please enter some feedback.")

# Fallback
else:
    st.write("Unknown page. Use sidebar to navigate.")

# ----------------------------- End of app ---------------------------------------------
