"""
MAIN ENTRY POINT
================
Unified FastAPI app for Railway deployment.
Runs:
  - Vapi webhook server (voice call events)
  - WhatsApp inbound webhook (Twilio)
  - Health check endpoint
  - Manual trigger endpoints (for testing)
  - Background orchestrator (follow-ups, new leads)
"""

import os
import json
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import JSONResponse, HTMLResponse
from dotenv import load_dotenv

load_dotenv()

# Import all modules
from module2_agent_brain import SalesAgentBrain
from module3_voice_agent import VapiCallManager, vapi_webhook
from module4_outreach import OutreachOrchestrator, WhatsAppManager
from module5_orchestrator import SalesAgentOrchestrator, LeadStateManager


# ── Background Orchestrator ───────────────────────────────────────────────────
orchestrator = SalesAgentOrchestrator()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start background tasks when app starts."""
    print("🚀 AI Sales Agent starting up...")
    # Start the scheduler in background
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, start_scheduler)
    yield
    print("Shutting down...")

def start_scheduler():
    """Start the APScheduler in a thread."""
    try:
        orchestrator.scheduler.start()
        print("✅ Scheduler started")
    except Exception as e:
        print(f"Scheduler error: {e}")


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="AI Sales Agent",
    description="Automated sales pipeline for DigitalBoost Agency",
    version="1.0.0",
    lifespan=lifespan
)


# ── Health Check ──────────────────────────────────────────────────────────────
@app.get("/")
async def root():
    state = LeadStateManager()
    leads = state.load_all()
    return {
        "status": "✅ AI Sales Agent is LIVE",
        "total_leads": len(leads),
        "by_stage": {
            stage: len([l for l in leads if l.get("stage") == stage])
            for stage in ["new", "contacted", "discovery", "qualified", "pitched", "closed", "cold"]
        },
        "scheduler": "running" if orchestrator.scheduler.running else "stopped"
    }

@app.get("/health")
async def health():
    return {"status": "ok"}


# ── Vapi Voice Webhook ────────────────────────────────────────────────────────
@app.post("/vapi/webhook")
async def handle_vapi_webhook(request: Request):
    """Receives all Vapi call events (call-started, transcript, call-ended)."""
    return await vapi_webhook(request)


# ── Twilio WhatsApp Inbound Webhook ───────────────────────────────────────────
@app.post("/twilio/whatsapp/inbound")
async def handle_whatsapp_inbound(request: Request):
    """
    Twilio calls this when a prospect replies on WhatsApp.
    Set this URL in Twilio Console → WhatsApp Sandbox → When a message comes in
    """
    form = await request.form()
    from_number = form.get("From", "").replace("whatsapp:", "")
    message_body = form.get("Body", "")

    print(f"[WhatsApp Inbound] From: {from_number} | Message: {message_body}")

    # Get AI response
    wa_mgr = WhatsAppManager()
    ai_response = wa_mgr.handle_inbound_whatsapp(from_number, message_body)

    # Send reply back
    wa_mgr._send_whatsapp(from_number, ai_response)

    # Also update orchestrator pipeline
    orchestrator.handle_response(from_number, message_body, channel="whatsapp")

    return JSONResponse({"status": "replied"})


# ── Manual Trigger Endpoints (for testing) ────────────────────────────────────
@app.post("/trigger/new-leads")
async def trigger_new_leads(background_tasks: BackgroundTasks):
    """Manually trigger new lead processing."""
    background_tasks.add_task(orchestrator.process_new_leads)
    return {"status": "triggered", "message": "Processing new leads in background"}

@app.post("/trigger/followups")
async def trigger_followups(background_tasks: BackgroundTasks):
    """Manually trigger follow-up processing."""
    background_tasks.add_task(orchestrator.process_followups)
    return {"status": "triggered", "message": "Processing follow-ups in background"}

@app.post("/trigger/source-leads")
async def trigger_lead_sourcing(background_tasks: BackgroundTasks):
    """Run the lead sourcing pipeline."""
    from module1_lead_sourcing import LeadSourcingPipeline
    async def run():
        pipeline = LeadSourcingPipeline()
        pipeline.run(cities=["Mumbai", "Delhi", "Bangalore"], max_leads=100)
    background_tasks.add_task(run)
    return {"status": "triggered", "message": "Lead sourcing started in background"}

@app.post("/trigger/test-call")
async def trigger_test_call(request: Request):
    """Make a test call to a specific number."""
    body = await request.json()
    phone = body.get("phone")
    name  = body.get("name", "Test Lead")
    
    if not phone:
        return JSONResponse({"error": "phone required"}, status_code=400)
    
    caller = VapiCallManager()
    test_lead = {
        "name": name, "phone": phone,
        "website": "https://test.com", "pain_points": ["low traffic"],
        "email": "", "city": "Mumbai"
    }
    result = caller.make_outbound_call(test_lead)
    return {"status": "call_initiated", "call_id": result.get("id")}

@app.post("/trigger/test-chat")
async def trigger_test_chat(request: Request):
    """Test the AI brain with a sample conversation."""
    body = await request.json()
    message = body.get("message", "Hello, who is this?")
    
    brain = SalesAgentBrain()
    test_lead = {
        "name": "Test Lead", "email": "test@example.com",
        "phone": "+919999999999", "website": "https://mystore.in",
        "city": "Mumbai", "pain_points": ["slow website", "bad SEO"], "stage": "new"
    }
    result = brain.chat(test_lead, message, channel="whatsapp")
    return {"ai_response": result["response"], "stage": result["stage"], "action": result["action"]}


# ── Leads API ─────────────────────────────────────────────────────────────────
@app.get("/leads")
async def get_leads(stage: str = None):
    """View all leads, optionally filtered by stage."""
    state = LeadStateManager()
    leads = state.load_all()
    if stage:
        leads = [l for l in leads if l.get("stage") == stage]
    return {"total": len(leads), "leads": leads}

@app.post("/leads/add")
async def add_lead(request: Request):
    """Manually add a lead."""
    body = await request.json()
    state = LeadStateManager()
    leads = state.load_all()
    from datetime import datetime
    body["stage"] = "new"
    body["created_at"] = datetime.utcnow().isoformat()
    body["pain_points"] = body.get("pain_points", [])
    leads.append(body)
    state.save_all(leads)
    return {"status": "added", "lead": body}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
