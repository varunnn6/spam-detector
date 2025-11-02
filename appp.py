# spam_new.py
# Final Spam Shield with Twilio OTP Integration (SMS only)
# Fast2SMS removed – Twilio used exclusively

import streamlit as st
import phonenumbers
from phonenumbers import carrier, geocoder, timezone
import joblib
import requests
import re
import random
import time
from datetime import datetime
import pandas as pd
import traceback
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
import firebase_admin
from firebase_admin import credentials, firestore

# ----------------------------- Twilio Configuration -----------------------------------
TWILIO_ACCOUNT_SID = "AC9058d9d51aa2ac706127161899966c98"
TWILIO_AUTH_TOKEN = "8744fbe276b9dd8a436ddfdb16b1be51"
TWILIO_PHONE_NUMBER = "+12627669058"

NUMLOOKUP_API_KEY = "num_live_1DP975acU1UFuYM0qR8oKUWFMDZxq6cz7fx8Qs8P"
MODEL_FILE = "spam_classifier.pkl"
VECTORIZER_FILE = "tfidf_vectorizer.pkl"
FIREBASE_CRED_FILENAME = "serviceAccountKey.json"

OTP_LENGTH = 6
OTP_EXPIRY_SECONDS = 120
OTP_RESEND_COOLDOWN = 60

# ---------------------------------------------------------------------------------------
st.set_page_config(page_title="Spam Shield 🛡️", layout="wide")

# ----------------------------- Firebase -----------------------------------------------
try:
    if not firebase_admin._apps:
        cred = credentials.Certificate(FIREBASE_CRED_FILENAME)
        firebase_admin.initialize_app(cred)
    db = firestore.client()
    firebase_available = True
except Exception as e:
    db = None
    firebase_available = False
    st.warning("⚠️ Firebase not available.")
    print("Firebase init error:", e)

# ----------------------------- Session State ------------------------------------------
for key, val in {
    'userdata': {},
    'feedback': [],
    'spam_numbers': {},
    'parsed_numbers': {},
    'current_page': "Home",
    'otp_code': None,
    'otp_sent_time': None,
    'otp_phone': None,
    'otp_name': None,
    'verified_number': None,
    'resend_allowed_time': None
}.items():
    if key not in st.session_state:
        st.session_state[key] = val

# ----------------------------- Twilio Functions ---------------------------------------
def initialize_twilio_client():
    try:
        return Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    except Exception as e:
        print("Twilio init error:", e)
        return None

def send_otp_twilio(phone_number, otp, recipient_name="User"):
    try:
        client = initialize_twilio_client()
        if not client:
            return False

        if not phone_number.startswith('+'):
            phone_number = '+' + phone_number

        message_body = f"Hello {recipient_name},\nYour Spam Shield OTP is: {otp}\nIt will expire in 2 minutes.\n- Spam Shield"

        message = client.messages.create(
            body=message_body,
            from_=TWILIO_PHONE_NUMBER,
            to=phone_number
        )

        print(f"✅ OTP sent to {phone_number} via Twilio (SID: {message.sid})")
        return True

    except TwilioRestException as e:
        print(f"Twilio error: {e}")
        return False
    except Exception as e:
        print("OTP send error:", e)
        traceback.print_exc()
        return False

def verify_twilio_setup():
    try:
        client = initialize_twilio_client()
        if not client:
            return False, "Client not initialized"
        account = client.api.accounts(TWILIO_ACCOUNT_SID).fetch()
        return True, f"Twilio setup valid ✅ (Name: {account.friendly_name})"
    except Exception as e:
        return False, str(e)

# ----------------------------- Utilities ----------------------------------------------
@st.cache_data
def get_numlookup_info(phone_number):
    try:
        headers = {"Accept": "application/json"}
        url = f"https://api.numlookupapi.com/v1/validate/{phone_number}?apikey={NUMLOOKUP_API_KEY}"
        response = requests.get(url, headers=headers, timeout=8)
        data = response.json()
        return (
            data.get("carrier", "Unknown"),
            data.get("location", "Unknown"),
            data.get("line_type", "Unknown"),
            data.get("country_name", "Unknown")
        )
    except:
        return "Unknown", "Unknown", "Unknown", "Unknown"

def parse_phone_number(phone_number):
    if not phone_number:
        return None, None, None, None, False
    try:
        parsed = phonenumbers.parse(phone_number, None)
        if phonenumbers.is_valid_number(parsed):
            formatted = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
            return (
                formatted,
                carrier.name_for_number(parsed, "en") or "Unknown",
                geocoder.description_for_number(parsed, "en") or "Unknown",
                timezone.time_zones_for_number(parsed)[0],
                True
            )
    except:
        pass
    return None, None, None, None, False

# ----------------------------- Firestore ----------------------------------------------
def load_spam_numbers():
    if not db: return {}
    spam = {}
    try:
        for doc in db.collection('spam_numbers').stream():
            spam[doc.id] = doc.to_dict().get('report_count', 1)
    except Exception as e:
        print("load_spam_numbers:", e)
    return spam

def save_spam_number(phone):
    if not db:
        st.session_state.spam_numbers[phone] = st.session_state.spam_numbers.get(phone, 0) + 1
        return
    try:
        ref = db.collection('spam_numbers').document(phone)
        snap = ref.get()
        count = snap.to_dict().get('report_count', 0) + 1 if snap.exists else 1
        ref.set({'report_count': count})
    except Exception as e:
        print("save_spam_number error:", e)

