"""
MODULE 4: EMAIL + WHATSAPP OUTREACH
=====================================
Handles all written communication channels:
  - Personalized cold emails (SendGrid)
  - WhatsApp messages (Twilio)
  - SMS fallback (Twilio)
  - Quote emails with PDF attachment
  - Email open/click tracking

pip install sendgrid twilio jinja2
"""

import os
from datetime import datetime
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition
from twilio.rest import Client as TwilioClient
from module2_agent_brain import SalesAgentBrain, QuoteGenerator
import base64
import json

# ── Config ────────────────────────────────────────────────────────────────────
SENDGRID_API_KEY      = os.getenv("SENDGRID_API_KEY")
SENDGRID_FROM_EMAIL   = os.getenv("SENDGRID_FROM_EMAIL", "aryan@digitalboost.in")
SENDGRID_FROM_NAME    = "Aryan | DigitalBoost Agency"

TWILIO_ACCOUNT_SID    = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN     = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER   = os.getenv("TWILIO_PHONE_NUMBER")      # +1XXXXXXXXXX (Twilio SMS)
TWILIO_WHATSAPP_FROM  = os.getenv("TWILIO_WHATSAPP_FROM")     # whatsapp:+14155238886 (Sandbox or approved)


# ── Email Manager ─────────────────────────────────────────────────────────────
class EmailManager:
    def __init__(self):
        self.sg = SendGridAPIClient(SENDGRID_API_KEY)
        self.agent_brain = SalesAgentBrain()

    def send_cold_email(self, lead: dict) -> bool:
        """Send a personalized cold outreach email."""
        content = self.agent_brain.generate_opening_message(lead, channel="email")
        
        # Split subject from body (GPT returns "Subject: ...\n\nBody...")
        lines = content.strip().split("\n")
        subject = ""
        body_lines = []
        
        for i, line in enumerate(lines):
            if line.lower().startswith("subject:"):
                subject = line.replace("Subject:", "").replace("subject:", "").strip()
            else:
                body_lines.append(line)
        
        if not subject:
            subject = f"Quick question about {lead.get('website', 'your store')}"
        
        body_html = self._text_to_html("\n".join(body_lines))
        
        return self._send(
            to_email=lead["email"],
            to_name=lead.get("name", ""),
            subject=subject,
            html_content=body_html,
            lead_id=lead.get("email"),
            email_type="cold_outreach"
        )

    def send_quote_email(self, lead: dict, package_key: str) -> bool:
        """Send a professional quote email with pricing details."""
        qg = QuoteGenerator()
        quote = qg.generate(lead, package_key)
        
        subject = f"Your Custom Growth Proposal — {quote['package']}"
        html = self._build_quote_html(quote, lead)
        
        return self._send(
            to_email=lead["email"],
            to_name=lead.get("name", ""),
            subject=subject,
            html_content=html,
            lead_id=lead.get("email"),
            email_type="quote"
        )

    def send_followup_email(self, lead: dict, followup_number: int) -> bool:
        """Send a follow-up email (Day 2 / Day 5 / Day 10)."""
        content = self.agent_brain.generate_followup(lead, followup_number, channel="email")
        
        lines = content.strip().split("\n")
        subject = f"Re: Your e-commerce growth — follow-up #{followup_number}"
        body = "\n".join(lines)
        
        for line in lines:
            if line.lower().startswith("subject:"):
                subject = line.split(":", 1)[1].strip()
                body = "\n".join([l for l in lines if not l.lower().startswith("subject:")])
                break
        
        return self._send(
            to_email=lead["email"],
            to_name=lead.get("name", ""),
            subject=subject,
            html_content=self._text_to_html(body),
            lead_id=lead.get("email"),
            email_type=f"followup_{followup_number}"
        )

    def _send(self, to_email: str, to_name: str, subject: str,
              html_content: str, lead_id: str = "", email_type: str = "") -> bool:
        message = Mail(
            from_email=(SENDGRID_FROM_EMAIL, SENDGRID_FROM_NAME),
            to_emails=[(to_email, to_name)],
            subject=subject,
            html_content=html_content
        )
        # Add tracking category for analytics
        message.category = [email_type]
        message.custom_arg = {"lead_id": lead_id, "email_type": email_type}
        
        try:
            response = self.sg.send(message)
            print(f"  [Email] Sent '{email_type}' to {to_email} — Status: {response.status_code}")
            return response.status_code in (200, 201, 202)
        except Exception as e:
            print(f"  [Email] Failed to send to {to_email}: {e}")
            return False

    def _text_to_html(self, text: str) -> str:
        """Convert plain text to clean HTML email."""
        paragraphs = [p for p in text.split("\n\n") if p.strip()]
        html_parts = ["<div style='font-family: Arial, sans-serif; font-size: 15px; line-height: 1.6; color: #333; max-width: 600px;'>"]
        for p in paragraphs:
            html_parts.append(f"<p>{p.replace(chr(10), '<br>')}</p>")
        html_parts.append("""
            <hr style='border: none; border-top: 1px solid #eee; margin-top: 24px;'>
            <p style='font-size: 13px; color: #888;'>
                Aryan | Senior Sales Consultant<br>
                DigitalBoost Agency | Website & SEO for E-Commerce<br>
                <a href='mailto:aryan@digitalboost.in'>aryan@digitalboost.in</a>
            </p>
        """)
        html_parts.append("</div>")
        return "".join(html_parts)

    def _build_quote_html(self, quote: dict, lead: dict) -> str:
        includes_html = "".join([f"<li>✓ {item}</li>" for item in quote["includes"]])
        return f"""
        <div style='font-family: Arial, sans-serif; max-width: 640px; color: #222;'>
          <h2 style='color: #4f46e5;'>Your Custom Growth Proposal</h2>
          <p>Hi {lead.get('name', '').split()[0]},</p>
          <p>As discussed, here's your tailored proposal for <strong>{lead.get('website')}</strong>:</p>
          
          <div style='background: #f5f3ff; border-left: 4px solid #4f46e5; padding: 20px; border-radius: 8px; margin: 20px 0;'>
            <h3 style='margin: 0 0 8px; color: #4f46e5;'>{quote['package']}</h3>
            <p style='font-size: 28px; font-weight: bold; margin: 0;'>₹{quote['price']:,}<span style='font-size: 14px; font-weight: normal;'>/month</span></p>
          </div>
          
          <h4>What's included:</h4>
          <ul style='line-height: 2;'>{includes_html}</ul>
          
          <p><strong>Valid for:</strong> {quote['validity']}</p>
          
          <a href='{quote['payment_link']}' style='background: #4f46e5; color: white; padding: 14px 28px; border-radius: 8px; text-decoration: none; font-size: 16px; display: inline-block; margin: 16px 0;'>
            Accept & Pay Now →
          </a>
          
          <p style='font-size: 13px; color: #666;'>Questions? Just reply to this email or call/WhatsApp me directly.</p>
          
          <hr style='border: none; border-top: 1px solid #eee; margin-top: 24px;'>
          <p style='font-size: 13px; color: #888;'>Aryan | DigitalBoost Agency</p>
        </div>
        """


