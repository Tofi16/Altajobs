# ---------------------------------------------------------------------------
# REPLACE this single existing line:
#     CV_PREMIUM_PRICE = 50                     # "Banana AI" premium CV (with photo) ვVERTINE - ከዋሌት ሲቀነስ
# WITH the block below (tiered pricing replaces the old flat price).
# ---------------------------------------------------------------------------

CV_TIERS = {
    "standard": {
        "label": "Standard CV",
        "price": 200,
        "cover_letter": False,
        "priority_badge": False,
    },
    "premium": {
        "label": "Premium CV",
        "price": 350,
        "cover_letter": True,
        "priority_badge": False,
    },
    "vip": {
        "label": "VIP CV",
        "price": 500,
        "cover_letter": True,
        "priority_badge": True,
    },
}

CV_TEMPLATES = {
    "classic": {"label": "Classic", "accent": "#00c853", "layout": "single-column"},
    "modern":  {"label": "Modern",  "accent": "#2ECC71", "layout": "sidebar"},
    "bold":    {"label": "Bold",    "accent": "#0a7a3c", "layout": "banner"},
}

# ---------------------------------------------------------------------------
# ADD this near ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
# ---------------------------------------------------------------------------

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-1.5-flash"
GEMINI_ENDPOINT = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
)
