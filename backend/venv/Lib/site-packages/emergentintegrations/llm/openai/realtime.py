from typing import Any, Dict
import aiohttp
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

class OpenAIChatRealtime:
    def __init__(self, api_key: str):
        self.api_key = api_key

    async def create_ephemeral_session_for_audio_chat(self, voice: str = "verse", model: str = "gpt-4o-realtime-preview-2024-12-17") -> Dict[str, Any]:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.openai.com/v1/realtime/sessions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "voice": voice,
                }
            ) as response:
                return await response.json()

    async def negotiate_connection(self, sdp_offer: str, model: str = "gpt-4o-realtime-preview-2024-12-17") -> str:
        """
        Negotiates the WebRTC connection using the provided SDP offer.
        
        Args:
            sdp_offer (str): The SDP offer from the client
            
        Returns:
            str: The SDP answer from OpenAI's server
        """
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"https://api.openai.com/v1/realtime?model={model}",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/sdp"
                },
                data=sdp_offer
            ) as response:
                return await response.text()

    @staticmethod
    def register_openai_realtime_router(router: APIRouter, openai_realtime: "OpenAIChatRealtime"):
        """
        Creates and returns a FastAPI router with OpenAI chat endpoints.
        
        Args:
            api_key (str): The OpenAI API key
            system_message (str): The system message to initialize the chat with
            
        Returns:
            APIRouter: A FastAPI router with the chat endpoints
        """
        
        @router.post("/realtime/session")
        async def create_session():
            """
            Creates an ephemeral session for audio chat.
            """
            try:
                session = await openai_realtime.create_ephemeral_session_for_audio_chat()
                return JSONResponse(content=session)
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @router.post("/realtime/negotiate")
        async def negotiate_connection(request: Request):
            """
            Handles WebRTC connection negotiation.
            """
            try:
                sdp_offer = await request.body()
                sdp_answer = await openai_realtime.negotiate_connection(sdp_offer.decode())
                return JSONResponse(content={"sdp": sdp_answer})
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
                
        return router 
