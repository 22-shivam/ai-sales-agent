"""
MODULE 5: FOLLOW-UP AUTOMATION + DEAL CLOSING + MAIN ORCHESTRATOR
==================================================================
The main controller that runs the entire sales pipeline:
  1. Load leads → run outreach
  2. Monitor responses → trigger follow-ups on schedule
  3. Detect closing signals → send quote + contract
  4. Close deals → trigger onboarding
  5. Human handoff for edge cases

Scheduler: APScheduler (runs as background process)
pip install apscheduler httpx
"""

import os
import json
import time
import httpx
from datetime import datetime, timedelta
from typing import Optional
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from module2_agent_brain import SalesAgentBrain
from module3_voice_agent import VapiCallManager
from module4_outreach import OutreachOrchestrator

# ── Config ────────────────────────────────────────────────────────────────────
SLACK_WEBHOOK_URL     = os.getenv("SLACK_WEBHOOK_URL")      # for human alerts
HUBSPOT_API_KEY       = os.getenv("HUBSPOT_API_KEY")
DOCUSIGN_INTEGRATION_KEY = os.getenv("DOCUSIGN_INTEGRATION_KEY")
STRIPE_SECRET_KEY     = os.getenv("STRIPE_SECRET_KEY")

# Follow-up schedule (days after first contact)
FOLLOWUP_SCHEDULE = [2, 5, 10]   # Day 2, Day 5, Day 10


# ── Lead State Manager ────────────────────────────────────────────────────────
class LeadStateManager:
    """Manages lead pipeline state in leads.json (swap for DB in production)."""
    
    def __init__(self, filepath="leads.json"):
        self.filepath = filepath

    def load_all(self) -> list[dict]:
        try:
            with open(self.filepath) as f:
                return json.load(f)
        except FileNotFoundError:
            return []

    def save_all(self, leads: list[dict]):
        with open(self.filepath, "w") as f:
            json.dump(leads, f, indent=2)

    def update_lead(self, identifier: str, updates: dict):
        leads = self.load_all()
        for lead in leads:
            if lead.get("email") == identifier or lead.get("phone") == identifier:
                lead.update(updates)
                break
        self.save_all(leads)

    def get_leads_by_stage(self, stage: str) -> list[dict]:
        return [l for l in self.load_all() if l.get("stage") == stage]

    def get_leads_needing_followup(self) -> list[dict]:
        """Find leads due for follow-up based on schedule."""
        now = datetime.utcnow()
        overdue = []
        
        for lead in self.load_all():
            if lead.get("stage") in ("contacted", "discovery", "qualified"):
                created = datetime.fromisoformat(lead.get("created_at", now.isoformat()))
                days_since = (now - created).days
                followup_num = lead.get("followup_count", 0)
                
                # Check if a new follow-up is due
                if followup_num < len(FOLLOWUP_SCHEDULE):
                    if days_since >= FOLLOWUP_SCHEDULE[followup_num]:
                        lead["_followup_number"] = followup_num + 1
                        overdue.append(lead)
        
        return overdue


# ── Human Handoff (Slack Alert) ───────────────────────────────────────────────
class HumanHandoff:
    def alert(self, lead: dict, reason: str, transcript: str = ""):
        """Send Slack alert for human to take over."""
        if not SLACK_WEBHOOK_URL:
            print(f"[HUMAN HANDOFF NEEDED] {lead['name']} — Reason: {reason}")
            return
        
        payload = {
            "text": f"🚨 *Human handoff needed!*",
            "attachments": [{
                "color": "#ff4444",
                "fields": [
                    {"title": "Lead", "value": lead.get("name"), "short": True},
                    {"title": "Phone", "value": lead.get("phone"), "short": True},
                    {"title": "Website", "value": lead.get("website"), "short": True},
                    {"title": "Stage", "value": lead.get("stage"), "short": True},
                    {"title": "Reason", "value": reason, "short": False},
                    {"title": "Transcript Snippet", "value": transcript[-500:] if transcript else "N/A", "short": False},
                ]
            }]
        }
        try:
            import httpx
            httpx.post(SLACK_WEBHOOK_URL, json=payload)
            print(f"  [Slack] Human handoff alert sent for {lead['name']}")
        except Exception as e:
            print(f"  [Slack] Alert failed: {e}")


