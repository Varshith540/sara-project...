import json
from django.test import TestCase
from unittest.mock import patch, MagicMock
from core.resume_parser import extract_structured_data, _clean_json_response

class StructuredParserTestCase(TestCase):
    def test_clean_json_response_with_markdown(self):
        """Test that the cleaner strips hallucinated markdown tags."""
        dirty_json = "```json\n{\n  \"personal_info\": {\"name\": \"Test User\"}\n}\n```"
        cleaned = _clean_json_response(dirty_json)
        # Should be parseable
        parsed = json.loads(cleaned)
        self.assertEqual(parsed["personal_info"]["name"], "Test User")

    def test_clean_json_response_with_conversational_text(self):
        """Test that the cleaner strips conversational text before and after the JSON."""
        dirty_json = "Here is the extracted data:\n```json\n{\"skills\": {\"technical\": [\"Python\"]}}\n```\nLet me know if you need anything else."
        cleaned = _clean_json_response(dirty_json)
        parsed = json.loads(cleaned)
        self.assertEqual(parsed["skills"]["technical"][0], "Python")

    @patch('core.resume_parser.genai.Client')
    @patch('core.resume_parser.settings')
    def test_extract_structured_data_success(self, mock_settings, mock_genai_client):
        """Test a successful structured data extraction."""
        mock_settings.GEMINI_API_KEY = "test_key_123"
        
        mock_client_instance = MagicMock()
        mock_genai_client.return_value = mock_client_instance
        
        mock_response = MagicMock()
        mock_response.text = '```json\n{"personal_info": {"name": "Jane Doe", "email": "jane@example.com", "phone": "1234567890", "links": []}, "education": [], "skills": {"technical": ["Django"], "soft": []}, "experience": [], "projects": []}\n```'
        mock_client_instance.models.generate_content.return_value = mock_response

        raw_text = "Jane Doe | jane@example.com | 1234567890 | Skills: Django"
        result = extract_structured_data(raw_text)

        self.assertEqual(result["personal_info"]["name"], "Jane Doe")
        self.assertIn("Django", result["skills"]["technical"])
        
    @patch('core.resume_parser.genai.Client')
    @patch('core.resume_parser.settings')
    def test_extract_structured_data_fallback(self, mock_settings, mock_genai_client):
        """Test that invalid JSON falls back to the default schema safely."""
        mock_settings.GEMINI_API_KEY = "test_key_123"
        
        mock_client_instance = MagicMock()
        mock_genai_client.return_value = mock_client_instance
        
        mock_response = MagicMock()
        # Missing closing brace
        mock_response.text = '{"personal_info": {"name": "Jane Doe"'
        mock_client_instance.models.generate_content.return_value = mock_response

        result = extract_structured_data("Some raw text")

        self.assertEqual(result["personal_info"]["name"], "") # Should be default schema
        self.assertIsInstance(result["skills"], dict)
        self.assertIsInstance(result["experience"], list)
