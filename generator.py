import os
import requests
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from translator import LANGUAGES
import streamlit as st
import re

def wrap_english_text(text):
    """
    Finds sequences containing Latin characters (along with numbers, spaces, and punctuation)
    and wraps them in a <font name='Helvetica'>...</font> tag to ensure they render properly
    in ReportLab even when using a regional font.
    """
    # Escape XML characters to prevent parsing errors in ReportLab Paragraph
    escaped_text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    pattern = r'([A-Za-z0-9\s\(\)\[\]\-\:\,\.\+\/\*]*[A-Za-z][A-Za-z0-9\s\(\)\[\]\-\:\,\.\+\/\*]*)'
    return re.sub(pattern, r"<font name='Helvetica'>\1</font>", escaped_text)

# Fonts path
FONTS_DIR = "c:/genai/apps/prescimate/fonts"
os.makedirs(FONTS_DIR, exist_ok=True)

# Map languages to font URLs (using verified, working googlefonts/noto-fonts repository links)
LANGUAGE_FONTS = {
    "Hindi": {
        "name": "NotoSansDevanagari",
        "file": "NotoSansDevanagari-Regular-Full.ttf",
        "url": "https://github.com/google/fonts/raw/main/ofl/notosansdevanagari/NotoSansDevanagari-Regular.ttf"
    },
    "Marathi": {
        "name": "NotoSansDevanagari",
        "file": "NotoSansDevanagari-Regular-Full.ttf",
        "url": "https://github.com/google/fonts/raw/main/ofl/notosansdevanagari/NotoSansDevanagari-Regular.ttf"
    },
    "Tamil": {
        "name": "NotoSansTamil",
        "file": "NotoSansTamil-Regular-Full.ttf",
        "url": "https://github.com/google/fonts/raw/main/ofl/notosanstamil/NotoSansTamil-Regular.ttf"
    },
    "Bengali": {
        "name": "NotoSansBengali",
        "file": "NotoSansBengali-Regular-Full.ttf",
        "url": "https://github.com/google/fonts/raw/main/ofl/notosansbengali/NotoSansBengali-Regular.ttf"
    },
    "Telugu": {
        "name": "NotoSansTelugu",
        "file": "NotoSansTelugu-Regular-Full.ttf",
        "url": "https://github.com/google/fonts/raw/main/ofl/notosanstelugu/NotoSansTelugu-Regular.ttf"
    },
    "Gujarati": {
        "name": "NotoSansGujarati",
        "file": "NotoSansGujarati-Regular-Full.ttf",
        "url": "https://github.com/google/fonts/raw/main/ofl/notosansgujarati/NotoSansGujarati-Regular.ttf"
    },
    "Kannada": {
        "name": "NotoSansKannada",
        "file": "NotoSansKannada-Regular-Full.ttf",
        "url": "https://github.com/google/fonts/raw/main/ofl/notosanskannada/NotoSansKannada-Regular.ttf"
    },
    "Malayalam": {
        "name": "NotoSansMalayalam",
        "file": "NotoSansMalayalam-Regular-Full.ttf",
        "url": "https://github.com/google/fonts/raw/main/ofl/notosansmalayalam/NotoSansMalayalam-Regular.ttf"
    },
    "Odia": {
        "name": "NotoSansOriya",
        "file": "NotoSansOriya-Regular-Full.ttf",
        "url": "https://github.com/google/fonts/raw/main/ofl/notosansoriya/NotoSansOriya-Regular.ttf"
    },
    "Punjabi": {
        "name": "NotoSansGurmukhi",
        "file": "NotoSansGurmukhi-Regular-Full.ttf",
        "url": "https://github.com/google/fonts/raw/main/ofl/notosansgurmukhi/NotoSansGurmukhi-Regular.ttf"
    },
    "Assamese": {
        "name": "NotoSansBengali",
        "file": "NotoSansBengali-Regular-Full.ttf",
        "url": "https://github.com/google/fonts/raw/main/ofl/notosansbengali/NotoSansBengali-Regular.ttf"
    },
    "Urdu": {
        "name": "NotoNastaliqUrdu",
        "file": "NotoNastaliqUrdu-Regular-Full.ttf",
        "url": "https://github.com/google/fonts/raw/main/ofl/notonastaliqurdu/NotoNastaliqUrdu-Regular.ttf"
    }
}