# ----------------------------- Model ----------------------------------------------
@st.cache_resource
def load_model_and_vectorizer():
    try:
        model = joblib.load(MODEL_FILE)
        vectorizer = joblib.load(VECTORIZER_FILE)
        return model, vectorizer
    except:
        return None, None

model, vectorizer = load_model_and_vectorizer()
st.session_state.spam_numbers = load_spam_numbers()

# ----------------------------- OTP helpers --------------------------------------------
def generate_otp():
    return ''.join(str(random.randint(0, 9)) for _ in range(OTP_LENGTH))

def otp_expired():
    sent_time = st.session_state.otp_sent_time
    if not sent_time:
        return True
    return (time.time() - sent_time) > OTP_EXPIRY_SECONDS

# ----------------------------- Sidebar -----------------------------------------------
with st.sidebar:
    st.header("Navigation")
    if st.button("Home"): st.session_state.current_page = "Home"
    if st.button("Services"): st.session_state.current_page = "Services"
    if st.button("Feedback"): st.session_state.current_page = "Feedback"
    st.markdown("---")
    st.write("**Verification:**", "✅ Verified" if st.session_state.verified_number else "❌ Not Verified")
    if st.button("Check Twilio Status"):
        ok, msg = verify_twilio_setup()
        if ok: st.success(msg)
        else: st.error(msg)

# ----------------------------- Verification -------------------------------------------
st.title("Spam Shield 🛡️")
st.markdown("📱 **Secure OTP Verification (via Twilio SMS)**")

if not st.session_state.verified_number:
    name = st.text_input("Your Name:")
    phone = st.text_input("Phone Number (+91...):")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Send OTP"):
            if not name or not phone:
                st.warning("Enter both name and number.")
            else:
                formatted, *_ , valid = parse_phone_number(phone)
                if not valid:
                    st.error("Invalid number.")
                else:
                    otp = generate_otp()
                    if send_otp_twilio(formatted, otp, name):
                        st.session_state.otp_code = otp
                        st.session_state.otp_sent_time = time.time()
                        st.session_state.otp_phone = formatted
                        st.session_state.otp_name = name
                        st.success(f"OTP sent to {formatted}")
                    else:
                        st.error("Failed to send OTP via Twilio.")
    with col2:
        if st.button("Resend OTP"):
            if not st.session_state.otp_phone:
                st.warning("Send OTP first.")
            else:
                otp = generate_otp()
                if send_otp_twilio(st.session_state.otp_phone, otp, st.session_state.otp_name):
                    st.session_state.otp_code = otp
                    st.session_state.otp_sent_time = time.time()
                    st.info("OTP resent.")
                else:
                    st.error("Resend failed.")

    if st.session_state.otp_code:
        otp_input = st.text_input("Enter OTP:", type="password")
        if st.button("Verify OTP"):
            if otp_expired():
                st.error("OTP expired. Please resend.")
            elif otp_input == st.session_state.otp_code:
                st.session_state.verified_number = st.session_state.otp_phone
                st.success(f"✅ Verified! Welcome {st.session_state.otp_name}")
                st.balloons()
                st.rerun()
            else:
                st.error("Incorrect OTP.")
    st.stop()

# ----------------------------- Main Pages ---------------------------------------------
page = st.session_state.current_page

if page == "Home":
    st.header("Welcome to Spam Shield ⚔️")
    st.write("""
    Spam Shield protects against spam calls and SMS.
    ✅ Reliable OTP (Twilio SMS)
    ✅ Global coverage
    ✅ Spam message detection
    """)

elif page == "Services":
    tab1, tab2, tab3 = st.tabs(["🔍 Search Number", "💬 Check Spam Message", "🚨 Report Spam"])

    with tab1:
        phone = st.text_input("Enter Number to Lookup:")
        if st.button("Search"):
            formatted, prov, region, tz, valid = parse_phone_number(phone)
            if not valid:
                st.error("Invalid number.")
            else:
                api_prov, loc, line, country = get_numlookup_info(formatted)
                reports = st.session_state.spam_numbers.get(formatted, 0)
                st.write(f"📞 **Number:** {formatted}")
                st.write(f"📶 **Provider:** {api_prov}")
                st.write(f"🌍 **Location:** {loc}")
                st.write(f"📱 **Type:** {line}")
                st.write(f"🌎 **Country:** {country}")
                st.write(f"🚨 **Reports:** {reports}")

    with tab2:
        msg = st.text_area("Enter Message:")
        if st.button("Check Spam"):
            if not msg.strip():
                st.warning("Enter a message.")
            else:
                result = "✅ Not Spam"
                spam_keywords = ["win", "free", "offer", "click", "link", "urgent"]
                if any(w in msg.lower() for w in spam_keywords):
                    result = "🚨 Spam"
                st.write(f"🔍 Result: {result}")

    with tab3:
        rep = st.text_input("Report Spam Number:")
        if st.button("Report"):
            formatted, *_ , valid = parse_phone_number(rep)
            if not valid:
                st.error("Invalid number.")
            else:
                save_spam_number(formatted)
                st.success("Reported successfully.")

elif page == "Feedback":
    st.header("📝 Feedback")
    fb = st.text_area("Enter your feedback:")
    if st.button("Submit"):
        if fb.strip():
            st.session_state.feedback.append(fb)
            if db:
                db.collection("feedback").add({"entry": fb, "time": datetime.now()})
            st.success("Thanks for your feedback!")
        else:
            st.warning("Enter feedback before submitting.")

else:
    st.write("Page not found.")
