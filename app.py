import os
import json
from datetime import datetime
from dotenv import load_dotenv
load_dotenv(override=True)
import streamlit as st
from PIL import Image, ImageDraw, ImageFont

# Ensure relative imports work
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import (
    save_prescription,
    get_user_history,
)
from auth import (
    register_user,
    authenticate_user,
)
from interactions import (
    check_drug_interactions,
)
from translator import (
    translate_explanation,
    LANGUAGES,
)
from generator import (
    generate_pdf_explanation,
)

import google.generativeai as genai
from pydantic import BaseModel, Field
from typing import List

# Configure Page Config first
st.set_page_config(
    page_title="RxMate 💊 — Your Indian Language Prescription Guide",
    page_icon="💊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Setup Gemini API Key
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# Define file paths
SAMPLE_IMG_PATH = "c:/genai/apps/prescimate/sample_prescription.jpg"
PDF_DIR = "c:/genai/apps/prescimate/exports"
os.makedirs(PDF_DIR, exist_ok=True)

# Generate sample prescription image (force-overwrite with high-resolution TrueType fonts)
def ensure_sample_prescription():
    try:
        # Load high-quality system TrueType fonts (handles scaling and anti-aliasing)
        try:
            font_title = ImageFont.truetype("arial.ttf", 26)
            font_subtitle = ImageFont.truetype("arial.ttf", 16)
            font_body_bold = ImageFont.truetype("arial.ttf", 18)
            font_body = ImageFont.truetype("arial.ttf", 16)
            font_rx = ImageFont.truetype("arial.ttf", 40)
        except IOError:
            font_title = ImageFont.load_default()
            font_subtitle = font_title
            font_body_bold = font_title
            font_body = font_title
            font_rx = font_title

        # Create a high-resolution canvas
        img = Image.new("RGB", (800, 1000), "white")
        draw = ImageDraw.Draw(img)
        
        # Border
        draw.rectangle([(20, 20), (780, 980)], outline="teal", width=4)
        
        # Header (Clinic & Doctor Info)
        draw.text((60, 60), "DR. ARUN SHARMA, MD (CARDIOLOGY)", fill="darkblue", font=font_title)
        draw.text((60, 95), "Reg No: 12345-A  |  City Health Clinic, Mumbai", fill="gray", font=font_subtitle)
        draw.line([(60, 125), (740, 125)], fill="gray", width=2)
        
        # Patient Details
        draw.text((60, 150), "Patient Name: Rajesh Kumar  |  Age: 52  |  Gender: Male", fill="black", font=font_body_bold)
        draw.text((60, 180), f"Date: {datetime.now().strftime('%d/%m/%Y')}", fill="black", font=font_body)
        draw.line([(60, 210), (740, 210)], fill="gray", width=1)
        
        # Rx Symbol
        draw.text((60, 230), "Rx", fill="teal", font=font_rx)
        
        # Prescribed medicines (Aspirin + Warfarin is a major interaction)
        draw.text((100, 300), "1. Ecosprin 75 mg", fill="black", font=font_body_bold)
        draw.text((120, 330), "   Dosage: 1 tablet daily after lunch", fill="gray", font=font_body)
        
        draw.text((100, 400), "2. Warfarin 5 mg", fill="black", font=font_body_bold)
        draw.text((120, 430), "   Dosage: 1 tablet daily at 9:00 PM", fill="gray", font=font_body)
        
        draw.text((100, 500), "3. Glycomet 500 mg", fill="black", font=font_body_bold)
        draw.text((120, 530), "   Dosage: 1 tablet twice daily before meals (morning & night)", fill="gray", font=font_body)
        
        draw.text((100, 600), "4. Lipvas 10 mg", fill="black", font=font_body_bold)
        draw.text((120, 630), "   Dosage: 1 tablet at bedtime", fill="gray", font=font_body)
        
        # Footer
        draw.text((60, 780), "Please review after 1 month.", fill="black", font=font_body_bold)
        draw.text((530, 850), "Dr. Arun Sharma", fill="darkblue", font=font_body_bold)
        draw.text((530, 875), "Authorized Signature", fill="gray", font=font_subtitle)
        
        img.save(SAMPLE_IMG_PATH)
    except Exception as e:
        print(f"Failed to generate sample prescription image: {e}")

ensure_sample_prescription()

# Register default test user for testing phase
try:
    register_user("test", "password")
except Exception as e:
    pass

# Define Pydantic schema for structured output
class MedicationDetail(BaseModel):
    brand: str = Field(description="The brand name of the medicine written on the prescription")
    generic: str = Field(description="The generic / active chemical ingredient name of the medicine (e.g. Paracetamol for Crocin)")
    dosage: str = Field(description="The dosage and instructions (e.g., 1 tablet twice daily after food)")
    purpose: str = Field(description="A brief summary of what this medicine is used for")
    benefits: str = Field(description="Detailed health benefits, clinical role, and how it helps the patient's condition in patient-friendly terms")

class PrescriptionAnalysis(BaseModel):
    patient_name: str = Field(description="The name of the patient written on the prescription (e.g. HARAMOHAN KUANAR). If not found, write 'N/A'.")
    date_of_visit: str = Field(description="The date of the visit or the date when the prescription was written as found on the prescription image (e.g. 28/07/2026). If not found, write 'N/A'.")
    medications: List[MedicationDetail] = Field(description="List of all detected medications in the prescription")
    english_explanation: List[str] = Field(description="A warm, simple, plain English explanation points. Return this as a list of strings, with each medicine's explanation and general instructions as a separate item in the list.")
    what_to_watch_out_for: List[str] = Field(description="Key warnings, side effects, or general lifestyle advice related to this prescription, returned as a list of strings.")
    translated_explanation: List[str] = Field(description="The complete prescription explanation translated directly into the target Indian language. Return this as a list of strings, with each medicine/point as a separate item. Write this entire explanation in the native script of the target language (e.g. Devanagari script for Hindi, Tamil script for Tamil, Bengali script for Bengali). Ensure that all medicine brand names and generic names (e.g. TRESIBA, HUMINSULIN R, SEMASIZE) are kept in English script inside parentheses (e.g. Tresiba (degludec)) directly in the translated explanation. Do not translate or transliterate the actual brand/generic names of medicines into local script.")

def analyze_prescription_image(image: Image.Image, target_lang_name: str) -> PrescriptionAnalysis:
    """Invokes Gemini's structured output generation on the prescription image."""
    model = genai.GenerativeModel("gemini-3.5-flash")
    prompt = f"""Analyze this handwritten prescription image. Extract the patient name, date of visit/prescription date, and all the medications listed, identifying both their brand names and generic/active ingredient names, dosages, purposes, and detailed health benefits. 
Explain the benefits of each medicine in a supportive, patient-friendly way, explaining why it was prescribed and how it helps their body. Always emphasize checking in with their doctor.

IMPORTANT FORMATTING RULES:
1. The fields 'english_explanation', 'what_to_watch_out_for', and 'translated_explanation' MUST be JSON lists of strings. Each medication's detail, explanation point, or general warning should be a separate element in the list. Do NOT join them into one long string or paragraph.
2. In the 'translated_explanation' field, write the complete translation directly into {target_lang_name} using its native script (e.g. Devanagari for Hindi). Ensure that all medicine brand names and generic names (e.g. TRESIBA, HUMINSULIN R, SEMASIZE) are kept in English script inside parentheses (e.g. Tresiba (degludec)) directly in the translated explanation. Do not translate or transliterate the actual brand/generic names of medicines into local script or strip them out."""
    
    response = model.generate_content(
        [prompt, image],
        generation_config={
            "response_mime_type": "application/json",
            "response_schema": PrescriptionAnalysis
        }
    )
    
    raw_text = response.text.strip()
    # Strip markdown code blocks if the model wrapped them
    if raw_text.startswith("```"):
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        else:
            raw_text = raw_text[3:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]
        raw_text = raw_text.strip()

    # Escape raw/unescaped carriage returns and newlines inside JSON string fields to prevent parsing errors
    in_string = False
    escape = False
    cleaned_chars = []
    for char in raw_text:
        if char == '"' and not escape:
            in_string = not in_string
        
        if char == '\\' and not escape:
            escape = True
        else:
            escape = False
            
        if in_string and char == '\n':
            cleaned_chars.append('\\n')
        elif in_string and char == '\r':
            cleaned_chars.append('\\r')
        else:
            cleaned_chars.append(char)
            
    cleaned_text = "".join(cleaned_chars)
    data = json.loads(cleaned_text)
    return data

# Streamlit CSS Customization (Premium look and feel)
st.markdown("""
<style>
    /* Styling headers and fonts */
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Outfit', sans-serif;
    }
    
    .logo-container {
        display: flex;
        align-items: center;
        margin-bottom: 20px;
    }
    
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        color: #0F4C5C;
        margin-bottom: 5px;
    }
    
    .disclaimer-card {
        background-color: #FFF3CD;
        border-left: 5px solid #FFC107;
        padding: 15px;
        border-radius: 6px;
        margin-top: 25px;
        margin-bottom: 25px;
        color: #856404;
        font-size: 0.9rem;
    }
    
    .interaction-card-major {
        background-color: #F8D7DA;
        border-left: 5px solid #DC3545;
        padding: 15px;
        border-radius: 8px;
        margin-bottom: 12px;
        color: #721C24;
    }
    
    .interaction-card-moderate {
        background-color: #FFF3CD;
        border-left: 5px solid #FFC107;
        padding: 15px;
        border-radius: 8px;
        margin-bottom: 12px;
        color: #856404;
    }
    
    .premium-card {
        background-color: #f8f9fa;
        border: 1px solid #e9ecef;
        padding: 20px;
        border-radius: 12px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.02);
        margin-bottom: 20px;
    }
    
    .highlight-pill {
        background-color: #E2ECE9;
        color: #0F4C5C;
        font-weight: bold;
        padding: 4px 10px;
        border-radius: 12px;
        font-size: 0.85rem;
        display: inline-block;
        margin-right: 5px;
    }
    
    /* Hide Streamlit header, footer, MainMenu, and deployment badges */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .stAppDeployButton {display: none !important;}
    .viewerBadge {display: none !important;}
    .stViewerBadge {display: none !important;}
    div.viewerBadge {display: none !important;}
    a.viewerBadge {display: none !important;}
</style>
""", unsafe_allow_html=True)

# Initialize Session State
if "current_user" not in st.session_state:
    st.session_state.current_user = None
if "selected_prescription" not in st.session_state:
    st.session_state.selected_prescription = None

# --- User Auth Screens ---
if st.session_state.current_user is None:
    st.markdown("<h1 style='text-align: center; color: #0F4C5C;'>PresciMate 💊</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; font-size: 1.15rem; margin-bottom: 5px;'>Your plain-language medical prescription guide in your own Indian language.</p>", unsafe_allow_html=True)
    st.write("---")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        auth_tab1, auth_tab2 = st.tabs(["🔒 Login to Account", "👤 Create New Account"])
        
        with auth_tab1:
            st.write("### Sign In")
            login_user = st.text_input("Username", value="test", key="login_user_key")
            login_pass = st.text_input("Password", value="password", type="password", key="login_pass_key")
            if st.button("Login", use_container_width=True):
                user = authenticate_user(login_user, login_pass)
                if user:
                    st.session_state.current_user = user
                    st.success(f"Welcome back, {user['username']}!")
                    st.rerun()
                else:
                    st.error("Invalid username or password.")
                    
        with auth_tab2:
            st.write("### Create Account")
            st.info("Everything stays private to your account. No medical details are shared publicly.")
            reg_user = st.text_input("Username", key="reg_user_key")
            reg_pass = st.text_input("Password (min 6 characters)", type="password", key="reg_pass_key")
            reg_pass_conf = st.text_input("Confirm Password", type="password", key="reg_pass_conf_key")
            
            if st.button("Sign Up", use_container_width=True):
                if reg_pass != reg_pass_conf:
                    st.error("Passwords do not match.")
                else:
                    success, msg = register_user(reg_user, reg_pass)
                    if success:
                        st.success("Account created successfully! Please switch to the Login tab.")
                    else:
                        st.error(msg)
                        
        # Render About application information card directly below the login/signup form (col2)
        try:
            about_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "about_card.html")
            with open(about_path, "r", encoding="utf-8") as f:
                about_html = f.read()
            st.markdown(about_html, unsafe_allow_html=True)
        except Exception as e:
            st.error(f"Could not load application info: {e}")
    st.stop()

