"""Tests for multi-language scheme localization, translation strategy, and cache isolation.

    pytest tests/test_localization.py -v
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from app import briefs, localization
from app.main import app
from app.profile import Profile

client = TestClient(app)

FARMER = Profile(
    age=45, gender="Male", state="Karnataka", residence="Rural",
    occupation="Farmer", annual_income=100000, land_acres=2,
    caste="Other Backward Class (OBC)", is_bpl=True,
    needs=["health insurance"],
)


# --------------------------------------------------------------------------- #
#  1. Localization Helpers & Formatting
# --------------------------------------------------------------------------- #
class TestLocalizationHelpers:
    def test_format_title_english(self):
        title = "Pradhan Mantri Kisan Samman Nidhi"
        formatted = localization.format_title(title, "PM-KISAN", "en")
        assert formatted == title

    def test_format_title_hindi_with_english_acronym(self):
        title = "प्रधानमंत्री किसान सम्मान निधि"
        formatted = localization.format_title(title, "PM-KISAN", "hi")
        assert formatted == "प्रधानमंत्री किसान सम्मान निधि (PM-KISAN)"

    def test_format_title_no_duplicate_parens(self):
        title = "प्रधानमंत्री किसान सम्मान निधि (PM-KISAN)"
        formatted = localization.format_title(title, "PM-KISAN", "hi")
        assert formatted == "प्रधानमंत्री किसान सम्मान निधि (PM-KISAN)"

    def test_format_title_other_languages(self):
        title_kn = "ಪ್ರಧಾನ ಮಂತ್ರಿ ಕಿಸಾನ್ ಸಮ್ಮಾನ್ ನಿಧಿ"
        formatted_kn = localization.format_title(title_kn, "PM-KISAN", "kn")
        assert formatted_kn == "ಪ್ರಧಾನ ಮಂತ್ರಿ ಕಿಸಾನ್ ಸಮ್ಮಾನ್ ನಿಧಿ (PM-KISAN)"

    def test_translate_why_state_reasons(self):
        assert localization.translate_why("A Karnataka state scheme", "hi") == "कर्नाटक राज्य की योजना"
        assert localization.translate_why("A Karnataka state scheme", "kn") == "ಕರ್ನಾಟಕ ರಾಜ್ಯದ ಯೋಜನೆ"
        assert localization.translate_why("A Karnataka state scheme", "ta") == "கர்நாடகா மாநில திட்டம்"
        assert localization.translate_why("A Karnataka state scheme", "en") == "A Karnataka state scheme"

    def test_translate_why_work_reasons(self):
        assert localization.translate_why("Matches your work: Farmer", "hi") == "आपके काम के लिए: किसान"
        assert localization.translate_why("For your work: Farmer", "ta") == "உங்கள் பணிக்காக: விவசாயி"
        assert localization.translate_why("Matches your work: Farmer", "kn") == "ನಿಮ್ಮ ಕೆಲಸಕ್ಕಾಗಿ: ರೈತ"
        assert localization.translate_why("Matches your work: Farmer", "en") == "Matches your work: Farmer"

    def test_translate_why_daughter_and_son_studies(self):
        assert localization.translate_why("For your daughter's studies", "hi") == "आपकी बेटी की पढ़ाई के लिए"
        assert localization.translate_why("For your son's studies", "hi") == "आपके बेटे की पढ़ाई के लिए"
        assert localization.translate_why("For your daughter's studies", "kn") == "ನಿಮ್ಮ ಮಗಳ ವ್ಯಾಸಂಗಕ್ಕಾಗಿ"

    def test_translate_why_basic_categories(self):
        assert localization.translate_why("For BPL card holders", "hi") == "बीपीएल (BPL) कार्ड धारकों के लिए"
        assert localization.translate_why("For students", "hi") == "विद्यार्थियों के लिए"
        assert localization.translate_why("For women", "hi") == "महिलाओं के लिए"
        assert localization.translate_why("For persons with disability", "hi") == "दिव्यांगजनों के लिए"

    def test_translate_document_names(self):
        assert "आधार कार्ड" in localization.translate_document("Aadhaar Card", "hi")
        assert "राशन कार्ड" in localization.translate_document("Ration Card", "hi")
        assert localization.translate_document("Aadhaar Card", "en") == "Aadhaar Card"

    def test_translate_apply_mode(self):
        assert localization.translate_mode("Online", "hi") == "ऑनलाइन"
        assert localization.translate_mode("Offline", "hi") == "ऑफलाइन"
        assert localization.translate_mode("Online", "en") == "Online"

    def test_verified_official_titles(self):
        assert localization.get_official_title("pm-kisan", "hi") is not None
        assert "किसान" in localization.get_official_title("pm-kisan", "hi")
        assert localization.get_official_title("ab-pmjay", "hi") is not None
        assert "आयुष्मान" in localization.get_official_title("ab-pmjay", "hi")


# --------------------------------------------------------------------------- #
#  2. Card Generation & Template Translation
# --------------------------------------------------------------------------- #
class TestCardLocalization:
    def test_template_with_native_translation(self):
        native_doc = {
            "slug": "pm-kisan",
            "name": "प्रधानमंत्री किसान सम्मान निधि",
            "official_name": "Pradhan Mantri Kisan Samman Nidhi",
            "has_native": True,
            "source_language": "hi",
            "brief": "किसानों को वित्तीय सहायता",
            "benefits": "₹6,000 प्रति वर्ष",
            "eligibility": "भूमिधारक किसान",
            "documents": ["Aadhaar Card", "Bank Passbook"],
            "apply": [{"mode": "Online", "steps": "पोर्टल पर आवेदन करें"}],
        }
        b = briefs._template(native_doc, "hi")
        assert b.benefit == "₹6,000 प्रति वर्ष"
        assert "आधार" in b.documents[0]
        assert "ऑनलाइन" in b.how_to_apply

    def test_template_with_english_only_source_records(self):
        english_only_doc = {
            "slug": "custom-scheme",
            "name": "Custom Rural Scheme",
            "official_name": "Custom Rural Scheme",
            "has_native": False,
            "source_language": "en",
            "brief": "Financial support for rural residents",
            "benefits": "Rs 5,000 one-time grant",
            "eligibility": "Rural residents below poverty line",
            "documents": ["Aadhaar Card", "Ration Card"],
            "apply": [{"mode": "Offline", "steps": "Visit Gram Panchayat office"}],
        }
        b = briefs._template(english_only_doc, "hi")
        # Documents and application mode should be translated to help the user navigate
        assert any("आधार" in d for d in b.documents)
        assert any("राशन" in d for d in b.documents)
        assert "ऑफलाइन" in b.how_to_apply
        # Facts like monetary amount and steps are accurately preserved without hallucinations
        assert "5,000" in b.benefit or "grant" in b.benefit

    def test_cache_isolation_by_language(self):
        briefs._cache.clear()
        mock_en_detail = {
            "slug": "test-scheme",
            "name": "Test Scheme",
            "official_name": "Test Scheme",
            "has_native": False,
            "source_language": "en",
            "brief": "English description",
            "benefits": "English benefit Rs 1000",
            "documents": ["Aadhaar Card"],
            "apply": [{"mode": "Online"}],
        }
        mock_hi_detail = {
            "slug": "test-scheme",
            "name": "परीक्षण योजना",
            "official_name": "Test Scheme",
            "has_native": True,
            "source_language": "hi",
            "brief": "हिंदी विवरण",
            "benefits": "₹1000 लाभ",
            "documents": ["Aadhaar Card"],
            "apply": [{"mode": "Online"}],
        }

        async def fake_detail(slug, lang="en"):
            return mock_hi_detail if lang == "hi" else mock_en_detail

        with patch("app.scraper.detail", side_effect=fake_detail), \
             patch("app.llm.generate", side_effect=RuntimeError("offline")):
            import asyncio
            card_en = asyncio.run(briefs.card("test-scheme", language="en"))
            card_hi = asyncio.run(briefs.card("test-scheme", language="hi"))

            assert card_en.brief.benefit == "English benefit Rs 1000"
            assert card_hi.brief.benefit == "₹1000 लाभ"
            # Keys in briefs._cache must be distinct
            assert ("test-scheme", "en", "") in briefs._cache
            assert ("test-scheme", "hi", "") in briefs._cache
            assert briefs._cache[("test-scheme", "en", "")].brief.benefit != briefs._cache[("test-scheme", "hi", "")].brief.benefit


# --------------------------------------------------------------------------- #
#  3. API Endpoints: /api/schemes/match and /api/schemes/{slug}/card
# --------------------------------------------------------------------------- #
class TestApiEndpoints:
    def test_match_endpoint_hindi(self):
        # Mock matcher.find_schemes to return controlled schemes
        mock_search_result = {
            "total": 2,
            "schemes": [
                {
                    "slug": "pm-kisan",
                    "name": "प्रधानमंत्री किसान सम्मान निधि (PM-KISAN)",
                    "official_name": "Pradhan Mantri Kisan Samman Nidhi",
                    "short_title": "PM Kisan",
                    "brief": "किसानों को प्रति वर्ष ₹6,000 की वित्तीय सहायता।",
                    "category": "farming",
                    "score": 100,
                    "why": ["आपके काम के लिए: किसान", "कर्नाटक राज्य की योजना"],
                },
                {
                    "slug": "ab-pmjay",
                    "name": "आयुष्मान भारत - प्रधानमंत्री जन आरोग्य योजना (AB-PMJAY)",
                    "official_name": "Ayushman Bharat PM-JAY",
                    "short_title": "Ayushman Bharat",
                    "brief": "₹5 लाख तक का मुफ़्त स्वास्थ्य बीमा।",
                    "category": "health",
                    "score": 90,
                    "why": ["आपकी ज़रूरत के अनुसार: स्वास्थ्य बीमा"],
                },
            ],
        }

        with patch("app.matcher.find_schemes", return_value=mock_search_result):
            resp = client.post("/api/schemes/match", json={
                "profile": FARMER.model_dump(),
                "language": "hi",
                "limit": 5,
            })
            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] == 2
            schemes = data["schemes"]
            assert len(schemes) == 2

            pm_kisan = schemes[0]
            assert "प्रधानमंत्री" in pm_kisan["name"]
            assert "किसान" in pm_kisan["why"][0]
            assert "कर्नाटक" in pm_kisan["why"][1]

    def test_match_endpoint_english(self):
        mock_search_result = {
            "total": 1,
            "schemes": [
                {
                    "slug": "pm-kisan",
                    "name": "Pradhan Mantri Kisan Samman Nidhi",
                    "official_name": "Pradhan Mantri Kisan Samman Nidhi",
                    "short_title": "PM Kisan",
                    "brief": "Income support of Rs 6,000 per year to farmer families.",
                    "category": "farming",
                    "score": 100,
                    "why": ["Matches your work: Farmer", "A Karnataka state scheme"],
                },
            ],
        }

        with patch("app.matcher.find_schemes", return_value=mock_search_result):
            resp = client.post("/api/schemes/match", json={
                "profile": FARMER.model_dump(),
                "language": "en",
                "limit": 5,
            })
            assert resp.status_code == 200
            data = resp.json()
            pm_kisan = data["schemes"][0]
            assert "Pradhan Mantri" in pm_kisan["name"]
            assert pm_kisan["why"][0] == "Matches your work: Farmer"
            assert pm_kisan["why"][1] == "A Karnataka state scheme"

    def test_card_endpoint_hindi_and_english(self):
        briefs._cache.clear()
        mock_detail = {
            "slug": "pm-kisan",
            "name": "प्रधानमंत्री किसान सम्मान निधि",
            "official_name": "Pradhan Mantri Kisan Samman Nidhi",
            "has_native": True,
            "source_language": "hi",
            "brief": "किसानों को वित्तीय सहायता",
            "benefits": "₹6,000 प्रति वर्ष",
            "documents": ["Aadhaar Card"],
            "apply": [{"mode": "Online"}],
            "url": "https://www.myscheme.gov.in/schemes/pm-kisan",
        }

        async def fake_detail(slug, lang="en"):
            return mock_detail

        with patch("app.scraper.detail", side_effect=fake_detail), \
             patch("app.llm.generate", side_effect=RuntimeError("offline")):
            resp = client.post("/api/schemes/pm-kisan/card", json={
                "language": "hi",
                "profile": FARMER.model_dump(),
            })
            assert resp.status_code == 200
            card = resp.json()
            assert card["slug"] == "pm-kisan"
            assert card["brief"]["benefit"] == "₹6,000 प्रति वर्ष"
            assert card["source_language"] == "hi"
            assert card["translation_status"] == "verified"