@st.cache_resource
def get_registered_font(lang_name):
    """
    Downloads and registers the TrueType font for the target language.
    Falls back to 'Helvetica' if the download or registration fails.
    """
    if lang_name not in LANGUAGE_FONTS:
        return "Helvetica"
        
    font_info = LANGUAGE_FONTS[lang_name]
    font_name = font_info["name"]
    font_file = font_info["file"]
    font_url = font_info["url"]
    
    font_path = os.path.join(FONTS_DIR, font_file)
    
    # Download font if not already present
    if not os.path.exists(font_path):
        try:
            print(f"Downloading {font_name} font for {lang_name}...")
            response = requests.get(font_url, timeout=15)
            response.raise_for_status()
            with open(font_path, "wb") as f:
                f.write(response.content)
            print(f"Font downloaded successfully.")
        except Exception as e:
            print(f"Failed to download font {font_name}: {e}")
            return "Helvetica"
            
    # Register font in ReportLab
    try:
        pdfmetrics.registerFont(TTFont(font_name, font_path))
        return font_name
    except Exception as e:
        print(f"Failed to register font {font_name}: {e}")
        return "Helvetica"

def add_header_footer(canvas, doc):
    """Add a running footer with medical disclaimer and page numbers."""
    canvas.saveState()
    canvas.setFont("Helvetica-Bold", 8)
    canvas.setFillColor(colors.HexColor("#b30000")) # Medical red
    canvas.drawString(36, 45, "MEDICAL DISCLAIMER: PresciMate is an AI assistant, NOT a substitute for professional medical advice.")
    canvas.setFont("Helvetica-Oblique", 7.5)
    canvas.setFillColor(colors.HexColor("#555555"))
    canvas.drawString(36, 32, "This document is for educational/informational use only. Always consult your doctor before starting or changing medications.")
    
    # Page number
    canvas.setFont("Helvetica", 9)
    canvas.drawRightString(doc.pagesize[0] - 36, 32, f"Page {doc.page}")
    canvas.restoreState()

