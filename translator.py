import os
import requests
import google.generativeai as genai

# Setup Gemini API
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# Dictionary mapping friendly language names to Sarvam AI language codes
LANGUAGES = {
    "Hindi": {"code": "hi-IN", "native": "हिन्दी"},
    "Tamil": {"code": "ta-IN", "native": "தமிழ்"},
    "Bengali": {"code": "bn-IN", "native": "বাংলা"},
    "Telugu": {"code": "te-IN", "native": "తెలుగు"},
    "Marathi": {"code": "mr-IN", "native": "मराठी"},
    "Gujarati": {"code": "gu-IN", "native": "ગુજરાતી"},
    "Kannada": {"code": "kn-IN", "native": "ಕನ್ನಡ"},
    "Malayalam": {"code": "ml-IN", "native": "മലയാളம்"},
    "Odia": {"code": "or-IN", "native": "ଓଡ଼ିଆ"},
    "Punjabi": {"code": "pa-IN", "native": "ਪੰਜਾਬੀ"},
    "Assamese": {"code": "as-IN", "native": "অসমীয়া"},
    "Urdu": {"code": "ur-IN", "native": "اردو"}
}

def translate_via_gemini(text: str, target_lang_name: str) -> str:
    """Translate text using Gemini as a high-quality fallback."""
    if not GEMINI_API_KEY:
        return f"[Translation Error: Gemini API key missing] {text}"
        
    try:
        model = genai.GenerativeModel("gemini-3.5-flash")
        prompt = f"""You are an expert translator specializing in medical communications for Indian patients.
Translate the following prescription analysis and warning notes into {target_lang_name}.

Translation guidelines:
1. Make it sound simple, clear, and natural to a person living in a rural area or small town in India.
2. Keep ALL medicine brand names and generic names (e.g. TRESIBA, HUMINSULIN R, SEMASIZE) in English script or in brackets (e.g. Tresiba (degludec)) so patients can recognize the packaging. Do not translate or omit them.
3. Keep the tone compassionate, helpful, and clear.

Text to translate:
{text}

Translation:"""
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"[Gemini translation failed: {str(e)}]\n\n{text}"

def translate_via_sarvam(text: str, target_lang_code: str, api_key: str) -> str:
    """Translate text using Sarvam AI translation API."""
    url = "https://api.sarvam.ai/translate"
    headers = {
        "api-subscription-key": api_key,
        "Content-Type": "application/json"
    }
    payload = {
        "input": text,
        "source_language_code": "en-IN",
        "target_language_code": target_lang_code,
        "speaker_gender": "MALE",
        "mode": "formal"
    }
    
    response = requests.post(url, json=payload, headers=headers, timeout=12)
    response.raise_for_status()
    data = response.json()
    return data.get("translated_text", "")

def translate_explanation(text: str, target_language_name: str) -> str:
    """
    Translates the text into the target language.
    To ensure medical safety and preserve brand/generic names in English script inside brackets,
    we use Gemini's translation engine which is highly robust for mixed-script medical text.
    """
    if target_language_name not in LANGUAGES:
        return text # Return original English if not supported
        
    return translate_via_gemini(text, target_language_name)
