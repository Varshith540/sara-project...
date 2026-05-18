import json
from django.test import TestCase
from unittest.mock import patch, MagicMock
from core.interview_evaluator import evaluate_interview_answer

class InterviewEvaluatorTestCase(TestCase):
    @patch('core.interview_evaluator.genai.Client')
    @patch('core.interview_evaluator.settings')
    def test_evaluate_answer_success(self, mock_settings, mock_genai_client):
        """Test a successful score and feedback extraction."""
        mock_settings.GEMINI_API_KEY = "test_key_123"
        
        mock_client_instance = MagicMock()
        mock_genai_client.return_value = mock_client_instance
        
        mock_response = MagicMock()
        mock_response.text = '```json\n{"score": 8, "feedback": "Great use of the STAR method!"}\n```'
        mock_client_instance.models.generate_content.return_value = mock_response

        result = evaluate_interview_answer("Tell me about a time you failed.", "I failed once but learned a lot and fixed it using the STAR method.")

        self.assertEqual(result["score"], 8)
        self.assertEqual(result["feedback"], "Great use of the STAR method!")

    def test_evaluate_answer_too_short(self):
        """Test that short answers bypass the API and return a default failure."""
        result = evaluate_interview_answer("Question", "no")
        self.assertEqual(result["score"], 0)
        self.assertIn("too short", result["feedback"])

    @patch('core.interview_evaluator.genai.Client')
    @patch('core.interview_evaluator.settings')
    def test_evaluate_answer_fallback_on_bad_json(self, mock_settings, mock_genai_client):
        """Test that invalid JSON hallucination triggers safe fallback."""
        mock_settings.GEMINI_API_KEY = "test_key_123"
        
        mock_client_instance = MagicMock()
        mock_genai_client.return_value = mock_client_instance
        
        mock_response = MagicMock()
        mock_response.text = 'I think they did a good job! 8 out of 10.' # No JSON
        mock_client_instance.models.generate_content.return_value = mock_response

        result = evaluate_interview_answer("Question", "Here is a decently long answer that should normally be evaluated correctly.")

        self.assertEqual(result["score"], 0)
        self.assertIn("AI error", result["feedback"])