# --- Authenticated App ---
user = st.session_state.current_user

# --- Sidebar (History & Search) ---
with st.sidebar:
    st.write(f"### 👤 Active Account: **{user['username']}**")
    
    if st.button("Logout", type="secondary", use_container_width=True):
        st.session_state.current_user = None
        st.session_state.selected_prescription = None
        st.rerun()
        
    st.write("---")
    st.write("### 🔍 Prescription Search & History")
    search_q = st.text_input("Search (e.g. 'Aspirin', 'bedtime')", placeholder="Hybrid vector search...")
    
    # Retrieve user history using Qdrant (Hybrid search when query is typed)
    history = get_user_history(user["id"], search_q if search_q.strip() else None)
    
    if history:
        st.write(f"Records Found: {len(history)}")
        for item in history:
            # Parse Date
            dt_parsed = datetime.fromisoformat(item["timestamp"]).strftime("%d %b %Y, %H:%M")
            button_label = f"📄 {item['image_name'][:18]}...\n({dt_parsed})"
            
            if st.button(button_label, key=f"hist_{item['id']}", use_container_width=True):
                st.session_state.selected_prescription = item
                st.rerun()
    else:
        st.write("No prescription history found.")

# --- Main Window Dashboard ---
st.markdown("<div class='logo-container'><h1 class='main-header'>RxMate 💊</h1></div>", unsafe_allow_html=True)
st.write("Translate prescription brand names into plain language and check for interactions instantly.")

