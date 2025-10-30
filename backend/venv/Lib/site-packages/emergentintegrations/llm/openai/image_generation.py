import asyncio
import os
from typing import List, Dict
from litellm import image_generation
import base64
import requests

class OpenAIImageGeneration:
    def __init__(self, api_key: str, custom_headers: Dict[str, str] = None):
        self.api_key = api_key
        proxy_url = os.getenv("INTEGRATION_PROXY_URL")
        if not proxy_url:
            proxy_url = "https://integrations.emergentagent.com"
        self.emergent_proxy_url = proxy_url + "/llm"
        self.custom_headers = custom_headers or {}
        
        app_url = os.getenv('APP_URL')
        # if app_url:
        #     self.custom_headers['X-App-ID'] = app_url

    def _is_emergent_key(self, api_key):
        return api_key.startswith("sk-emergent-")

    async def generate_images(
        self,
        prompt: str,
        model: str = "gpt-image-1",
        number_of_images: int = 1,
        quality: str = "low"
    ) -> List[bytes]:
        """
        Generates images using OpenAI's image generation API via LiteLLM.
        
        Args:
            prompt (str): The prompt to generate images from
            model (str): The model to use for generation
            number_of_images (int): Number of images to generate
            quality (str): The quality of the image ("low", "standard", "hd")
            
        Returns:
            List[bytes]: List of generated image bytes
        """
        try:
            # Convert quality for different models
            if model == "dall-e-3":
                if quality in ["low", "medium"]:
                    quality = "standard"
                elif quality == "high":
                    quality = "hd"
            elif model == "gpt-image-1":
                # GPT-Image-1 supports: 'low', 'medium', 'high'
                if quality == "standard":
                    quality = "medium"
                elif quality == "hd":
                    quality = "high"

            params = {
                "model": f"openai/{model}",
                "prompt": prompt,
                "n": number_of_images,
                "api_key": self.api_key,
            }
            
            # Only add quality parameter for models that support it (DALL-E-3 and GPT-Image-1)
            if model in ["dall-e-3", "gpt-image-1"]:
                params["quality"] = quality
            
            if self._is_emergent_key(self.api_key):
                params["api_base"] = self.emergent_proxy_url
                
                # Add custom headers when using Emergent proxy
                if self.custom_headers:
                    params["extra_headers"] = self.custom_headers

            response = image_generation(**params)
            
            # Convert URLs/base64 to bytes
            image_bytes_list = []
            for img in response.data:
                # Check if we have b64_json or url
                if hasattr(img, 'b64_json') and img.b64_json:
                    image_bytes_list.append(base64.b64decode(img.b64_json))
                elif hasattr(img, 'url') and img.url:
                    # If we get URL instead of base64, fetch the image
                    image_response = requests.get(img.url)
                    image_bytes_list.append(image_response.content)
                else:
                    raise Exception(f"Unexpected image response format: {img}")
            
            return image_bytes_list
        except Exception as e:
            raise Exception(f"Failed to generate images: {str(e)}")

