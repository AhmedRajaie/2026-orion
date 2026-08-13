import os
from dotenv import load_dotenv

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from openai import OpenAI


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()

PROVIDER = os.getenv("AI_PROVIDER", "gemini")

CONFIG = {
    "openai": {
        "api_key": os.getenv("OPENAI_API_KEY"),
        "base_url": None,
        "model": "gpt-5-mini",
    },

    "gemini": {
        "api_key": os.getenv("GEMINI_API_KEY"),
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "model": "gemini-flash-latest",
    },

    "anthropic": {
        "api_key": os.getenv("ANTHROPIC_API_KEY"),
        "base_url": "https://api.anthropic.com/v1/",
        "model": "claude-sonnet-5",
    },
}


# ============================================================
# FASTAPI APP
# ============================================================

app = FastAPI(
    title="Stock Prediction Dashboard API",
    description="Backend API for LSTM, MLP and AI Assistant",
    version="1.0.0",
)


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# BASIC ROUTES
# ============================================================

@app.get("/")
def root():
    return {
        "message": "Stock Prediction API is running",
        "ai_provider": PROVIDER,
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "ai_provider": PROVIDER,
    }


# ============================================================
# AI CHAT
# ============================================================

class ChatRequest(BaseModel):
    message: str
    context: dict | None = None


def get_ai_client():

    cfg = CONFIG.get(PROVIDER)

    if not cfg:
        raise HTTPException(
            status_code=500,
            detail=f"Unknown AI provider: {PROVIDER}"
        )

    if not cfg["api_key"]:
        raise HTTPException(
            status_code=500,
            detail=f"{PROVIDER.upper()} API key is missing."
        )

    if cfg["base_url"]:
        return OpenAI(
            api_key=cfg["api_key"],
            base_url=cfg["base_url"]
        )

    return OpenAI(
        api_key=cfg["api_key"]
    )


def build_system_prompt(context=None):

    prompt = """
You are an AI assistant inside a stock market prediction dashboard.

Your job is to help the user understand:
- stock trends
- LSTM predictions
- MLP predictions
- model performance
- technical indicators
- strategy performance
- dashboard charts

Important rules:

1. Explain technical results in simple language.
2. Use the dashboard data provided to you.
3. Do not invent values that are not provided.
4. Clearly distinguish predictions from facts.
5. Do not present financial predictions as guaranteed outcomes.
6. If the user asks about an LSTM prediction, explain what the
   prediction means and mention the relevant model confidence/value
   when available.
7. Keep answers concise and useful.
"""

    if context:

        prompt += """

CURRENT DASHBOARD DATA:

"""

        prompt += str(context)

    return prompt


@app.post("/ai-chat")
def ai_chat(request: ChatRequest):

    if not request.message.strip():
        raise HTTPException(
            status_code=400,
            detail="Message cannot be empty."
        )

    try:

        client = get_ai_client()

        system_prompt = build_system_prompt(
            request.context
        )

        response = client.chat.completions.create(
            model=CONFIG[PROVIDER]["model"],

            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": request.message
                }
            ],

            max_tokens=500,
        )

        answer = response.choices[0].message.content

        return {
            "success": True,
            "reply": answer,
            "provider": PROVIDER,
        }

    except Exception as e:

        print("AI ERROR:", repr(e))

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


# ============================================================
# LSTM / MLP RESULTS
# ============================================================

# Replace these example values with your actual model results.

MODEL_RESULTS = {
    "lstm": {
        "prediction": "UP",
        "confidence": 0.82,
        "status": "available"
    },

    "mlp": {
        "prediction": "UP",
        "confidence": 0.76,
        "status": "available"
    },

    "model": {
        "name": "LSTM",
        "sequence_length": 20,
        "top_k": 5,
        "epochs": 20
    },

    "loss": {
        "train": [],
        "test": []
    },

    "final_values": {
        "lstm": 100000,
        "mlp": 98000,
        "benchmark": 95000
    },

    "predictions": [],
    "actual": []
}


@app.get("/model-results")
def model_results():

    return {
        "status": "ok",
        "success": True,

        "models": {
            "lstm": MODEL_RESULTS["lstm"],
            "mlp": MODEL_RESULTS["mlp"]
        },

        "model": MODEL_RESULTS["model"],

        "loss": MODEL_RESULTS["loss"],

        "final_values": MODEL_RESULTS["final_values"],

        "predictions": MODEL_RESULTS["predictions"],

        "actual": MODEL_RESULTS["actual"]
    }


@app.get("/lstm")
def lstm_result():

    return {
        "success": True,
        "model": "LSTM",
        "prediction": MODEL_RESULTS["lstm"]["prediction"],
        "confidence": MODEL_RESULTS["lstm"]["confidence"]
    }


@app.get("/mlp")
def mlp_result():

    return {
        "success": True,
        "model": "MLP",
        "prediction": MODEL_RESULTS["mlp"]["prediction"],
        "confidence": MODEL_RESULTS["mlp"]["confidence"]
    }
