# spamshield_with_otp.py
# Full Spam Shield Streamlit app with Fast2SMS OTP verification.
#
# Features:
# - OTP via Fast2SMS (route=otp) using GET URL format required by Fast2SMS docs
# - 6-digit numeric OTP, expires after 120 seconds (2 minutes)
# - Resend OTP allowed after 60 seconds (countdown shown)
# - Spinner while sending OTP
# - Verified users saved to Firestore collection "users"
# - Verification required before accessing app features
# - Spam number lookup via Numlookup API
# - ML-based message spam classification (joblib model & vectorizer)
# - Report spam numbers to Firestore collection "spam_numbers"
# - Feedback saved to Firestore collection "feedback"
#
# Requirements:
# pip install streamlit phonenumbers firebase-admin joblib requests pandas
#
# Put your Firebase service account JSON as 'serviceAccountKey.json' in same directory.

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

# Firebase
import firebase_admin
from firebase_admin import credentials, firestore

# ----------------------------- Config (edit if necessary) -----------------------------
# Fast2SMS API key (hardcoded as requested)
FAST2SMS_API_KEY = "RqVxel3hVmosidQdWpSmgQBI7hN9ROckLEjj1OUs2KKhoMpgSKscU4uWfs48"

# Numlookup API key (replace if you have a different key)
NUMLOOKUP_API_KEY = "num_live_1DP975acU1UFuYM0qR8oKUWFMDZxq6cz7fx8Qs8P"

# OTP settings
OTP_LENGTH = 6
OTP_EXPIRY_SECONDS = 120    # 2 minutes
OTP_RESEND_COOLDOWN = 60   # 60 seconds before allowing resend

# Filenames for model & vectorizer
MODEL_FILE = "spam_classifier.pkl"
VECTORIZER_FILE = "tfidf_vectorizer.pkl"

# Firebase credential filename (must exist in the project directory)
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
    # We'll still continue using session state as fallback
    st.warning("Warning: Firebase init failed. Using local session state only. "
               "Check your serviceAccountKey.json and Firestore permissions.")
    # print error to logs for debugging
    print("Firebase init error:", e)
    traceback.print_exc()

# ----------------------------- Session-state initial values ---------------------------
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

# OTP session items
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

# ----------------------------- Utilities: Number parsing, Numlookup -------------------
@st.cache_data
def get_numlookup_info(phone_number):
    """
    Calls Numlookup API and returns (service_provider, location, line_type, country)
    """
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
        print("Numlookup error:", e)
        return "Unknown", "Unknown", "Unknown", "Unknown"

def parse_phone_number(phone_number):
    """
    Parse and validate a phone number; returns (formatted_e164, carrier, region, timezone_str, is_valid)
    Accepts formats like: +919876543210, 919876543210, 9876543210
    """
    if not phone_number:
        return (None, None, None, None, False)
    if phone_number in st.session_state.parsed_numbers:
        return st.session_state.parsed_numbers[phone_number]
    try:
        # normalize: if user enters 10-digit without country, try default country 'IN'
        candidate = phone_number.strip()
        if candidate.startswith("+"):
            parsed = phonenumbers.parse(candidate, None)
        else:
            # attempt parse with None first; fallback to "IN"
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

# ----------------------------- Firestore / Local load/save helpers --------------------
def load_userdata():
    """
    Load first ~100 users from Firestore 'users' collection into session state (if Firestore available).
    """
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
    """
    Save a dict mapping phone->name into Firestore 'users' collection (batch)
    """
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
        # remove old docs, write new ones (keeps indexing stable)
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
    """
    Increment spam report count for a phone (in Firestore transaction if available).
    Returns updated count.
    """
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
        # verify
        doc = spam_ref.get()
        if doc.exists and doc.to_dict().get('report_count') == new_count:
            return new_count
        else:
            # fallback
            return st.session_state.spam_numbers.get(phone, new_count)
    except Exception as e:
        print("save_spam_number error:", e)
        return st.session_state.spam_numbers.get(phone, 0)

# ----------------------------- Load initial data into session -------------------------
st.session_state.userdata = load_userdata()
st.session_state.feedback = load_feedback()
if 'spam_numbers' not in st.session_state or not st.session_state.spam_numbers:
    # a modest initial list to bootstrap UI (same format used originally)
    initial_spam_numbers = {
        "+917397947365": 3, "+917550098431": 2, "+919150228347": 5,
        "+918292577122": 1, "+919060883501": 4
    }
    st.session_state.spam_numbers = load_spam_numbers()
    for p, c in initial_spam_numbers.items():
        if p not in st.session_state.spam_numbers:
            st.session_state.spam_numbers[p] = c