# Collapsible expander displaying workflow & LLM details
with st.expander("💡 How RxMate Works & LLM Technology Stack Details", expanded=False):
    try:
        workflow_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "workflow_and_llm.html")
        with open(workflow_path, "r", encoding="utf-8") as f:
            workflow_html = f.read()
        st.markdown(workflow_html, unsafe_allow_html=True)
    except Exception as e:
        st.error(f"Could not load workflow details: {e}")

# Banner displaying current selection or mode
if st.session_state.selected_prescription:
    current_presc = st.session_state.selected_prescription
    st.write("---")
    col_back, col_title = st.columns([1, 6])
    with col_back:
        if st.button("← Upload New", use_container_width=True):
            st.session_state.selected_prescription = None
            st.rerun()
    with col_title:
        # Extract patient name and date of visit from stored prescription JSON
        try:
            analysis_data = json.loads(current_presc["extracted_text"])
            patient_name = analysis_data.get("patient_name", "N/A")
            date_of_visit = analysis_data.get("date_of_visit", "N/A")
        except Exception:
            patient_name = "N/A"
            date_of_visit = "N/A"
            
        st.subheader(f"Viewing Saved Prescription: {current_presc['image_name']}")
        meta_md = []
        if patient_name and patient_name != "N/A":
            meta_md.append(f"👤 **Patient Name:** {patient_name}")
        if date_of_visit and date_of_visit != "N/A":
            meta_md.append(f"📅 **Date of Visit:** {date_of_visit}")
            
        if meta_md:
            st.markdown("  |  ".join(meta_md))
        
    # DISPLAY PREVIOUS PRESCRIPTION
    tab1, tab2, tab3 = st.tabs(["Overview (English)", "Translated Explanation", "Interactions & Warnings"])
    
    with tab1:
        # Table of medications
        st.write("### Medications List")
        meds_data = current_presc["raw_meds"]
        
        # Build numbered tabular visualizer with user-friendly headers
        numbered_meds = []
        for idx, med in enumerate(meds_data, 1):
            numbered_meds.append({
                "No.": idx,
                "Medicine / Brand Name": med.get("brand", "N/A"),
                "Active Ingredient": med.get("generic", "N/A"),
                "Dosage & Frequency": med.get("dosage", "N/A"),
                "Health Benefits": med.get("benefits", med.get("purpose", "N/A"))
            })
        st.table(numbered_meds)
        
        st.write("### Plain English Explanation")
        st.markdown(current_presc["explanation"])
        
    with tab2:
        st.subheader(f"Explanation in {current_presc['lang_code']}")
        st.markdown(current_presc["translated_explanation"])
        
    with tab3:
        st.write("### Drug Interaction Audit")
        
        # Recalculate or retrieve interactions
        generic_names = [med.get("generic", "") for med in meds_data if med.get("generic")]
        interactions = check_drug_interactions(generic_names)
        
        if interactions:
            for item in interactions:
                card_class = "interaction-card-major" if item["severity"] == "Major" else "interaction-card-moderate"
                st.markdown(f"""
                <div class="{card_class}">
                    <h4>⚠️ {item['severity']} Interaction Detected</h4>
                    <strong>{item['drug_a']} ({item['generic_a']})</strong> + <strong>{item['drug_b']} ({item['generic_b']})</strong>
                    <p style="margin-top: 5px; margin-bottom: 0px;">{item['description']}</p>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.success("No drug-drug interactions detected for the medicines on this prescription.")
            
        st.markdown("""
        <div class="disclaimer-card">
            <strong>⚠️ Medical Disclaimer</strong><br/>
            PresciMate is an AI tool and does NOT provide professional medical advice, diagnosis, or treatment. 
            All medication explanations and interaction warnings are computed automatically. Always review these details 
            with your prescribing physician or doctor. Never stop or alter dosage without clinical advice.
        </div>
        """, unsafe_allow_html=True)
        
    # PDF generation trigger
    pdf_filename = f"prescimate_{current_presc['id']}.pdf"
    pdf_path = os.path.join(PDF_DIR, pdf_filename)
    
    dt_str = datetime.fromisoformat(current_presc['timestamp']).strftime("%d/%m/%Y")
    
    # Extract patient name and date of visit from stored prescription JSON
    try:
        analysis_data = json.loads(current_presc["extracted_text"])
        patient_name = analysis_data.get("patient_name", "N/A")
        date_of_visit = analysis_data.get("date_of_visit", "N/A")
        if patient_name == "N/A" or not patient_name:
            patient_name = user["username"]
    except Exception:
        patient_name = user["username"]
        date_of_visit = "N/A"
        
    # Generate the PDF file on demand (always regenerate to ensure layout/formatting updates are reflected)
    generate_pdf_explanation(
        pdf_path,
        patient_name,  # Pass extracted patient name instead of account username
        current_presc["image_name"],
        dt_str,
        meds_data,
        current_presc["explanation"],
        current_presc["lang_code"],
        current_presc["translated_explanation"],
        interactions,
        date_of_visit=date_of_visit
    )
    
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()
        
    st.download_button(
        label="📥 Download Explanation Report (PDF)",
        data=pdf_bytes,
        file_name=pdf_filename,
        mime="application/pdf",
        use_container_width=True
    )

else:
    # UPLOAD / PROCESS NEW PRESCRIPTION MODE
    st.write("### 📤 Step 1: Upload or Capture Prescription")
    
    img_choice = st.radio("Choose Input Method", ["Upload File", "Take Photo", "Use Demo/Sample Prescription"])
    
    uploaded_file = None
    taken_photo = None
    use_demo = False
    
    if img_choice == "Upload File":
        uploaded_file = st.file_uploader("Upload prescription photo (PNG, JPG, JPEG)", type=["png", "jpg", "jpeg"])
    elif img_choice == "Take Photo":
        taken_photo = st.camera_input("Take prescription snapshot")
    else:
        use_demo = True
        st.info("Demonstrates PresciMate with a pre-configured sample prescription containing: Ecosprin (Aspirin), Warfarin, Glycomet (Metformin), and Lipvas (Atorvastatin).")
        if st.checkbox("Show Sample Image Preview"):
            ensure_sample_prescription()
            st.image(SAMPLE_IMG_PATH, caption="Sample Doctor's Prescription (Ecosprin + Warfarin)", width=450)
            
    st.write("---")
    st.write("### 🗣️ Step 2: Choose Indian Language")
    lang_selection = st.selectbox(
        "Which language would you like the explanation in?",
        list(LANGUAGES.keys())
    )
    
    st.write("---")
    st.write("### 🚀 Step 3: Parse and Explain")
    
    if st.button("Generate Plain-Language Explanation", type="primary", use_container_width=True):
        image = None
        img_name = ""
        
        if use_demo:
            ensure_sample_prescription()
            image = Image.open(SAMPLE_IMG_PATH)
            img_name = "demo_prescription.jpg"
        elif uploaded_file:
            import io
            file_bytes = uploaded_file.getvalue()
            try:
                image = Image.open(io.BytesIO(file_bytes))
                img_name = uploaded_file.name
            except Exception as e:
                magic = list(file_bytes[:10]) if file_bytes else []
                st.error(f"Pillow could not identify the uploaded image file. Details: {e}. File size: {len(file_bytes)} bytes. First 10 bytes: {magic}")
                st.stop()
        elif taken_photo:
            import io
            file_bytes = taken_photo.getvalue()
            try:
                image = Image.open(io.BytesIO(file_bytes))
                img_name = "captured_photo.jpg"
            except Exception as e:
                magic = list(file_bytes[:10]) if file_bytes else []
                st.error(f"Pillow could not identify the captured camera photo. Details: {e}. File size: {len(file_bytes)} bytes. First 10 bytes: {magic}")
                st.stop()
            
        if image is None:
            st.error("Please provide an image of a prescription first.")
        elif not use_demo and not GEMINI_API_KEY:
            st.error("GEMINI_API_KEY environment variable is not configured. Cannot process OCR.")
        else:
            # PROCESS PRESCRIPTION
            with st.spinner("Processing... Please wait."):
                if use_demo:
                    st.write("📊 Retrieving pre-configured mock data for the demo prescription...")
                    import time
                    time.sleep(0.5) # Fast local response
                    
                    analysis = {
                        "patient_name": "Rajesh Kumar",
                        "medications": [
                            {
                                "brand": "Ecosprin 75 mg",
                                "generic": "aspirin",
                                "dosage": "1 tablet daily after lunch",
                                "purpose": "Blood thinner to prevent heart attacks and strokes.",
                                "benefits": "Prevents blood cells (platelets) from clumping together to form blood clots. This drastically reduces the risk of heart attacks, ischemic strokes, and protects cardiovascular health."
                            },
                            {
                                "brand": "Warfarin 5 mg",
                                "generic": "warfarin",
                                "dosage": "1 tablet daily at 9:00 PM",
                                "purpose": "Blood thinner to treat or prevent blood clots.",
                                "benefits": "Slows down the body's process of making clots. It prevents existing clots from growing larger and stops new clots from forming in the blood vessels or heart."
                            },
                            {
                                "brand": "Glycomet 500 mg",
                                "generic": "metformin",
                                "dosage": "1 tablet twice daily before meals (morning & night)",
                                "purpose": "Blood sugar regulation for managing Type 2 Diabetes.",
                                "benefits": "Improves insulin sensitivity, decreases the amount of sugar absorbed from your food, and lowers the amount of sugar produced by your liver, keeping blood glucose levels stable."
                            },
                            {
                                "brand": "Lipvas 10 mg",
                                "generic": "atorvastatin",
                                "dosage": "1 tablet at bedtime",
                                "purpose": "Lowers high cholesterol and protects cardiovascular health.",
                                "benefits": "Works in the liver to block the enzyme responsible for producing cholesterol. This lowers 'bad' LDL cholesterol and triglycerides while raising 'good' HDL cholesterol, preventing plaque buildup in arteries."
                            }
                        ],
                        "english_explanation": [
                            "Ecosprin 75 mg (aspirin): A blood thinner taken once daily after lunch to prevent heart attacks and strokes.",
                            "Warfarin 5 mg (warfarin): A blood thinner taken once daily at 9:00 PM to treat or prevent blood clots.",
                            "Glycomet 500 mg (metformin): A blood sugar regulator taken twice daily before meals (morning & night) to manage Type 2 Diabetes.",
                            "Lipvas 10 mg (atorvastatin): A cholesterol-lowering medication taken once daily at bedtime to protect cardiovascular health."
                        ],
                        "what_to_watch_out_for": [
                            "Bleeding Risk: Ecosprin (Aspirin) and Warfarin are both blood thinners. Using them together dramatically increases the risk of internal bleeding. Monitor for unusual bruising, nosebleeds, or dark stools.",
                            "Diabetes check: Monitor your blood sugar regularly while on Glycomet.",
                            "Take Lipvas at bedtime as cholesterol synthesis peaks during sleep."
                        ]
                    }
                else:
                    # 1. OCR and analysis using Gemini
                    st.write("🔍 Running Gemini Vision OCR & Medicine extraction (with single-pass translation)...")
                    try:
                        analysis = analyze_prescription_image(image, lang_selection)
                    except Exception as e:
                        st.error(f"Failed to analyze image: {e}")
                        st.stop()
                    
                # 2. Interactions Graph Check
                st.write("🕸️ Performing NetworkX GraphRAG drug-drug interaction audit...")
                extracted_meds = []
                meds_table_data = []
                
                for item in analysis.get("medications", []):
                    brand_name = item.get("brand", "N/A")
                    generic_name = item.get("generic", "N/A")
                    extracted_meds.append(brand_name)
                    extracted_meds.append(generic_name)
                    
                    meds_table_data.append({
                        "brand": brand_name,
                        "generic": generic_name,
                        "dosage": item.get("dosage", "N/A"),
                        "purpose": item.get("purpose", "N/A"),
                        "benefits": item.get("benefits", item.get("purpose", "N/A"))
                    })
                    
                # Check conflicts using generic names
                generic_only = [med.get("generic") for med in meds_table_data if med.get("generic")]
                detected_interactions = check_drug_interactions(generic_only)
                
                # 3. Compile explanation
                eng_list = analysis.get('english_explanation', [])
                watch_list = analysis.get('what_to_watch_out_for', [])
                
                if isinstance(eng_list, list):
                    eng_formatted = "\n".join([f"{idx}. {item}" for idx, item in enumerate(eng_list, 1)])
                else:
                    eng_formatted = str(eng_list)
                    
                if isinstance(watch_list, list):
                    watch_formatted = "\n".join([f"- {item}" for item in watch_list])
                else:
                    watch_formatted = str(watch_list)
                    
                full_eng_explanation = f"{eng_formatted}\n\n**Things to watch out for:**\n{watch_formatted}"
                
                # 4. Translation
                # Prioritize Gemini's high-quality single-pass translation which preserves English brand/generic names.
                # Only run translate_explanation (Sarvam/Fallback) if the translation is missing, or if we are in demo mode.
                translated_expl = ""
                if not use_demo:
                    translated_list = analysis.get("translated_explanation", [])
                    if isinstance(translated_list, list) and translated_list:
                        translated_expl = "\n".join([f"{idx}. {item}" for idx, item in enumerate(translated_list, 1)])
                    elif isinstance(translated_list, str):
                        translated_expl = translated_list.strip()
                
                if not translated_expl:
                    sarvam_key = os.environ.get("SARVAM_API_KEY", "").strip()
                    if sarvam_key:
                        st.write(f"🗣️ Translating medical explanation to {lang_selection} using Sarvam AI...")
                        translated_expl = translate_explanation(full_eng_explanation, lang_selection)
                    else:
                        st.write(f"🗣️ Translating medical explanation to {lang_selection}...")
                        if use_demo:
                            # Translate the mock summary on the fly if key is present, otherwise show English
                            if GEMINI_API_KEY:
                                translated_expl = translate_explanation(full_eng_explanation, lang_selection)
                            else:
                                translated_expl = f"[Demo Translation Mode - API Key Missing. Showing English]:\n\n" + full_eng_explanation
                        else:
                            translated_expl = translate_explanation(full_eng_explanation, lang_selection)
                
                # 5. Save in database (Qdrant)
                st.write("💾 Storing record in Qdrant database...")
                presc_id = save_prescription(
                    user_id=user["id"],
                    image_name=img_name,
                    extracted_text=json.dumps(analysis),
                    raw_meds=meds_table_data,
                    explanation=full_eng_explanation,
                    lang_code=lang_selection,
                    translated_explanation=translated_expl
                )
                
                st.success("Analysis complete and saved privately to your history!")
                
                # Setup session state and reload page to view details
                saved_item = {
                    "id": presc_id,
                    "user_id": user["id"],
                    "image_name": img_name,
                    "extracted_text": json.dumps(analysis),
                    "raw_meds": meds_table_data,
                    "explanation": full_eng_explanation,
                    "lang_code": lang_selection,
                    "translated_explanation": translated_expl,
                    "timestamp": datetime.now().isoformat()
                }
                st.session_state.selected_prescription = saved_item
                st.rerun()

# --- Global Footer ---
st.markdown("---")
st.markdown("<p style='text-align: center; color: gray; font-size: 0.8rem;'>RxMate 💊 © 2026. Made with ❤️ to simplify health access across India.</p>", unsafe_allow_html=True)
