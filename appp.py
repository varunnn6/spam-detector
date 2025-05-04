import streamlit as st

# Load user data from file
def load_user_data():
    try:
        with open("userdata.txt", "r") as f:
            lines = f.readlines()
            data = {}
            for line in lines:
                phone, name = line.strip().split(",", 1)
                data[phone] = name
            return data
    except FileNotFoundError:
        return {}

# Load spam numbers from file
def load_spam_data():
    try:
        with open("spam_numbers.txt", "r") as f:
            return set([line.strip() for line in f.readlines()])
    except FileNotFoundError:
        return set()

# Save new user to file
def save_user(phone, name):
    with open("userdata.txt", "a") as f:
        f.write(f"{phone},{name}\n")

# Save new spam number to file
def save_spam(phone):
    with open("spam_numbers.txt", "a") as f:
        f.write(f"{phone}\n")

# Streamlit UI
st.title("📱 Phone Number Tracker")

# Load data
user_data = load_user_data()
spam_numbers = load_spam_data()

# Tabs
tab1, tab2 = st.tabs(["🔍 Verify Number", "🚨 Report Spam"])

# --- Tab 1: Verify Number ---
with tab1:
    st.header("Verify a Number")
    phone_input = st.text_input("Enter phone number to verify:")

    if st.button("Verify"):
        if phone_input in spam_numbers:
            st.error("⚠️ This number has been reported as spam!")
        elif phone_input in user_data:
            st.success(f"✅ Verified! Name: {user_data[phone_input]}")
        else:
            name = st.text_input("New number. Enter name to register:")
            if name:
                save_user(phone_input, name)
                st.success(f"✅ {name} has been added to the database.")

# --- Tab 2: Report Spam ---
with tab2:
    st.header("Report a Spam Number")
    spam_input = st.text_input("Enter phone number to report as spam:")

    if st.button("Report Spam"):
        if spam_input in spam_numbers:
            st.info("ℹ️ This number is already reported as spam.")
        else:
            save_spam(spam_input)
            st.success("🚨 Spam number reported successfully.")