# ── WhatsApp + SMS Manager ────────────────────────────────────────────────────
class WhatsAppManager:
    def __init__(self):
        self.client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        self.agent_brain = SalesAgentBrain()

    def send_cold_whatsapp(self, lead: dict) -> bool:
        """Send first WhatsApp message."""
        message = self.agent_brain.generate_opening_message(lead, channel="whatsapp")
        return self._send_whatsapp(lead["phone"], message)

    def send_followup_whatsapp(self, lead: dict, followup_number: int) -> bool:
        """Send a follow-up WhatsApp message."""
        message = self.agent_brain.generate_followup(lead, followup_number, channel="whatsapp")
        return self._send_whatsapp(lead["phone"], message)

    def send_quote_whatsapp(self, lead: dict, package_key: str) -> bool:
        """Send a short quote summary over WhatsApp with payment link."""
        from module2_agent_brain import QuoteGenerator, SERVICE_PACKAGES
        qg = QuoteGenerator()
        quote = qg.generate(lead, package_key)
        pkg = SERVICE_PACKAGES.get(package_key, {})
        
        message = (
            f"Hi {lead.get('name', '').split()[0]}! 👋\n\n"
            f"Here's your proposal:\n\n"
            f"📦 *{quote['package']}*\n"
            f"💰 ₹{quote['price']:,}/month\n\n"
            f"Includes:\n" +
            "\n".join([f"✅ {item}" for item in quote["includes"]]) +
            f"\n\n🔗 To proceed: {quote['payment_link']}\n\n"
            f"Valid for 7 days. Any questions? Just reply here! 🙏"
        )
        return self._send_whatsapp(lead["phone"], message)

    def send_sms(self, lead: dict, message: str) -> bool:
        """Send SMS as fallback."""
        try:
            msg = self.client.messages.create(
                body=message[:1600],
                from_=TWILIO_PHONE_NUMBER,
                to=lead["phone"]
            )
            print(f"  [SMS] Sent to {lead['phone']} — SID: {msg.sid}")
            return True
        except Exception as e:
            print(f"  [SMS] Failed: {e}")
            return False

    def _send_whatsapp(self, phone: str, message: str) -> bool:
        """Send a WhatsApp message via Twilio."""
        try:
            msg = self.client.messages.create(
                body=message,
                from_=TWILIO_WHATSAPP_FROM,
                to=f"whatsapp:{phone}"
            )
            print(f"  [WhatsApp] Sent to {phone} — SID: {msg.sid}")
            return True
        except Exception as e:
            print(f"  [WhatsApp] Failed to {phone}: {e}")
            return False

    def handle_inbound_whatsapp(self, from_number: str, message_body: str) -> str:
        """
        Handle incoming WhatsApp replies.
        Returns AI response to send back.
        Plug this into your Twilio webhook.
        """
        # Load lead from DB/file by phone number
        lead = self._find_lead_by_phone(from_number)
        if not lead:
            lead = {"name": "there", "phone": from_number, "pain_points": [], "stage": "new"}
        
        result = self.agent_brain.chat(lead, message_body, channel="whatsapp")
        return result["response"]

    def _find_lead_by_phone(self, phone: str) -> dict | None:
        """Look up lead from leads.json by phone."""
        try:
            with open("leads.json") as f:
                leads = json.load(f)
            for lead in leads:
                if lead.get("phone") == phone or lead.get("phone") == phone.replace("+", ""):
                    return lead
        except FileNotFoundError:
            pass
        return None