# ── Deal Closer ───────────────────────────────────────────────────────────────
class DealCloser:
    """Handles everything after a lead says yes."""

    def close_deal(self, lead: dict, package_key: str):
        """Full closing sequence: send contract → take payment → trigger onboarding."""
        print(f"\n🎉 CLOSING DEAL: {lead['name']} — {package_key}")
        
        # 1. Send contract via DocuSign (or PandaDoc)
        contract_url = self._send_contract(lead, package_key)
        print(f"  [Contract] Sent to {lead['email']} — URL: {contract_url}")
        
        # 2. Send Stripe payment link
        payment_link = self._create_payment_link(package_key)
        print(f"  [Payment] Stripe link: {payment_link}")
        
        # 3. Update HubSpot to "Closed Won"
        self._update_hubspot_stage(lead, "closedwon", package_key)
        
        # 4. Trigger onboarding workflow
        self._trigger_onboarding(lead, package_key)
        
        # 5. Notify team
        HumanHandoff().alert(
            lead,
            f"🎉 DEAL CLOSED — {package_key} package. Onboarding triggered.",
            transcript=""
        )
        
        return {"status": "closed", "contract_url": contract_url, "payment_link": payment_link}

    def _send_contract(self, lead: dict, package_key: str) -> str:
        """
        Send contract via PandaDoc API.
        Replace with DocuSign if preferred.
        """
        # PandaDoc API call
        headers = {
            "Authorization": f"API-Key {os.getenv('PANDADOC_API_KEY')}",
            "Content-Type": "application/json"
        }
        from module2_agent_brain import SERVICE_PACKAGES
        package = SERVICE_PACKAGES.get(package_key, {})
        
        payload = {
            "name": f"Service Agreement — {lead['name']}",
            "template_uuid": os.getenv("PANDADOC_TEMPLATE_ID"),
            "recipients": [{
                "email": lead["email"],
                "first_name": lead["name"].split()[0],
                "last_name": " ".join(lead["name"].split()[1:]),
                "role": "Client"
            }],
            "fields": {
                "client_name": {"value": lead["name"]},
                "client_website": {"value": lead.get("website", "")},
                "package_name": {"value": package.get("name", "")},
                "package_price": {"value": f"₹{package.get('price', 0):,}"},
                "start_date": {"value": datetime.utcnow().strftime("%B %d, %Y")}
            },
            "send_immediately": True
        }
        
        try:
            resp = httpx.post("https://api.pandadoc.com/public/v1/documents", headers=headers, json=payload)
            return resp.json().get("public_preview_url", "Contract sent via email")
        except Exception as e:
            print(f"  [PandaDoc] Error: {e}")
            return "Contract sent via email"

    def _create_payment_link(self, package_key: str) -> str:
        """Create a Stripe payment link for the package."""
        from module2_agent_brain import SERVICE_PACKAGES
        package = SERVICE_PACKAGES.get(package_key, {})
        
        try:
            import stripe
            stripe.api_key = STRIPE_SECRET_KEY
            
            link = stripe.PaymentLink.create(
                line_items=[{
                    "price_data": {
                        "currency": "inr",
                        "product_data": {"name": package.get("name", "")},
                        "unit_amount": package.get("price", 0) * 100,  # paise
                        "recurring": {"interval": "month"}
                    },
                    "quantity": 1
                }]
            )
            return link.url
        except Exception as e:
            print(f"  [Stripe] Error: {e}")
            return f"https://pay.stripe.com/manual/{package_key}"

    def _update_hubspot_stage(self, lead: dict, stage: str, package_key: str):
        """Update deal stage in HubSpot."""
        headers = {"Authorization": f"Bearer {HUBSPOT_API_KEY}", "Content-Type": "application/json"}
        payload = {"properties": {"dealstage": stage, "amount": str(
            {"starter": 15000, "growth": 35000, "premium": 75000}.get(package_key, 0)
        )}}
        try:
            httpx.patch(
                f"https://api.hubapi.com/crm/v3/objects/contacts/{lead.get('email')}",
                headers=headers, json=payload
            )
        except Exception as e:
            print(f"  [HubSpot] Error: {e}")

    def _trigger_onboarding(self, lead: dict, package_key: str):
        """Trigger onboarding workflow (e.g., n8n, Zapier, or your own)."""
        onboarding_webhook = os.getenv("ONBOARDING_WEBHOOK_URL")
        if onboarding_webhook:
            httpx.post(onboarding_webhook, json={
                "lead": lead,
                "package": package_key,
                "triggered_at": datetime.utcnow().isoformat()
            })
            print(f"  [Onboarding] Workflow triggered for {lead['name']}")


