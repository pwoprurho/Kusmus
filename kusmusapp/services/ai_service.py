import os
import json
import logging
import requests
import google.generativeai as genai
from datetime import datetime
from gtts import gTTS
import uuid
from .key_manager import key_manager

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AIService:
    def __init__(self):
        # Use KeyManager to get the current valid key
        self.gemini_key = key_manager.get_current_key()
        self.ltx_key = os.getenv('LTX_API_KEY')
        
        if self.gemini_key and "placeholder" not in self.gemini_key:
            genai.configure(api_key=self.gemini_key)
            self.model = genai.GenerativeModel('gemini-2.5-flash')
        else:
            self.model = None
            logger.warning("Gemini API Key is missing or invalid.")

    def _generate_with_retry(self, prompt, is_json=False):
        """Helper to generate content with key rotation and retry logic."""
        if not self.model:
            raise Exception("AI Model not initialized")

        max_retries = 5
        attempts = 0
        
        while attempts < max_retries:
            try:
                # Ensure we are using the current key
                current_key = key_manager.get_current_key()
                genai.configure(api_key=current_key)
                
                response = self.model.generate_content(prompt)
                return response
            except Exception as e:
                logger.error(f"Generation attempt {attempts+1} failed: {e}")
                if "429" in str(e) or "Quota" in str(e):
                    logger.info("Quota exceeded, rotating key...")
                    key_manager.rotate_key()
                    attempts += 1
                else:
                    # For other errors, maybe rotating won't help but we can try once or twice
                    if attempts < 2:
                         attempts += 1
                    else:
                         raise e
        
        raise Exception("All API keys exhausted or max retries reached.")

    def generate_roadmap(self, ambition, hours):
        """
        Generates a structured roadmap using Gemini.
        Returns a JSON object or structured dict.
        """
        if not self.model:
            return self._mock_roadmap(ambition)

        prompt = f"""
        Act as an expert educational curriculum designer.
        Create a detailed, step-by-step learning roadmap for a student whose ambition is: '{ambition}'.
        They can study for {hours} hours per day.
        
        Return the response strictly as valid JSON with the following structure:
        {{
            "goal": "{ambition}",
            "steps": [
                {{
                    "step_number": 1,
                    "title": "Step Title",
                    "description": "Detailed description of what to learn.",
                    "youtube_queries": ["search query 1", "search query 2"]
                }}
            ]
        }}
        Do not include markdown formatting like ```json. Just raw JSON.
        """
        
        try:
            response = self._generate_with_retry(prompt)
            # clean up potential markdown formatting
            text = response.text.replace('```json', '').replace('```', '').strip()
            return json.loads(text)
        except Exception as e:
            logger.error(f"Gemini Roadmap Generation Failed: {e}")
            return self._mock_roadmap(ambition)

    def generate_banner(self, ambition):
        """Generates a banner image URL using Gemini (or returns a placeholder)."""
        if not self.model:
            return "https://via.placeholder.com/1200x300?text=Roadmap+Banner"
            
        try:
            # Placeholder logic preserved as per original code
             return "https://via.placeholder.com/1200x300?text=" + ambition.replace(" ", "+")
        except Exception as e:
            logger.error(f"Banner generation failed: {e}")
            return "https://via.placeholder.com/1200x300?text=Roadmap"

    def generate_lecture_content(self, title, description):
        """Generates a detailed detailed text lecture for a step."""
        if not self.model:
            return f"Mock Lecture for {title}: {description} (AI not configured)"
            
        prompt = f"""
        Write a comprehensive, engaging educational lecture for the topic: '{title}'.
        Context: {description}.
        Structure:
        1. Introduction
        2. Key Concepts (explain in detail)
        3. Real-world Examples
        4. Summary
        Format using Markdown.
        """
        try:
            response = self._generate_with_retry(prompt)
            return response.text
        except Exception as e:
            logger.error(f"Lecture generation failed: {e}")
            return f"Could not generate lecture. Error: {e}"

    def generate_audio_explanation(self, text, output_dir):
        """Generates audio from text using gTTS and saves to output_dir."""
        try:
            # Clean text for audio (remove markdown symbols roughly)
            clean_text = text.replace('#', '').replace('*', '')
            
            tts = gTTS(text=clean_text, lang='en')
            filename = f"lecture_{uuid.uuid4().hex}.mp3"
            filepath = os.path.join(output_dir, filename)
            tts.save(filepath)
            return filename
        except Exception as e:
            logger.error(f"Audio generation failed: {e}")
            return None

    def _mock_roadmap(self, ambition):
        """Fallback mock roadmap if AI fails."""
        return {
            "goal": ambition,
            "steps": [
                {
                    "step_number": 1,
                    "title": f"Introduction to {ambition}",
                    "description": "Learn the basics and fundamental concepts.",
                    "youtube_queries": [f"{ambition} tutorial for beginners"]
                },
                {
                    "step_number": 2,
                    "title": "Advanced Concepts",
                    "description": "Deep dive into complex topics.",
                    "youtube_queries": [f"Advanced {ambition} techniques"]
                }
            ]
        }
