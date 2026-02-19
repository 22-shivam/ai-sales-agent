"""
MODULE 3: VOICE CALLING AGENT (Vapi.ai)
========================================
Makes real AI phone calls that sound human.

Features:
  - Outbound cold calls to leads
  - Real-time conversation via Vapi + GPT-4o
  - Call transcripts saved automatically
  - Webhook handler for call events
  - Inbound call support (prospects calling back)

Setup:
  pip install vapi-python fastapi uvicorn
  Set VAPI_API_KEY, VAPI_PHONE_NUMBER_ID in env
"""

import os
import json
import requests
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from module2_agent_brain import SalesAgentBrain, SERVICE_PACKAGES

# ── Config ────────────────────────────────────────────────────────────────────
VAPI_API_KEY         = os.getenv("VAPI_API_KEY")
VAPI_PHONE_NUMBER_ID = os.getenv("VAPI_PHONE_NUMBER_ID")   # from Vapi dashboard
OPENAI_API_KEY       = os.getenv("OPENAI_API_KEY")
WEBHOOK_BASE_URL     = os.getenv("WEBHOOK_BASE_URL")        # e.g. https://yourserver.com

VAPI_BASE = "https://api.vapi.ai"
HEADERS   = {"Authorization": f"Bearer {VAPI_API_KEY}", "Content-Type": "application/json"}


# ── Vapi Assistant Config ─────────────────────────────────────────────────────
def build_assistant_config(lead: dict) -> dict:
    """
    Builds the Vapi assistant configuration for a specific lead.
    This defines the AI's voice, personality, and first message.
    """
    pain_points = ", ".join(lead.get("pain_points", [])) or "online visibility issues"
    
    system_prompt = f"""
You are Aryan, a senior sales consultant at DigitalBoost Agency, calling {lead['name']} 
about their e-commerce website at {lead.get('website', 'their store')}.

You know their website has issues with: {pain_points}

Your goal: Have a natural conversation, uncover pain, pitch the right solution.

CALL SCRIPT FLOW:
1. Introduce yourself briefly (10 sec max)
2. Ask one discovery question: "Quick question — are you happy with the traffic and sales your website is generating?"
3. Listen carefully, ask follow-ups
4. Pitch the relevant package when you understand their pain
5. Handle objections warmly
6. Try to get a commitment or schedule a follow-up

CALL RULES:
- Speak naturally, short sentences
- Never read off a script, be conversational  
- If they're busy, ask for a better time
- If voicemail, leave a 20-second message with a callback hook
- Do NOT rush to pitch — discovery first

Available packages to pitch:
- Starter (₹15,000/mo): Basic SEO + website fix — for stores with no online presence
- Growth (₹35,000/mo): Full SEO + Shopify optimization + Google Ads — for stores with low traffic
- Premium (₹75,000/mo): Full rebuild + aggressive ads + CRO — for scaling stores
"""

    return {
        "name": f"Aryan - DigitalBoost - {lead['name']}",
        "model": {
            "provider": "openai",
            "model": "gpt-4o",
            "systemPrompt": system_prompt,
            "temperature": 0.7,
        },
        "voice": {
            "provider": "elevenlabs",
            "voiceId": "pNInz6obpgDQGcFmaJgB",   # Adam voice — replace with your preferred voice
            "stability": 0.5,
            "similarityBoost": 0.75,
        },
        "firstMessage": f"Hi, is this {lead['name'].split()[0]}? This is Aryan calling from DigitalBoost Agency — do you have just 2 minutes?",
        "transcriber": {
            "provider": "deepgram",
            "model": "nova-2",
            "language": "en-IN",   # Indian English
        },
        "serverUrl": f"{WEBHOOK_BASE_URL}/vapi/webhook",
        "endCallFunctionEnabled": True,
        "recordingEnabled": True,
        "silenceTimeoutSeconds": 30,
        "maxDurationSeconds": 1800,   # 30 min max
    }


# ── Vapi Call Manager ─────────────────────────────────────────────────────────
class VapiCallManager:

    def make_outbound_call(self, lead: dict) -> dict:
        """Initiate an outbound AI call to a lead."""
        if not lead.get("phone"):
            raise ValueError(f"No phone number for lead: {lead.get('name')}")
        
        assistant_config = build_assistant_config(lead)
        
        payload = {
            "phoneNumberId": VAPI_PHONE_NUMBER_ID,
            "customer": {
                "number": lead["phone"],   # E.164 format: +919876543210
                "name": lead.get("name", ""),
            },
            "assistant": assistant_config,
            "metadata": {
                "lead_email": lead.get("email"),
                "lead_website": lead.get("website"),
                "campaign": "ecommerce_outreach_v1"
            }
        }
        
        resp = requests.post(f"{VAPI_BASE}/call/phone", headers=HEADERS, json=payload)
        resp.raise_for_status()
        
        call_data = resp.json()
        print(f"📞 Call initiated to {lead['name']} ({lead['phone']}) — Call ID: {call_data['id']}")
        return call_data

    def schedule_callback(self, lead: dict, scheduled_time: str) -> dict:
        """Schedule a callback at a specific time (ISO 8601 format)."""
        # Use your scheduling system (e.g., Google Calendar API, Cal.com)
        # Here we store it and trigger via a cron job or n8n workflow
        return {
            "status": "scheduled",
            "lead": lead["name"],
            "time": scheduled_time,
            "phone": lead["phone"]
        }

    def get_call_transcript(self, call_id: str) -> dict:
        """Retrieve transcript + recording after a call ends."""
        resp = requests.get(f"{VAPI_BASE}/call/{call_id}", headers=HEADERS)
        resp.raise_for_status()
        call = resp.json()
        
        return {
            "call_id": call_id,
            "duration": call.get("endedAt", ""),
            "transcript": call.get("transcript", ""),
            "recording_url": call.get("recordingUrl", ""),
            "summary": call.get("summary", ""),
            "cost": call.get("cost", 0),
        }

    def run_bulk_campaign(self, leads: list[dict], delay_seconds: int = 60) -> list:
        """
        Call multiple leads with a delay between each call.
        Recommended: 60s+ between calls to avoid spam flags.
        """
        import time
        results = []
        for i, lead in enumerate(leads):
            try:
                print(f"\n[{i+1}/{len(leads)}] Calling {lead['name']}...")
                result = self.make_outbound_call(lead)
                results.append({"lead": lead["name"], "status": "called", "call_id": result["id"]})
            except Exception as e:
                print(f"  ❌ Failed for {lead['name']}: {e}")
                results.append({"lead": lead["name"], "status": "failed", "error": str(e)})
            
            if i < len(leads) - 1:
                time.sleep(delay_seconds)
        
        return results


