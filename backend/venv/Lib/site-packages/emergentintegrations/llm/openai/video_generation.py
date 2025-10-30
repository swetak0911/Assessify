import time
import json
import requests
import os
from typing import Optional, Dict
from io import BytesIO
import base64


class OpenAIVideoGeneration:
    """OpenAI Sora video generation client using emergent proxy."""

    # Supported models
    MODELS = ["sora-2", "sora-2-pro"]

    # Supported video sizes
    SIZES = {
        "1280x720": {"width": 1280, "height": 720},
        "1792x1024": {"width": 1792, "height": 1024},
        "1024x1792": {"width": 1024, "height": 1792},
        "1024x1024": {"width": 1024, "height": 1024}
    }

    # Supported durations in seconds
    DURATIONS = [4, 8, 12]

    def __init__(self, api_key: str, custom_headers: Dict[str, str] = None):
        """
        Initialize the OpenAI video generator.

        Args:
            api_key: API key for emergent proxy authentication
            custom_headers: Custom headers to include in requests
        """
        self.api_key = api_key
        self.custom_headers = custom_headers or {}

        # Always use emergent proxy (like Gemini does)
        proxy_url = os.getenv("INTEGRATION_PROXY_URL")
        if not proxy_url:
            proxy_url = "https://integrations.emergentagent.com"
        self.base_url = proxy_url + "/llm/openai/v1"

        app_url = os.getenv('APP_URL')
        if app_url:
            self.custom_headers['X-App-ID'] = app_url

        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            **self.custom_headers
        }

    def text_to_video(
        self,
        prompt: str,
        model: str = "sora-2",
        size: str = "1280x720",
        duration: int = 4,
        max_wait_time: int = 600,
        image_path: Optional[str] = None,
        mime_type: str = "image/jpeg"
    ) -> Optional[bytes]:
        """
        Generate video from text prompt.

        Args:
            prompt: Text description of the video to generate
            model: Model to use ("sora-2" or "sora-2-pro")
            size: Video size (e.g., "1280x720", "1792x1024", "1024x1792", "1024x1024")
            duration: Video duration in seconds (4, 8, or 12)
            max_wait_time: Maximum time to wait in seconds (default: 10 minutes)
            image_path: Optional path to reference image for video generation
            mime_type: MIME type of the image if provided

        Returns:
            Video bytes if successful, None otherwise
        """
        # Validate parameters
        if model not in self.MODELS:
            raise ValueError(f"Invalid model: {model}. Must be one of {self.MODELS}")
        if size not in self.SIZES:
            raise ValueError(f"Invalid size: {size}. Must be one of {list(self.SIZES.keys())}")
        if duration not in self.DURATIONS:
            raise ValueError(f"Invalid duration: {duration}. Must be one of {self.DURATIONS}")

        # Initiate video generation
        operation_id = self._generate_video(prompt, model, size, duration, image_path, mime_type)
        if not operation_id:
            return None

        # Wait for completion
        video_uri = self._wait_for_completion(operation_id, max_wait_time)
        if not video_uri:
            return None

        # Download the video
        return self._download_video_bytes(video_uri)

    def _generate_video(
        self,
        prompt: str,
        model: str,
        size: str,
        duration: int,
        image_path: Optional[str] = None,
        mime_type: str = "image/jpeg"
    ) -> Optional[str]:
        """
        Initiate video generation with OpenAI Sora.

        Args:
            prompt: Text description of the video to generate
            model: Model to use
            size: Video size
            duration: Video duration in seconds
            image_path: Optional path to reference image
            mime_type: MIME type of the image

        Returns:
            Operation ID if successful, None otherwise
        """
        url = f"{self.base_url}/videos"

        # According to Sora 2 API docs, duration is passed as "seconds" and as a string
        payload = {
            "model": model,
            "prompt": prompt,
            "size": size,
            "seconds": str(duration)  # Sora 2 expects "seconds" as string "4", "8", or "12"
        }

        # Add reference image if provided
        if image_path:
            with open(image_path, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode("utf-8")
            payload["reference_image"] = {
                "data": f"data:{mime_type};base64,{encoded_string}"
            }

        try:
            response = requests.post(url, headers=self.headers, json=payload)
            response.raise_for_status()

            data = response.json()

            # OpenAI may return the operation ID differently
            # Check for various possible field names
            operation_id = data.get("id") or data.get("operation_id") or data.get("generation_id")

            if operation_id:
                print(f"Video generation initiated with ID: {operation_id}")
                return operation_id
            else:
                print(f"Error: No operation ID in response: {data}")
                return None

        except requests.RequestException as e:
            print(f"Error initiating video generation: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Response content: {e.response.text}")
            return None

    def _wait_for_completion(self, operation_id: str, max_wait_time: int = 600) -> Optional[str]:
        """
        Poll operation status until video generation is complete.

        Args:
            operation_id: ID of the generation operation to monitor
            max_wait_time: Maximum time to wait in seconds

        Returns:
            Video URI if successful, None otherwise
        """
        operation_url = f"{self.base_url}/videos/{operation_id}"
        start_time = time.time()
        poll_interval = 10  # Start with 10 seconds

        print(f"Waiting for video generation to complete (ID: {operation_id})...")

        while time.time() - start_time < max_wait_time:
            try:
                response = requests.get(operation_url, headers=self.headers)
                response.raise_for_status()

                data = response.json()

                # Check for errors - only if error field has actual value
                if data.get("error"):  # This will be False if error is None or doesn't exist
                    print(f"Error in video generation: {data['error']}")
                    return None

                # Check status - be flexible with case
                status = data.get("status", "").lower()

                # Also check for alternative status fields
                if not status:
                    status = data.get("state", "").lower()
                if not status:
                    status = data.get("job_status", "").lower()

                # Check if completed (various possible values)
                if status in ["completed", "complete", "succeeded", "success", "done"]:
                    print(f"Video generation completed!")

                    # Extract video URI from response
                    # The structure might vary, so we check multiple possible locations
                    video_uri = None

                    # Try different possible response structures
                    if "output" in data and "video_url" in data["output"]:
                        video_uri = data["output"]["video_url"]
                    elif "video" in data and "url" in data["video"]:
                        video_uri = data["video"]["url"]
                    elif "result" in data and "video_url" in data["result"]:
                        video_uri = data["result"]["video_url"]
                    elif "video_url" in data:
                        video_uri = data["video_url"]
                    elif "url" in data:
                        video_uri = data["url"]
                    elif "download_url" in data:
                        video_uri = data["download_url"]
                    elif "output_url" in data:
                        video_uri = data["output_url"]

                    # If no URL in response, construct the download URL using the video ID
                    if not video_uri:
                        # Extract the video ID from the response
                        video_id = data.get("id", operation_id)

                        # Construct the download URL
                        video_uri = f"{self.base_url}/videos/{video_id}/content"
                        print(f"No URL in response, constructed download URL: {video_uri}")

                    if video_uri:
                        print(f"Video ready at: {video_uri}")
                        return video_uri
                    else:
                        print(f"Error: Could not determine video download URL")
                        print(f"Full response: {json.dumps(data, indent=2)}")
                        return None

                elif status in ["failed", "error", "cancelled"]:
                    print(f"Video generation failed: {data.get('error', 'Unknown error')}")
                    return None

                elif status in ["pending", "in_progress", "processing", "running", "queued", "started"]:
                    elapsed = time.time() - start_time
                    progress = data.get("progress", 0)
                    print(f"Still processing... ({int(elapsed)}s elapsed, status: {status}, progress: {progress}%)")

                else:
                    # If no recognizable status, check if video is ready by other means
                    if any(key in data for key in ["video_url", "url", "download_url", "output_url"]):
                        print(f"No standard status, but found video URL")
                        # Try to extract URL
                        video_uri = (data.get("video_url") or data.get("url") or
                                    data.get("download_url") or data.get("output_url"))
                        if video_uri:
                            return video_uri

                    print(f"Unknown status: '{status}' - Full response: {json.dumps(data, indent=2)[:200]}...")

                # Wait with exponential backoff
                time.sleep(poll_interval)
                poll_interval = min(poll_interval * 1.2, 30)  # Max 30 seconds

            except requests.RequestException as e:
                print(f"Error checking status: {e}")
                time.sleep(poll_interval)

        print(f"Timeout: Video generation did not complete within {max_wait_time} seconds")
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
            print(f"Downloading video from: {video_uri}")

            # Always convert to emergent proxy URL (like Gemini does)
            # Convert OpenAI URI to emergent proxy URI if needed
            if "api.openai.com" in video_uri:
                # Extract path after api.openai.com
                path_parts = video_uri.split("api.openai.com/v1/")
                if len(path_parts) > 1:
                    download_url = f"{self.base_url}/{path_parts[1]}"
                else:
                    download_url = video_uri
            else:
                download_url = video_uri

            print(f"Final download URL: {download_url}")

            # Create session for handling redirects
            session = requests.Session()
            session.headers.update(self.headers)

            # Initial request without following redirects
            response = session.get(
                download_url,
                stream=True,
                allow_redirects=False
            )

            print(f"Initial response status: {response.status_code}")

            # Handle redirects manually (following Gemini pattern)
            redirect_count = 0
            max_redirects = 5

            while response.status_code in (301, 302, 303, 307, 308) and redirect_count < max_redirects:
                redirect_url = response.headers.get('location')
                print(f"Redirect #{redirect_count + 1} to: {redirect_url}")

                if not redirect_url:
                    print("Error: No redirect URL provided")
                    return None

                redirect_count += 1
                response = session.get(
                    redirect_url,
                    stream=True,
                    allow_redirects=False
                )
                print(f"Redirect response status: {response.status_code}")

            if response.status_code != 200:
                print(f"Error: Final status code: {response.status_code}")
                print(f"Response text: {response.text[:500]}")
                return None

            # Verify content type
            content_type = response.headers.get('content-type', '')
            content_length = response.headers.get('content-length', 'unknown')
            print(f"Content-Type: {content_type}")
            print(f"Content-Length: {content_length}")

            # If content type doesn't look like video, try one more time with full redirect following
            if not (content_type.startswith('video/') or content_type.startswith('application/octet-stream')):
                print("Content type doesn't look like video, trying fallback approach")
                final_response = session.get(
                    download_url,
                    stream=True,
                    allow_redirects=True
                )
                final_response.raise_for_status()
                response = final_response
                print(f"Fallback Content-Type: {response.headers.get('content-type', '')}")

            # Download video bytes
            video_bytes = BytesIO()
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    video_bytes.write(chunk)

            video_data = video_bytes.getvalue()
            print(f"Downloaded {len(video_data)} bytes")

            # Verify we got actual video data (should be much larger than 1KB)
            if len(video_data) < 1000:
                print(f"Error: Video data too small ({len(video_data)} bytes)")
                return None

            return video_data

        except requests.RequestException as e:
            print(f"Error downloading video: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Response content: {e.response.text[:500]}")
            return None

    def save_video(self, video_bytes: bytes, output_path: Optional[str] = None) -> str:
        """
        Save video bytes to a file.

        Args:
            video_bytes: The video data to save
            output_path: Path to save the video (auto-generated if not provided)

        Returns:
            Path where the video was saved
        """
        if not output_path:
            output_path = f"openai_video_{int(time.time())}.mp4"

        with open(output_path, 'wb') as f:
            f.write(video_bytes)

        print(f"Video saved to: {output_path}")
        return output_path