# ── Main Orchestrator ─────────────────────────────────────────────────────────
class SalesAgentOrchestrator:
    """
    The brain that runs the entire pipeline.
    Run this as a persistent process (systemd, Docker, etc.)
    """

    def __init__(self):
        self.state       = LeadStateManager()
        self.caller      = VapiCallManager()
        self.outreach    = OutreachOrchestrator()
        self.agent_brain = SalesAgentBrain()
        self.closer      = DealCloser()
        self.handoff     = HumanHandoff()
        self.scheduler   = BackgroundScheduler()

    def start(self):
        """Start the orchestrator."""
        print("\n🚀 AI Sales Agent Orchestrator STARTED")
        print("=" * 50)
        
        # Run new lead outreach every 2 hours
        self.scheduler.add_job(
            self.process_new_leads,
            IntervalTrigger(hours=2),
            id="new_leads"
        )
        
        # Check follow-ups every 6 hours
        self.scheduler.add_job(
            self.process_followups,
            IntervalTrigger(hours=6),
            id="followups"
        )
        
        # Run immediately on start
        self.scheduler.start()
        self.process_new_leads()
        self.process_followups()
        
        print("\n✅ Scheduler running. Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(60)
        except (KeyboardInterrupt, SystemExit):
            self.scheduler.shutdown()
            print("\nOrchestrator stopped.")

    def process_new_leads(self):
        """Process all new leads: call + email + WhatsApp."""
        new_leads = self.state.get_leads_by_stage("new")
        print(f"\n[Orchestrator] Processing {len(new_leads)} new leads...")
        
        for lead in new_leads:
            print(f"  → {lead['name']} ({lead.get('website')})")
            
            # 1. Make AI call
            if lead.get("phone"):
                try:
                    self.caller.make_outbound_call(lead)
                    time.sleep(5)  # brief pause between calls
                except Exception as e:
                    print(f"    [Call Failed] {e}")
            
            # 2. Send email + WhatsApp
            self.outreach.initial_outreach(lead)
            
            # 3. Update stage
            self.state.update_lead(
                lead.get("email") or lead.get("phone"),
                {"stage": "contacted", "contacted_at": datetime.utcnow().isoformat()}
            )
            
            time.sleep(30)  # 30s between each lead

    def process_followups(self):
        """Process leads due for follow-up."""
        due_leads = self.state.get_leads_needing_followup()
        print(f"\n[Orchestrator] {len(due_leads)} leads due for follow-up...")
        
        for lead in due_leads:
            followup_num = lead.pop("_followup_number", 1)
            print(f"  → Follow-up #{followup_num} for {lead['name']}")
            
            # Call + WhatsApp + Email
            if lead.get("phone"):
                try:
                    self.caller.make_outbound_call(lead)
                except Exception as e:
                    print(f"    [Call Failed] {e}")
            
            self.outreach.send_followup(lead, followup_num)
            
            # Update follow-up count
            self.state.update_lead(
                lead.get("email") or lead.get("phone"),
                {
                    "followup_count": followup_num,
                    f"followup_{followup_num}_at": datetime.utcnow().isoformat()
                }
            )
            
            # If max follow-ups reached, mark as cold
            if followup_num >= len(FOLLOWUP_SCHEDULE):
                self.state.update_lead(
                    lead.get("email") or lead.get("phone"),
                    {"stage": "cold"}
                )
                print(f"    → Marked as cold after {followup_num} follow-ups")
            
            time.sleep(30)

    def handle_response(self, lead_identifier: str, message: str, channel: str = "whatsapp"):
        """
        Call this when a lead responds (via WhatsApp webhook, email reply, etc.)
        
        Args:
            lead_identifier: email or phone number
            message: what the prospect said
            channel: "call" | "email" | "whatsapp"
        """
        leads = self.state.load_all()
        lead = next((l for l in leads if l.get("email") == lead_identifier or l.get("phone") == lead_identifier), None)
        
        if not lead:
            print(f"[Warning] Lead not found: {lead_identifier}")
            return None
        
        result = self.agent_brain.chat(lead, message, channel=channel)
        
        print(f"  [AI Response] Stage: {result['stage']} | Action: {result['action']}")
        
        # Update stage in state
        self.state.update_lead(lead_identifier, {"stage": result["stage"]})
        
        # Handle actions
        if result["action"] == "send_quote":
            package = result.get("suggested_package") or "growth"
            self.outreach.send_quote(lead, package)
            print(f"  [Quote] Sent {package} package to {lead['name']}")
        
        elif result["action"] == "close":
            package = result.get("suggested_package") or "growth"
            self.closer.close_deal(lead, package)
        
        elif result["action"] == "human_handoff":
            self.handoff.alert(lead, "Prospect requested specific info beyond AI scope", message)
        
        return result["response"]


# ── Entry Point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    orchestrator = SalesAgentOrchestrator()
    orchestrator.start()
