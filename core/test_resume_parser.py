import os
import io
from django.test import TestCase
from unittest.mock import patch, MagicMock

# Import the module we want to test
from core import resume_parser

class ResumeParserGeminiTestCase(TestCase):
    def setUp(self):
        # Create a dummy PDF file in memory/disk to simulate upload
        self.dummy_pdf_path = "dummy_test_resume.pdf"
        with open(self.dummy_pdf_path, "wb") as f:
            f.write(b"%PDF-1.4 dummy content")
            
    def tearDown(self):
        if os.path.exists(self.dummy_pdf_path):
            os.remove(self.dummy_pdf_path)

    @patch('core.resume_parser.genai.Client')
    @patch('core.resume_parser.settings')
    @patch('core.resume_parser.fitz')
    @patch('core.resume_parser.pdfplumber')
    @patch('core.resume_parser.PyPDF2')
    def test_gemini_native_pdf_fallback(self, mock_pypdf2, mock_pdfplumber, mock_fitz, mock_settings, mock_genai_client):
        # Mock standard extractors to fail/return empty so it falls back to Gemini OCR
        mock_fitz.open.side_effect = Exception("PyMuPDF simulated failure")
        mock_pdfplumber.open.side_effect = Exception("pdfplumber simulated failure")
        mock_pypdf2.PdfReader.side_effect = Exception("PyPDF2 simulated failure")
        
        # Mock Django settings to have the API key
        mock_settings.GEMINI_API_KEY = "test_api_key_123"
        
        # Mock the Gemini client and its chained responses
        mock_client_instance = MagicMock()
        mock_genai_client.return_value = mock_client_instance
        
        # Mock file upload
        mock_uploaded_file = MagicMock()
        mock_client_instance.files.upload.return_value = mock_uploaded_file
        
        # Mock generation response
        mock_response = MagicMock()
        mock_response.text = "Extracted Text from Gemini OCR"
        mock_client_instance.models.generate_content.return_value = mock_response

        # Execute
        result = resume_parser.extract_text(self.dummy_pdf_path)
        
        # Verify
        self.assertEqual(result, "Extracted Text from Gemini OCR")
        
        # Ensure the fallback OCR Native File Upload was called
        mock_client_instance.files.upload.assert_called_once_with(file=self.dummy_pdf_path)
        mock_client_instance.models.generate_content.assert_called_once()
        
        args, kwargs = mock_client_instance.models.generate_content.call_args
        self.assertEqual(kwargs.get('model'), 'gemini-1.5-flash') # Or whatever model is used
        
        print("✅ Enhanced Test Passed: Gemini Native PDF OCR fallback executed perfectly.")
