import json
import time
import requests
import os
from typing import Optional, Union, Dict
from io import BytesIO
import base64

try:
    from google import genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False


class GeminiVideoGeneration:
    """Gemini Veo video generation client using LiteLLM proxy."""

    def __init__(self, api_key: str,
                 custom_headers: Dict[str, str] = None):
        """
        Initialize the Gemini video generator.

        Args:
            api_key: API key for LiteLLM proxy authentication
            custom_headers: Custom headers to include in requests
        """
        self.api_key = api_key
        self.custom_headers = custom_headers or {}

        proxy_url = os.getenv("INTEGRATION_PROXY_URL")
        if not proxy_url:
            proxy_url = "https://integrations.emergentagent.com"
        self.base_url = proxy_url + "/llm/gemini/v1beta"

        app_url = os.getenv('APP_URL')
        if app_url:
            self.custom_headers['X-App-ID'] = app_url

        self.headers = {
            "x-goog-api-key": api_key,
            "Content-Type": "application/json",
            "Authorization": api_key,
            **self.custom_headers
        }

    def text_to_video_genai_sdk(self, prompt: str, max_wait_time: int = 600, output_path: str = None, image_path=None,
                                mime_type="image/jpeg") -> Optional[bytes]:
        """
        Alternative text-to-video generation using google-genai SDK approach with custom base URL.

        Note: This is essentially a wrapper that uses the existing HTTP-based methods
        since the genai SDK doesn't directly support video generation with custom endpoints.

        Args:
            prompt: Text description of the video to generate
            max_wait_time: Maximum time to wait in seconds (default: 10 minutes)
            output_path: Path to save the video file (optional)

        Returns:
            Video bytes if successful, None otherwise
        """
        if not GENAI_AVAILABLE:
            print("❌ google-genai SDK not available. Install with: pip install google-genai")
            print("📦 Install with: pip install google-genai")

        print("🔄 Using genai SDK approach (falls back to HTTP requests for video generation)")

        try:
            # Since genai SDK doesn't support video generation with custom endpoints,
            # we'll use our existing HTTP-based method but wrapped in the genai SDK style

            print(f"🚀 Starting video generation with prompt: {prompt}")

            # Use our existing text_to_video method
            video_bytes = self.text_to_video(prompt, max_wait_time, image_path, mime_type)

            if video_bytes:
                if output_path:
                    with open(output_path, 'wb') as f:
                        f.write(video_bytes)
                    print(f"✅ Video saved to: {output_path}")
                    return video_bytes
                else:
                    # Generate auto filename
                    auto_output_path = f"genai_video_{int(time.time())}.mp4"
                    with open(auto_output_path, 'wb') as f:
                        f.write(video_bytes)
                    print(f"✅ Video saved to: {auto_output_path}")
                    return video_bytes
            else:
                print("❌ Video generation failed")
                return None

        except Exception as e:
            print(f"❌ Error in genai SDK video generation: {e}")
            import traceback
            traceback.print_exc()
            return None

    def text_to_video(self, prompt: str, max_wait_time: int = 600, image_path=None, mime_type="image/jpeg") -> Optional[bytes]:
        """
        Generate video from text prompt.

        Args:
            prompt: Text description of the video to generate
            max_wait_time: Maximum time to wait in seconds (default: 10 minutes)

        Returns:
            Video bytes if successful, None otherwise
        """
        operation_name = self._generate_video(prompt, image_path, mime_type)
        if not operation_name:
            return None

        video_uri = self._wait_for_completion(operation_name, max_wait_time)
        if not video_uri:
            return None

        return self._download_video_bytes(video_uri)

    def _generate_video(self, prompt: str, image_path=None, mime_type="image/jpeg") -> Optional[str]:
        """
        Initiate text-to-video generation with Veo.

        Args:
            prompt: Text description of the video to generate

        Returns:
            Operation name if successful, None otherwise
        """
        url = f"{self.base_url}/models/veo-3.0-generate-001:predictLongRunning"

        payload = {
            "instances": [{
                "prompt": prompt,
            }]
        }

        if image_path:
            # --- Read the image file and encode it in base64 ---
            with open(image_path, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode("utf-8")
            payload["instances"][0]["image"] = {"bytesBase64Encoded": encoded_string, "mimeType": mime_type}

        try:
            response = requests.post(url, headers=self.headers, json=payload)
            response.raise_for_status()

            data = response.json()
            operation_name = data.get("name")

            if operation_name:
                return operation_name
            else:
                return None

        except requests.RequestException as e:
            return None

    def _wait_for_completion(self, operation_name: str, max_wait_time: int = 600) -> Optional[str]:
        """
        Poll operation status until video generation is complete.

        Args:
            operation_name: Name of the operation to monitor
            max_wait_time: Maximum time to wait in seconds

        Returns:
            Video URI if successful, None otherwise
        """
        operation_url = f"{self.base_url}/{operation_name}"
        start_time = time.time()
        poll_interval = 10

        while time.time() - start_time < max_wait_time:
            try:
                response = requests.get(operation_url, headers=self.headers)
                response.raise_for_status()

                data = response.json()

                if "error" in data:
                    return None

                is_done = data.get("done", False)

                if is_done:
                    try:
                        video_uri = data["response"]["generateVideoResponse"]["generatedSamples"][0]["video"]["uri"]
                        return video_uri
                    except KeyError:
                        return None

                time.sleep(poll_interval)
                poll_interval = min(poll_interval * 1.2, 30)

            except requests.RequestException:
                time.sleep(poll_interval)

        return None

    def _download_video_bytes(self, video_uri: str) -> Optional[bytes]:
        """
        Download the generated video file as bytes.

        Args:
            video_uri: URI of the video to download

        Returns:
            Video bytes if successful, None otherwise
        """
        try:
            # Convert Google URI to LiteLLM proxy URI
            download_path = video_uri.split("https://generativelanguage.googleapis.com/v1beta/")[1]
            litellm_download_url = f"{self.base_url}/{download_path}"

            print(f"Debug: Downloading from URL: {litellm_download_url}")

            # Follow redirects manually to ensure we get the actual file
            session = requests.Session()
            session.headers.update(self.headers)

            response = session.get(
                litellm_download_url,
                stream=True,
                allow_redirects=False  # Handle redirects manually
            )

            print(f"Debug: Initial response status: {response.status_code}")
            print(f"Debug: Initial response headers: {dict(response.headers)}")

            # Handle redirects manually
            redirect_count = 0
            max_redirects = 5

            while response.status_code in (301, 302, 303, 307, 308) and redirect_count < max_redirects:
                redirect_url = response.headers.get('location')
                print(f"Debug: Redirect #{redirect_count + 1} to: {redirect_url}")
                if not redirect_url:
                    return None

                redirect_count += 1
                response = session.get(
                    redirect_url,
                    stream=True,
                    allow_redirects=False
                )
                print(f"Debug: Redirect response status: {response.status_code}")

            if response.status_code != 200:
                print(f"Debug: Final status code: {response.status_code}")
                print(f"Debug: Final response text: {response.text[:500]}")

            response.raise_for_status()

            # Verify we have the actual video content
            content_type = response.headers.get('content-type', '')
            content_length = response.headers.get('content-length', 'unknown')
            print(f"Debug: Content-Type: {content_type}")
            print(f"Debug: Content-Length: {content_length}")

            if not (content_type.startswith('video/') or content_type.startswith('application/octet-stream')):
                print("Debug: Content type doesn't look like video, trying fallback approach")
                # If we still don't have video content, try one more approach
                # Some proxies might need different handling
                final_response = session.get(
                    litellm_download_url,
                    stream=True,
                    allow_redirects=True  # Let requests handle all redirects
                )
                final_response.raise_for_status()
                response = final_response
                print(f"Debug: Fallback Content-Type: {response.headers.get('content-type', '')}")

            video_bytes = BytesIO()
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    video_bytes.write(chunk)

            video_data = video_bytes.getvalue()
            print(f"Debug: Downloaded {len(video_data)} bytes")

            # Verify we actually got video data (should be much larger than 180 bytes)
            if len(video_data) < 1000:  # Video files should be at least 1KB
                print(f"Debug: Video data too small ({len(video_data)} bytes), returning None")
                return None

            return video_data

        except requests.RequestException as e:
            print(f"Debug: Request exception: {e}")
            return None