spam_numbers = st.session_state.spam_numbers

# ----------------------------- Load ML model (optional) --------------------------------
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

# ----------------------------- Fast2SMS helper functions --------------------------------
def _normalize_number_for_api(phone):
    """
    Convert +91xxxxxxxxxx, 91xxxxxxxxxx, 0xxxxxxxxxx or xxxxxxxxxx -> accepted format by Fast2SMS URL.
    Fast2SMS accepts numbers like 919876543210 or 9876543210; we will pass either 10-digit or leading 91 form.
    """
    if not phone:
        return ""
    s = re.sub(r"[^\d]", "", str(phone))
    # strip leading zeros
    s = s.lstrip("0")
    # if length==12 and startswith 91, keep; if length==10, keep; if length==11 with leading 1? just return digits
    return s

def send_otp_via_fast2sms(phone_number, otp):
    """
    Send OTP using Fast2SMS OTP route. Uses GET URL per Fast2SMS dev docs.
    Returns True on likely success; False otherwise.
    """
    try:
        norm = _normalize_number_for_api(phone_number)
        if not norm:
            return False
        # Build the URL exactly as required (params in URL)
        url = (
            f"https://www.fast2sms.com/dev/bulkV2?authorization={FAST2SMS_API_KEY}"
            f"&variables_values={otp}&route=otp&flash=0&numbers={norm}"
        )
        # Send GET request
        resp = requests.get(url, timeout=12)
        print("FAST2SMS DEBUG:", resp.status_code, resp.text)
        try:
            j = resp.json()
            return j.get("return", False)
        except Exception:
            return resp.status_code == 200
    except Exception as e:
        print("send_otp_via_fast2sms exception:", e)
        return False

# ----------------------------- OTP UI helpers ------------------------------------------
def _generate_otp():
    return ''.join(str(random.randint(0,9)) for _ in range(OTP_LENGTH))

def _can_resend():
    # returns True if resend allowed now
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

# ----------------------------- Navigation Sidebar --------------------------------------
with st.sidebar:
    st.header("Navigation")
    if st.button("Home", key="nav_home"):
        st.session_state.current_page = "Home"
    if st.button("Services", key="nav_services"):
        st.session_state.current_page = "Services"
    if st.button("Feedback", key="nav_feedback"):
        st.session_state.current_page = "Feedback"
    st.markdown("---")
    st.write("Logged-in (verified):", bool(st.session_state.get('verified_number')))

# ----------------------------- Verification Gate --------------------------------------
st.title("Spam Shield 🛡️")
st.markdown("Protecting you from spam calls and messages — please verify your phone to continue.")

# If user already verified in session, bypass OTP step
if st.session_state.get('verified_number'):
    verified = True
else:
    verified = False

