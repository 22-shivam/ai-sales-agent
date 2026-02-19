"""
MODULE 2: AI AGENT BRAIN
========================
LangChain-powered sales agent for digital marketing / e-commerce clients.
Handles:
  - Discovery questions (identify pain points)
  - Dynamic pitch generation (website, SEO, Google Ads)
  - Objection handling
  - Quote generation
  - Deal closing logic
  - Conversation memory per lead
"""

import os
import json
from typing import Optional
from langchain_openai import ChatOpenAI
from langchain.memory import ConversationBufferWindowMemory
from langchain.schema import SystemMessage, HumanMessage, AIMessage
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

# ── Config ────────────────────────────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Your service packages (customize these)
SERVICE_PACKAGES = {
    "starter": {
        "name": "Starter Growth Package",
        "price": 15000,
        "currency": "INR",
        "includes": ["Basic SEO setup", "5-page website redesign", "Google My Business setup"],
        "best_for": "Small e-commerce with no online presence"
    },
    "growth": {
        "name": "E-Commerce Growth Package",
        "price": 35000,
        "currency": "INR",
        "includes": ["Full SEO strategy", "Shopify/WooCommerce optimization", "Google Ads (₹10k ad budget mgmt)", "Monthly reporting"],
        "best_for": "Stores with site but low traffic"
    },
    "premium": {
        "name": "Premium Scale Package",
        "price": 75000,
        "currency": "INR",
        "includes": ["Full website rebuild", "Advanced SEO", "Google + Meta Ads", "Conversion rate optimization", "Dedicated account manager"],
        "best_for": "Growing stores wanting aggressive scale"
    }
}

SYSTEM_PROMPT = """
You are Aryan, a senior sales consultant at DigitalBoost Agency — a digital marketing company 
specializing in website development and SEO for e-commerce businesses.

Your personality:
- Warm, confident, consultative (never pushy)
- You ask smart questions before pitching
- You LISTEN and reflect their pain back to them
- You speak like a human, not a robot
- On calls: short sentences, natural pauses, no bullet points
- On email/chat: slightly more structured

Your services:
{services}

Your goal flow:
1. DISCOVERY: Ask 2-3 questions to understand their situation
2. IDENTIFY PAIN: Reflect their problems back ("So it sounds like your main issue is X")
3. PITCH: Recommend the right package based on their pain
4. HANDLE OBJECTIONS: Address concerns confidently
5. CLOSE: Ask for the commitment, send quote

Rules:
- Never quote price before understanding their pain
- Always tie price to ROI ("₹35k/month that drives ₹2L+ in new revenue")
- If they say "not interested", uncover the real objection
- If they say "send me info", treat as warm lead, schedule a follow-up call
- If they agree, confirm details and say you'll send contract via email

Lead context:
Name: {lead_name}
Website: {lead_website}  
Known pain points: {pain_points}
City: {lead_city}
"""


