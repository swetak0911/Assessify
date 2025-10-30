from fastapi import FastAPI, APIRouter, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List
import uuid
from datetime import datetime, timezone
from emergentintegrations.llm.chat import LlmChat, UserMessage
import base64
from PIL import Image
import io
import pytesseract

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Get EMERGENT_LLM_KEY
EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY')

# Define Models
class SolveCodeRequest(BaseModel):
    question: str
    model_provider: str = "openai"  # openai, anthropic, gemini, deepseek
    model_name: str = "gpt-5"
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))

class SolveCodeResponse(BaseModel):
    solution: str
    session_id: str
    timestamp: str

class OCRRequest(BaseModel):
    image_base64: str

class OCRResponse(BaseModel):
    extracted_text: str

class SessionHistory(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    question: str
    solution: str
    model_provider: str
    model_name: str
    timestamp: str

# Routes
@api_router.get("/")
async def root():
    return {"message": "Interview Assistant API Ready"}

@api_router.post("/solve-code", response_model=SolveCodeResponse)
async def solve_code(request: SolveCodeRequest):
    try:
        # Initialize LLM Chat
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=request.session_id,
            system_message="You are an expert coding interview assistant. Analyze the problem and provide the most efficient solution with optimal time and space complexity. Format your response with clear explanations and clean, production-ready code."
        )
        
        # Handle DeepSeek models with deepseek/ prefix
        if request.model_provider == 'deepseek':
            model_to_use = f"deepseek/{request.model_name}"
            # Use litellm provider for deepseek
            chat.with_model("openai", model_to_use)
        else:
            # Set the model for other providers
            chat.with_model(request.model_provider, request.model_name)
        
        # Create prompt
        prompt = f"""Problem Statement:
{request.question}

Provide:
1. Problem Analysis
2. Optimal Algorithm/Approach
3. Time & Space Complexity
4. Complete, working code solution
5. Brief explanation of the solution

Make the code clean, well-commented, and production-ready."""
        
        user_message = UserMessage(text=prompt)
        
        # Get response from LLM
        response = await chat.send_message(user_message)
        
        # Store in database
        session_doc = {
            "id": str(uuid.uuid4()),
            "session_id": request.session_id,
            "question": request.question,
            "solution": response,
            "model_provider": request.model_provider,
            "model_name": request.model_name,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        await db.sessions.insert_one(session_doc)
        
        return SolveCodeResponse(
            solution=response,
            session_id=request.session_id,
            timestamp=session_doc["timestamp"]
        )
    except Exception as e:
        logger.error(f"Error in solve_code: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/ocr-image", response_model=OCRResponse)
async def ocr_image(request: OCRRequest):
    try:
        # Decode base64 image
        image_data = base64.b64decode(request.image_base64.split(',')[1] if ',' in request.image_base64 else request.image_base64)
        image = Image.open(io.BytesIO(image_data))
        
        # Perform OCR
        extracted_text = pytesseract.image_to_string(image)
        
        return OCRResponse(extracted_text=extracted_text)
    except Exception as e:
        logger.error(f"Error in OCR: {str(e)}")
        raise HTTPException(status_code=500, detail=f"OCR failed: {str(e)}")

@api_router.get("/sessions/{session_id}", response_model=List[SessionHistory])
async def get_session_history(session_id: str):
    sessions = await db.sessions.find({"session_id": session_id}, {"_id": 0}).to_list(1000)
    return sessions

@api_router.get("/sessions", response_model=List[SessionHistory])
async def get_all_sessions():
    sessions = await db.sessions.find({}, {"_id": 0}).sort("timestamp", -1).to_list(100)
    return sessions

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()