# Verification flow
if not verified:
    st.subheader("Verify Your Number ✅")
    name = st.text_input("Your Name", key="verify_name")
    phone_input = st.text_input("Your Phone Number (accepts +91, 91..., or 10-digit)", key="verify_phone")

    # Buttons / actions
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Send OTP"):
            if not name or not phone_input:
                st.warning("Please enter both name and phone number.")
            else:
                formatted_phone, _, _, _, is_valid = parse_phone_number(phone_input)
                if not is_valid:
                    st.error("Invalid phone number. Please enter a valid number (include country code or enter 10-digit).")
                else:
                    # generate OTP and send
                    otp = _generate_otp()
                    with st.spinner("Please wait — sending OTP..."):
                        sent = send_otp_via_fast2sms(formatted_phone, otp)
                    if sent:
                        st.session_state.otp_code = otp
                        st.session_state.otp_sent_time = time.time()
                        st.session_state.otp_phone = formatted_phone
                        st.session_state.otp_name = name
                        st.session_state.resend_allowed_time = time.time() + OTP_RESEND_COOLDOWN
                        st.success(f"OTP sent to {formatted_phone}. It will expire in 2 minutes.")
                    else:
                        # show helpful hint for debugging
                        st.error("Failed to send OTP. Check Fast2SMS API key, route permissions, or account credits.")
                        st.write("Tip: Verify in the Fast2SMS dashboard that your API key has the OTP route enabled.")
    with col2:
        # Resend (only shown when allowed)
        if not _can_resend():
            st.write(f"Resend available in {_resend_seconds_left()}s")
        else:
            if st.button("Resend OTP"):
                # allow resend only if previous OTP isn't active or allowed time reached
                if not st.session_state.get('otp_phone'):
                    st.warning("No OTP request found — click Send OTP first.")
                else:
                    formatted_phone, _, _, _, is_valid2 = parse_phone_number(st.session_state.otp_phone)
                    if not is_valid2:
                        st.error("Internal: stored phone is invalid. Please request a new OTP.")
                    else:
                        otp2 = _generate_otp()
                        with st.spinner("Resending OTP..."):
                            sent2 = send_otp_via_fast2sms(formatted_phone, otp2)
                        if sent2:
                            st.session_state.otp_code = otp2
                            st.session_state.otp_sent_time = time.time()
                            st.session_state.resend_allowed_time = time.time() + OTP_RESEND_COOLDOWN
                            st.info("OTP resent successfully.")
                        else:
                            st.error("Failed to resend OTP. Check Fast2SMS/Balances.")

    # Show OTP input if OTP was sent
    if st.session_state.get('otp_code'):
        st.markdown("---")
        st.write("Enter the OTP you received on your phone.")
        otp_entered = st.text_input("OTP", key="otp_input_field", type="password")
        if st.button("Verify OTP"):
            # check expiry
            if st.session_state.get('otp_sent_time') is None:
                st.error("No OTP has been sent. Click Send OTP first.")
            else:
                elapsed = time.time() - st.session_state.otp_sent_time
                if elapsed > OTP_EXPIRY_SECONDS:
                    st.error("OTP expired — please resend and try again.")
                    # clear OTP
                    st.session_state.otp_code = None
                    st.session_state.otp_sent_time = None
                    st.session_state.otp_phone = None
                    st.session_state.otp_name = None
                    st.session_state.resend_allowed_time = None
                else:
                    if otp_entered == st.session_state.otp_code:
                        # Verified - save to Firestore 'users'
                        formatted_phone, _, _, _, _ = parse_phone_number(st.session_state.otp_phone)
                        name_to_save = st.session_state.otp_name
                        try:
                            if db:
                                db.collection('users').document(formatted_phone).set({
                                    'name': name_to_save,
                                    'verified': True,
                                    'verified_at': firestore.SERVER_TIMESTAMP
                                })
                            # also store in session userdata for instant use
                            st.session_state.userdata[formatted_phone] = name_to_save
                            save_userdata({formatted_phone: name_to_save})
                            st.success(f"✅ Verified! Thank you, {name_to_save}. You now have access.")
                        except Exception as e:
                            st.error(f"Verified but failed to save to Firestore: {e}. Saved locally instead.")
                            st.session_state.userdata[formatted_phone] = name_to_save
                        # mark verified in session
                        st.session_state.verified_number = formatted_phone
                        # clear OTP sensitive state
                        st.session_state.otp_code = None
                        st.session_state.otp_sent_time = None
                        st.session_state.otp_phone = None
                        st.session_state.otp_name = None
                        st.session_state.resend_allowed_time = None
                    else:
                        st.error("Incorrect OTP. Please try again.")

        # show expiry countdown
        seconds_left = _otp_seconds_left()
        if seconds_left > 0:
            st.info(f"OTP expires in {seconds_left} seconds.")
        else:
            st.warning("OTP has likely expired. Please resend.")

    # block main app until verified
    st.stop()

# ----------------------------- Main App: user is verified --------------------------------
# At this point we have a verified user (st.session_state.verified_number)
try:
verified_phone = st.session_state.verified_number
except Exception:
    verified_phone = None

if verified_phone:
    st.success(f"Access granted for {verified_phone} ✅")
else:
    # Safety: shouldn't happen because of st.stop() above, but keep guard
    st.error("No verified user found — restart verification.")
    st.stop()

# Recreate original UI features but gated: Home, Services, Feedback
page = st.session_state.current_page

# Home tab example & verify display
if page == "Home":
    tab1, tab2 = st.tabs(["Introduction", "Verify Info"])
    with tab1:
        st.header("Welcome to Spam Shield ⚔️")
        st.write("""
            **Spam Shield** protects against spam calls and text messages.
            Verify your number to contribute by reporting spam numbers and using the lookup tools.
        """)
    with tab2:
        st.header("Your Verified Info")
        name_for_display = st.session_state.userdata.get(verified_phone, "Unknown")
        st.write(f"**Name:** {name_for_display}")
        st.write(f"**Verified Phone:** {verified_phone}")