# ── Sales Agent Brain ─────────────────────────────────────────────────────────
class SalesAgentBrain:
    def __init__(self):
        self.llm = ChatOpenAI(
            model="gpt-4o",
            api_key=OPENAI_API_KEY,
            temperature=0.7,
        )
        self.memories: dict[str, ConversationBufferWindowMemory] = {}  # per lead
        self.lead_stages: dict[str, str] = {}

    def _get_memory(self, lead_id: str) -> ConversationBufferWindowMemory:
        if lead_id not in self.memories:
            self.memories[lead_id] = ConversationBufferWindowMemory(
                k=20,  # last 20 turns
                return_messages=True,
                memory_key="history"
            )
        return self.memories[lead_id]

    def _build_system_prompt(self, lead: dict) -> str:
        services_str = json.dumps(SERVICE_PACKAGES, indent=2)
        pain_points = ", ".join(lead.get("pain_points", [])) or "unknown — need to discover"
        return SYSTEM_PROMPT.format(
            services=services_str,
            lead_name=lead.get("name", "there"),
            lead_website=lead.get("website", "unknown"),
            pain_points=pain_points,
            lead_city=lead.get("city", "")
        )

    def chat(self, lead: dict, user_message: str, channel: str = "call") -> dict:
        """
        Process one turn of conversation.
        
        Args:
            lead: Lead dict from leads.json
            user_message: What the prospect just said
            channel: "call" | "email" | "whatsapp"
        
        Returns:
            {
                "response": str,       # what the AI says next
                "stage": str,          # current sales stage
                "action": str,         # "continue" | "send_quote" | "close" | "human_handoff"
                "suggested_package": str | None
            }
        """
        lead_id = lead.get("email") or lead.get("phone") or lead.get("name")
        memory = self._get_memory(lead_id)
        
        # Build messages
        system = self._build_system_prompt(lead)
        history = memory.load_memory_variables({})["history"]
        
        messages = [SystemMessage(content=system)] + history + [HumanMessage(content=user_message)]
        
        # Add channel instruction
        if channel == "call":
            messages[0].content += "\n\nIMPORTANT: This is a PHONE CALL. Keep responses under 3 sentences. Sound natural and conversational."
        elif channel == "email":
            messages[0].content += "\n\nIMPORTANT: This is an EMAIL. Be professional but warm. Use proper paragraphs."
        elif channel == "whatsapp":
            messages[0].content += "\n\nIMPORTANT: This is WHATSAPP. Keep it casual, short, use minimal formatting."

        response = self.llm.invoke(messages)
        ai_response = response.content

        # Save to memory
        memory.save_context({"input": user_message}, {"output": ai_response})

        # Detect stage + next action
        stage, action, package = self._detect_stage(ai_response, user_message, lead_id)

        return {
            "response": ai_response,
            "stage": stage,
            "action": action,
            "suggested_package": package
        }

    def _detect_stage(self, ai_response: str, user_msg: str, lead_id: str) -> tuple:
        """Simple rule-based stage detector (can be upgraded to LLM classifier)."""
        lower_ai = ai_response.lower()
        lower_user = user_msg.lower()

        # Detect close signals
        if any(w in lower_user for w in ["yes", "let's do it", "sounds good", "proceed", "go ahead", "confirm"]):
            self.lead_stages[lead_id] = "closed"
            return "closed", "close", self._detect_package(ai_response)

        # Detect quote request
        if any(w in lower_ai for w in ["₹", "package", "inr", "pricing", "investment"]):
            self.lead_stages[lead_id] = "pitched"
            return "pitched", "send_quote", self._detect_package(ai_response)

        # Detect human handoff needed
        if any(w in lower_user for w in ["legal", "contract terms", "refund policy", "case study", "reference"]):
            return "qualified", "human_handoff", None

        # Detect discovery
        if "?" in ai_response and self.lead_stages.get(lead_id) in (None, "new", "contacted"):
            self.lead_stages[lead_id] = "discovery"
            return "discovery", "continue", None

        current = self.lead_stages.get(lead_id, "contacted")
        return current, "continue", None

    def _detect_package(self, text: str) -> Optional[str]:
        text_lower = text.lower()
        if "premium" in text_lower or "75" in text_lower:
            return "premium"
        if "growth" in text_lower or "35" in text_lower:
            return "growth"
        if "starter" in text_lower or "15" in text_lower:
            return "starter"
        return None

    def generate_opening_message(self, lead: dict, channel: str = "call") -> str:
        """Generate the very first message for a cold outreach."""
        pain = lead.get("pain_points", [])
        pain_str = pain[0] if pain else "limited online visibility"
        
        prompts = {
            "call": f"Generate a 2-sentence cold call opening for {lead.get('name')} who runs an e-commerce store at {lead.get('website')}. Their known issue: {pain_str}. Be warm and hook them in 10 seconds.",
            "email": f"Write a 3-paragraph cold email to {lead.get('name')} from {lead.get('website')}. Subject line + body. Their pain: {pain_str}. No fluff. Clear value.",
            "whatsapp": f"Write a short WhatsApp message (under 100 words) to {lead.get('name')} from {lead.get('website')}. Their pain: {pain_str}. Casual, no spam vibes.",
        }
        
        msg = self.llm.invoke([HumanMessage(content=prompts[channel])])
        return msg.content

    def generate_followup(self, lead: dict, followup_number: int, channel: str = "email") -> str:
        """Generate follow-up message (Day 2, Day 5, Day 10)."""
        context = {
            1: "They didn't respond to first outreach. Gentle nudge with new insight.",
            2: "Second follow-up. Add social proof or a case study mention.",
            3: "Final follow-up. Create urgency — limited slots this month."
        }
        prompt = f"""
        Generate follow-up #{followup_number} for {lead.get('name')} on {channel}.
        Context: {context.get(followup_number, context[3])}
        Their website: {lead.get('website')}
        Known pain points: {', '.join(lead.get('pain_points', []))}
        Channel tone: {'conversational call script' if channel == 'call' else 'professional ' + channel}
        """
        msg = self.llm.invoke([HumanMessage(content=prompt)])
        return msg.content

    def handle_objection(self, lead: dict, objection: str) -> str:
        """Specialized objection handler."""
        prompt = f"""
        You are Aryan from DigitalBoost Agency.
        A prospect just said: "{objection}"
        Their context: {lead.get('name')}, e-commerce store at {lead.get('website')}, pain points: {lead.get('pain_points')}
        
        Respond to this objection in 2-3 sentences. Be empathetic, reframe, and move toward close.
        Don't be pushy. Use logic + social proof.
        """
        msg = self.llm.invoke([HumanMessage(content=prompt)])
        return msg.content