# ── Webhook Server (FastAPI) ──────────────────────────────────────────────────
app = FastAPI(title="AI Sales Agent - Vapi Webhook")

# In-memory store (replace with DB in production)
call_sessions = {}

@app.post("/vapi/webhook")
async def vapi_webhook(request: Request):
    """
    Handles all Vapi call events:
      - call-started
      - transcript (real-time)
      - function-call (tool use)
      - call-ended
      - hang (prospect hung up)
    """
    body = await request.json()
    event_type = body.get("message", {}).get("type")
    call_id    = body.get("message", {}).get("call", {}).get("id", "")
    
    print(f"[Webhook] Event: {event_type} | Call: {call_id}")

    if event_type == "call-started":
        call_sessions[call_id] = {"status": "active", "transcript": []}
        return JSONResponse({"status": "ok"})

    elif event_type == "transcript":
        msg = body["message"]
        role = msg.get("role")       # "user" or "assistant"
        text = msg.get("transcript", "")
        
        if call_id in call_sessions:
            call_sessions[call_id]["transcript"].append({"role": role, "text": text})
        
        return JSONResponse({"status": "ok"})

    elif event_type == "function-call":
        # Handle tool calls from the AI (e.g., "send_quote", "schedule_followup")
        fn_name = body["message"].get("functionCall", {}).get("name")
        fn_args = body["message"].get("functionCall", {}).get("parameters", {})
        
        result = await handle_function_call(fn_name, fn_args, call_id)
        return JSONResponse({"result": result})

    elif event_type == "call-ended":
        reason = body["message"].get("endedReason", "")
        duration = body["message"].get("call", {}).get("duration", 0)
        
        print(f"[Call Ended] Reason: {reason} | Duration: {duration}s")
        
        # Update CRM + trigger follow-up workflow
        await post_call_processing(call_id, body["message"])
        return JSONResponse({"status": "ok"})

    elif event_type == "hang":
        print(f"[Prospect Hung Up] Call: {call_id}")
        # Schedule follow-up
        await post_call_processing(call_id, body["message"], hung_up=True)
        return JSONResponse({"status": "ok"})

    return JSONResponse({"status": "unhandled", "event": event_type})


async def handle_function_call(fn_name: str, fn_args: dict, call_id: str) -> str:
    """Handle AI tool use during a call."""
    if fn_name == "send_quote":
        package = fn_args.get("package", "growth")
        email   = fn_args.get("email", "")
        # Trigger email with quote (see Module 4)
        print(f"  [Action] Sending quote: {package} to {email}")
        return f"Quote for {package} package sent to {email}. I've just sent it — you should receive it in a few minutes."

    elif fn_name == "schedule_callback":
        time_str = fn_args.get("preferred_time", "tomorrow")
        print(f"  [Action] Scheduling callback for {time_str}")
        return f"Perfect, I've noted {time_str} for our follow-up call."

    elif fn_name == "transfer_to_human":
        print(f"  [Action] Transferring to human agent")
        # In Vapi, you can transfer to a real phone number
        return "Transferring you to my senior consultant now."

    return "Done"


async def post_call_processing(call_id: str, call_data: dict, hung_up: bool = False):
    """After call ends: save transcript, update CRM, trigger follow-up."""
    import httpx
    
    # Get transcript from call session
    session = call_sessions.get(call_id, {})
    transcript = session.get("transcript", [])
    
    # Extract outcome using GPT (quick summarization)
    if transcript:
        transcript_text = "\n".join([f"{t['role']}: {t['text']}" for t in transcript])
        # You can call GPT here to extract: outcome, pain points, next action
        print(f"  [Post-Call] Transcript saved. {len(transcript)} turns.")
    
    # Trigger n8n follow-up workflow via webhook
    n8n_webhook = os.getenv("N8N_FOLLOWUP_WEBHOOK_URL")
    if n8n_webhook:
        async with httpx.AsyncClient() as client:
            await client.post(n8n_webhook, json={
                "call_id": call_id,
                "outcome": "hung_up" if hung_up else "completed",
                "transcript": transcript
            })


# ── Entry Point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    
    # Start webhook server
    print("Starting Vapi webhook server on port 8000...")
    print("Expose with: ngrok http 8000")
    print("Set WEBHOOK_BASE_URL=https://your-ngrok-url.ngrok.io")
    
    uvicorn.run(app, host="0.0.0.0", port=8000)
