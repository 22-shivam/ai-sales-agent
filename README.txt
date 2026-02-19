# AI Sales Agent — Setup Guide
# ================================
# Digital Marketing Agency — E-Commerce Lead Machine

# ── INSTALL DEPENDENCIES ──────────────────────────────────────────────────────
pip install \
  langchain langchain-openai langchain-core \
  openai \
  fastapi uvicorn \
  sendgrid \
  twilio \
  apscheduler \
  httpx \
  requests \
  stripe \
  python-dotenv

# ── ENVIRONMENT VARIABLES (.env) ──────────────────────────────────────────────
# Copy this to a .env file and fill in your keys

OPENAI_API_KEY=sk-...                    # OpenAI — GPT-4o brain
GOOGLE_PLACES_API_KEY=AIza...            # Google Cloud Console (free tier available)
PAGESPEED_API_KEY=AIza...                # Same Google project, free
APOLLO_API_KEY=...                       # apollo.io — free tier: 50 leads/mo
HUBSPOT_API_KEY=...                      # HubSpot free CRM API
SENDGRID_API_KEY=SG...                   # SendGrid — 100 emails/day free
SENDGRID_FROM_EMAIL=you@yourdomain.com   # Must be verified in SendGrid
TWILIO_ACCOUNT_SID=AC...                 # Twilio Console
TWILIO_AUTH_TOKEN=...                    # Twilio Console
TWILIO_PHONE_NUMBER=+1...                # Buy a Twilio number (~$1/mo)
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886  # Twilio WhatsApp Sandbox
VAPI_API_KEY=...                         # vapi.ai — pay per minute (~$0.05/min)
VAPI_PHONE_NUMBER_ID=...                 # Create in Vapi dashboard
WEBHOOK_BASE_URL=https://yourserver.com  # Your server URL (use ngrok for dev)
PANDADOC_API_KEY=...                     # PandaDoc for contracts (free trial)
PANDADOC_TEMPLATE_ID=...                 # Create a contract template in PandaDoc
STRIPE_SECRET_KEY=sk_live_...            # Stripe for payments
SLACK_WEBHOOK_URL=https://hooks.slack.com/...  # For human handoff alerts
N8N_FOLLOWUP_WEBHOOK_URL=...             # Optional: n8n for extra automation
ONBOARDING_WEBHOOK_URL=...               # Your onboarding system webhook

# ── HOW TO RUN ────────────────────────────────────────────────────────────────

# STEP 1: Source & score leads
python module1_lead_sourcing.py

# STEP 2: Start webhook server (in one terminal)
python module3_voice_agent.py
# Expose with ngrok: ngrok http 8000
# Set WEBHOOK_BASE_URL to your ngrok URL

# STEP 3: Start the main orchestrator (in another terminal)
python module5_orchestrator.py

# ── ARCHITECTURE ──────────────────────────────────────────────────────────────
#
#  module1_lead_sourcing.py    → Finds e-commerce leads (Google Maps + Apollo)
#  module2_agent_brain.py      → GPT-4o brain (discovery, pitch, objections, close)
#  module3_voice_agent.py      → Vapi.ai voice calls + webhook server
#  module4_outreach.py         → Email (SendGrid) + WhatsApp/SMS (Twilio)
#  module5_orchestrator.py     → Scheduler + pipeline controller + deal closing
#
# DATA FLOW:
#  leads.json → Orchestrator → Call + Email + WhatsApp → Track Responses
#       ↓               ↓
#   HubSpot          Follow-ups (Day 2, 5, 10)
#       ↓
#   Quote → Contract (PandaDoc) → Payment (Stripe) → Onboarding

# ── ESTIMATED COSTS (per month at 200 leads) ─────────────────────────────────
#  GPT-4o API:        ~$15-30
#  Vapi calling:      ~$20-50 (depends on call length)
#  Twilio WhatsApp:   ~$5-10
#  SendGrid email:    Free (under 100/day) or ~$15
#  Apollo.io:         Free (50/mo) or $49 basic
#  TOTAL:             ~$50–120/month to automate a full sales team 🚀

# ── HUMAN HANDOFF TRIGGERS ────────────────────────────────────────────────────
#  - Prospect asks for case studies / references
#  - Prospect asks about contracts / legal
#  - Deal value > ₹1,00,000/mo
#  - 3+ back-and-forth objections
#  → Slack alert sent with full transcript

# ── CUSTOMIZATION CHECKLIST ───────────────────────────────────────────────────
# [ ] Update SERVICE_PACKAGES in module2_agent_brain.py with your real pricing
# [ ] Update SYSTEM_PROMPT with your company name + real value props
# [ ] Create PandaDoc contract template + get template ID
# [ ] Set up Stripe products/prices for each package
# [ ] Create HubSpot account + get API key
# [ ] Verify sender email in SendGrid
# [ ] Buy Twilio number + apply for WhatsApp Business (or use sandbox for testing)
# [ ] Create Vapi account + add phone number
# [ ] Deploy to VPS (DigitalOcean, AWS EC2, Railway) for 24/7 operation