def generate_pdf_explanation(filepath, username, image_name, date_str, medicines_table_data, english_expl, target_lang, translated_expl, interactions, date_of_visit="N/A"):
    """Generates a beautifully structured PDF document containing the prescription details and translations."""
    
    # Establish document template
    doc = SimpleDocTemplate(
        filepath,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=54,
        bottomMargin=72
    )
    
    # Get styles
    styles = getSampleStyleSheet()
    
    # Get registered fonts
    registered_font = get_registered_font(target_lang)
    
    # Custom Palette
    primary_color = colors.HexColor("#0f4c5c") # Deep teal
    secondary_color = colors.HexColor("#e36414") # Warm orange
    accent_color = colors.HexColor("#fb8b24")
    dark_text = colors.HexColor("#2f3e46")
    bg_light = colors.HexColor("#f8f9fa")
    
    # Custom styles
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=22,
        leading=26,
        textColor=primary_color,
        spaceAfter=12
    )
    
    subtitle_style = ParagraphStyle(
        'DocSub',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#5f7d95"),
        spaceAfter=20
    )
    
    h2_style = ParagraphStyle(
        'SectionHeader',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=18,
        textColor=primary_color,
        spaceBefore=15,
        spaceAfter=8,
        keepWithNext=True
    )
    
    body_style = ParagraphStyle(
        'BodyTextCustom',
        parent=styles['BodyText'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=dark_text,
        spaceAfter=8
    )
    
    table_header_style = ParagraphStyle(
        'TableHeaderText',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=13,
        textColor=colors.white
    )
    
    table_body_style = ParagraphStyle(
        'TableBodyText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=12,
        textColor=dark_text
    )
    
    translation_body_style = ParagraphStyle(
        'TranslationBodyText',
        parent=styles['BodyText'],
        fontName=registered_font,
        fontSize=10,
        leading=15,
        textColor=dark_text,
        spaceAfter=8
    )
    
    warning_header_style = ParagraphStyle(
        'WarningHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=15,
        textColor=colors.HexColor("#b30000"),
        spaceAfter=4
    )
    
    warning_body_style = ParagraphStyle(
        'WarningBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor("#7a0000")
    )
    
    story = []
    
    # --- Title & Metadata ---
    story.append(Paragraph("RxMate 💊 — Prescription Analysis", title_style))
    story.append(Paragraph(f"Patient Name: {username} | Date of Visit: {date_of_visit} | Analysis report generated: {date_str} | Source File: {image_name}", subtitle_style))
    
    # --- Section: Extracted Medicines Table ---
    story.append(Paragraph("Detected Medications", h2_style))
    
    table_content = [[
        Paragraph("<b>No.</b>", table_header_style),
        Paragraph("<b>Medicine / Brand Name</b>", table_header_style),
        Paragraph("<b>Active Ingredient</b>", table_header_style),
        Paragraph("<b>Dosage & Frequency</b>", table_header_style),
        Paragraph("<b>Health Benefits</b>", table_header_style)
    ]]
    for idx, med in enumerate(medicines_table_data, 1):
        table_content.append([
            Paragraph(str(idx), table_body_style),
            Paragraph(med.get("brand", "N/A"), table_body_style),
            Paragraph(med.get("generic", "N/A"), table_body_style),
            Paragraph(med.get("dosage", "N/A"), table_body_style),
            Paragraph(med.get("benefits", med.get("purpose", "N/A")), table_body_style)
        ])
        
    meds_table = Table(table_content, colWidths=[30, 110, 100, 120, 163])
    meds_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), primary_color),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BACKGROUND', (0, 1), (-1, -1), bg_light),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, bg_light]),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(meds_table)
    story.append(Spacer(1, 15))
    
    # --- Section: Drug Interactions (If Any) ---
    if interactions:
        story.append(Paragraph("⚠️ Flagged Drug Interactions", h2_style))
        for item in interactions:
            int_content = [
                [
                    Paragraph(f"<b>{item['severity']} Interaction</b>: {item['drug_a']} ({item['generic_a']}) + {item['drug_b']} ({item['generic_b']})", warning_header_style)
                ],
                [
                    Paragraph(item['description'], warning_body_style)
                ]
            ]
            int_table = Table(int_content, colWidths=[522])
            int_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#fff0f0")), # Light pink background
                ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#ffcccc")),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('LEFTPADDING', (0, 0), (-1, -1), 12),
                ('RIGHTPADDING', (0, 0), (-1, -1), 12),
            ]))
            story.append(int_table)
            story.append(Spacer(1, 10))
        story.append(Spacer(1, 10))
        
    # --- Section: English Plain Explanation ---
    story.append(Paragraph("Explanation (English)", h2_style))
    for line in english_expl.split('\n'):
        if line.strip():
            escaped_line = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            story.append(Paragraph(escaped_line, body_style))
            
    story.append(Spacer(1, 15))
    
    # --- Section: Translated Explanation ---
    story.append(Paragraph(f"Explanation in {target_lang} ({LANGUAGES.get(target_lang, {}).get('native', '')})", h2_style))
    
    # Check if we successfully got a Unicode font
    is_unicode = registered_font != "Helvetica"
    
    if not is_unicode:
        # Fallback explanation warning in English
        story.append(Paragraph(
            "<i>Note: Local font installation is incomplete. Generating plain-language translation below (may require correct device unicode support to read directly):</i>",
            body_style
        ))
        
    for line in translated_expl.split('\n'):
        if line.strip():
            processed_line = wrap_english_text(line)
            story.append(Paragraph(processed_line, translation_body_style))
            
    # Build document
    doc.build(story, onFirstPage=add_header_footer, onLaterPages=add_header_footer)