# Services page with Search, Spam detection, Report
elif page == "Services":
    tab1, tab2, tab3 = st.tabs(["🔍 Search Number", "💬 Check Spam Message", "🚨 Report Spam"])

    # SEARCH NUMBER
    with tab1:
        st.header("Search a Number 🔍")
        phone_input = st.text_input("Enter phone number to check (e.g., +91 1234567890):", key="services_phone_input")
        if st.button("Search", key="search_button"):
            if not phone_input.strip():
                st.warning("Please enter a phone number.")
            else:
                formatted_number, local_provider, region, time_zone, is_valid_n = parse_phone_number(phone_input)
                if not is_valid_n:
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
                    # heuristics retained from original
                    if number_without_country.startswith("14"):
                        classification = "🚨 Spam"
                    elif number_without_country.startswith("88265"):
                        classification = "🚨 Spam"
                    elif number_without_country.startswith("796512"):
                        classification = "🚨 Spam"
                    elif number_without_country.startswith("16"):
                        special_classification = "Government or Regulators"
                        classification = "ℹ️ Not Spam"
                    if formatted_number.startswith("+140") or formatted_number.startswith("140"):
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
                        st.write("Note: Provider may vary due to MNP.")
                    st.write(f"🌍 **Region/City:** {location if location != 'Unknown' else region}")
                    st.write(f"⏰ **Time Zone:** {time_zone}")
                    st.write(f"📞 **Line Type:** {line_type}")
                    st.write(f"🌎 **Country:** {country}")
                    st.write(f"🔍 **Classification:** {classification}")
                    if is_reported_spam:
                        st.write(f"⚠️ **This number has been reported {report_count} times.**")

    # CHECK SPAM MESSAGE
    with tab2:
        st.header("Check Spam Messages 💬")
        user_message = st.text_area("Enter message text to check:", key="sms_input", height=140)
        SPAM_KEYWORDS = [
            "won", "click", "link", "prize", "free", "claim", "urgent", "offer",
            "win", "congratulations", "money", "rupee", "reward", "lottery", "click"
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
                    try:
                        user_message_vectorized = vectorizer.transform([user_message])
                        prediction = model.predict(user_message_vectorized)[0]
                    except Exception as me:
                        st.error("Model error: cannot classify. See console.")
                        print("Model predict error:", me)
                        prediction = 0
                    if is_trusted and spam_keyword_count <= 1:
                        result = "✅ Not Spam"
                    elif spam_keyword_count >= 2 or prediction == 1:
                        result = "🚨 Spam"
                    else:
                        result = "✅ Not Spam"
                else:
                    # fallback heuristics if model not loaded
                    if spam_keyword_count >= 2:
                        result = "🚨 Spam"
                    else:
                        result = "✅ Not Spam"

                if "🚨 Spam" in result:
                    st.error("This message is a spam.")
                else:
                    st.success("This message is not a spam.")
                st.write(f"🔍 **Classification:** {result}")
                if spam_keyword_count > 0 and result == "🚨 Spam":
                    st.warning(f"⚠️ Classified as spam due to {spam_keyword_count} suspicious keyword(s).")

    # REPORT SPAM
    with tab3:
        st.header("Report a Spam Number ⚠️")
        spam_input = st.text_input("Enter phone number to report as spam:", key="report_input")
        if st.button("Report Spam", key="report_spam_button"):
            if not spam_input.strip():
                st.warning("Please enter a valid phone number to report.")
            else:
                formatted_feedback, _, _, _, is_valid_fb = parse_phone_number(spam_input)
                if is_valid_fb:
                    previous_count = st.session_state.spam_numbers.get(formatted_feedback, 0)
                    updated_count = save_spam_number(formatted_feedback)
                    st.session_state.spam_numbers[formatted_feedback] = updated_count
                    if updated_count > previous_count:
                        st.success("🚨 The number is successfully reported")
                        st.info(f"It has been reported {updated_count} times by the people.")
                    else:
                        st.error("Failed to report number. Check Firestore connection and security rules.")
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
            st.success("Thank you for your feedback!")
        else:
            st.warning("Please enter some feedback.")

# Fallback: if page unknown
else:
    st.write("Unknown page. Use sidebar to navigate.")

# ----------------------------- End of app ---------------------------------------------