# ── Unified Outreach Orchestrator ─────────────────────────────────────────────
class OutreachOrchestrator:
    """
    Decides the best channel for each lead and sends the right message.
    Priority: Call first → WhatsApp → Email → SMS
    """
    def __init__(self):
        self.email_mgr  = EmailManager()
        self.wa_mgr     = WhatsAppManager()

    def initial_outreach(self, lead: dict) -> dict:
        """Send first contact across all available channels."""
        results = {}
        
        # 1. Email (if available)
        if lead.get("email"):
            results["email"] = self.email_mgr.send_cold_email(lead)
        
        # 2. WhatsApp (if phone available)
        if lead.get("phone"):
            results["whatsapp"] = self.wa_mgr.send_cold_whatsapp(lead)
        
        print(f"  [Outreach] {lead['name']} — {results}")
        return results

    def send_quote(self, lead: dict, package_key: str) -> dict:
        """Send quote via email + WhatsApp."""
        results = {}
        if lead.get("email"):
            results["email"] = self.email_mgr.send_quote_email(lead, package_key)
        if lead.get("phone"):
            results["whatsapp"] = self.wa_mgr.send_quote_whatsapp(lead, package_key)
        return results

    def send_followup(self, lead: dict, followup_number: int) -> dict:
        """Send follow-up across channels."""
        results = {}
        if lead.get("email"):
            results["email"] = self.email_mgr.send_followup_email(lead, followup_number)
        if lead.get("phone"):
            results["whatsapp"] = self.wa_mgr.send_followup_whatsapp(lead, followup_number)
        return results


# ── Quick Test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    orchestrator = OutreachOrchestrator()
    
    test_lead = {
        "name": "Priya Mehta",
        "email": "priya@fashionstore.in",
        "phone": "+919876543210",
        "website": "https://fashionstore.in",
        "city": "Bangalore",
        "pain_points": ["poor SEO ranking", "low conversion rate"],
        "stage": "new"
    }
    
    print("=== Initial Outreach ===")
    results = orchestrator.initial_outreach(test_lead)
    print(f"Results: {results}")