# ── Quote Generator ───────────────────────────────────────────────────────────
class QuoteGenerator:
    def generate(self, lead: dict, package_key: str) -> dict:
        """Generate a structured quote for sending via email/DocuSign."""
        package = SERVICE_PACKAGES.get(package_key, SERVICE_PACKAGES["growth"])
        
        return {
            "client_name": lead.get("name"),
            "client_email": lead.get("email"),
            "client_website": lead.get("website"),
            "package": package["name"],
            "price": package["price"],
            "currency": package["currency"],
            "includes": package["includes"],
            "validity": "7 days",
            "generated_at": __import__("datetime").datetime.utcnow().isoformat(),
            "payment_link": f"https://pay.stripe.com/your-link/{package_key}",  # replace with real Stripe link
        }


# ── Quick Test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    agent = SalesAgentBrain()
    
    # Simulate a lead
    test_lead = {
        "name": "Rahul Sharma",
        "email": "rahul@fashionstore.in",
        "phone": "+919876543210",
        "website": "https://fashionstore.in",
        "city": "Mumbai",
        "pain_points": ["slow website speed", "poor SEO ranking"],
        "stage": "new"
    }
    
    print("=== Generating Opening Call Script ===")
    opening = agent.generate_opening_message(test_lead, channel="call")
    print(opening)
    
    print("\n=== Simulating Conversation ===")
    turns = [
        "Yes, who's this?",
        "We do have a website but we barely get any sales from it.",
        "Our Google ranking is terrible, we're on page 5.",
        "What would this cost?",
        "That sounds reasonable. Can you send me the details?"
    ]
    
    for turn in turns:
        print(f"\nProspect: {turn}")
        result = agent.chat(test_lead, turn, channel="call")
        print(f"Aryan: {result['response']}")
        print(f"[Stage: {result['stage']} | Action: {result['action']}]")
        
        if result["action"] == "send_quote":
            qg = QuoteGenerator()
            quote = qg.generate(test_lead, result["suggested_package"] or "growth")
            print(f"\n📄 Quote generated: {quote['package']} — ₹{quote['price']:,}")
            break
