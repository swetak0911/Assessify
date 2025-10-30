from typing import Any, Dict, List
from google import genai
from google.genai import types
from PIL import Image
from io import BytesIO

class GeminiImageGeneration:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = genai.Client(api_key=api_key)

    async def generate_images(
        self, 
        prompt: str, 
        model: str = 'imagen-3.0-generate-002',
        number_of_images: int = 4
    ) -> List[bytes]:
        """
        Generates images using Gemini's image generation API.
        
        Args:
            prompt (str): The prompt to generate images from
            model (str): The model to use for generation
            number_of_images (int): Number of images to generate
            
        Returns:
            List[bytes]: List of generated image bytes
        """
        try:
            response = self.client.models.generate_images(
                model=model,
                prompt=prompt,
                config=genai.types.GenerateImagesConfig(
                    number_of_images=number_of_images,
                )
            )
            return [img.image.image_bytes for img in response.generated_images]
        except Exception as e:
            raise Exception(f"Failed to generate images: {str(e)}")
