import json
from django.conf import settings

def evaluate_interview_answer(question: str, transcribed_answer: str) -> dict:
    """
    Evaluates a user's spoken answer to an interview question using the Gemini API.
    Returns a strict JSON dictionary with a 'score' (0-10) and 'feedback' string.
    """
    default_response = {
        "score": 0,
        "feedback": "We couldn't evaluate your answer due to an AI error. Please try again."
    }
    
    if not transcribed_answer or len(transcribed_answer.strip()) < 10:
        return {
            "score": 0,
            "feedback": "Your answer was too short to evaluate. Please try providing more detail using the STAR method."
        }

    api_key = getattr(settings, 'GEMINI_API_KEY', '').strip()
    if not api_key or api_key == 'your_gemini_api_key_here':
        return {
            "score": 5,
            "feedback": "[Demo Mode] That was a solid answer, but consider being more specific. (Add GEMINI_API_KEY for real AI feedback)."
        }

    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        
        prompt = f"""
        You are an expert, empathetic Technical Recruiter conducting a mock interview.
        You asked the candidate the following question:
        "{question}"
        
        The candidate provided this spoken answer (transcribed via speech-to-text):
        "{transcribed_answer}"
        
        Evaluate the answer. Give it a score out of 10 based on clarity, relevance, completeness, and use of the STAR method (if applicable).
        Provide a short, constructive paragraph of feedback on how they can improve.
        
        You MUST return ONLY a valid JSON object following this EXACT schema. Do not add any markdown, comments, or conversational text.
        
        SCHEMA:
        {{
            "score": int,
            "feedback": "string"
        }}
        """
        
        response = client.models.generate_content(
            model='gemini-1.5-flash',
            contents=[prompt]
        )
        
        # Clean potential markdown tags
        cleaned = response.text.strip()
        if cleaned.startswith("```json"): cleaned = cleaned[7:]
        elif cleaned.startswith("```"): cleaned = cleaned[3:]
        if cleaned.endswith("```"): cleaned = cleaned[:-3]
        
        start_idx = cleaned.find('{')
        end_idx = cleaned.rfind('}')
        if start_idx != -1 and end_idx != -1:
            cleaned = cleaned[start_idx:end_idx+1]
            
        data = json.loads(cleaned)
        
        # Validate schema
        score = data.get("score", 0)
        feedback = data.get("feedback", "No feedback provided.")
        
        return {
            "score": score,
            "feedback": feedback
        }
        
    except json.JSONDecodeError as je:
        print(f"[InterviewEvaluator] JSON Parse Error: {je}")
        return default_response
    except Exception as e:
        print(f"[InterviewEvaluator] Extraction Error: {e}")
        return default_response
