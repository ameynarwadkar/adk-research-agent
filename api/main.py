import time
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from api.schemas import ResearchRequest, ResearchResponse
from research_agent.orchestrator import run_pipeline

app = FastAPI(title="ADK Research Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.post("/research", response_model=ResearchResponse)
async def run_research(req: ResearchRequest):
    try:
        start_time = time.time()
        review = await run_pipeline(req.question)
        total_time = time.time() - start_time
        
        return ResearchResponse(
            review=review,
            total_time_seconds=total_time,
            total_tokens=0  # To be implemented with Langfuse tracking later
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
