"""
MODULE 1: LEAD SOURCING
=======================
Sources e-commerce leads from:
  - Google Maps (local e-commerce / retail stores)
  - Apollo.io API (decision makers + emails)
  - SEO weakness scanner (sites with bad scores = hot prospects)

Output: leads saved to leads.json + HubSpot CRM
"""

import os
import json
import time
import requests
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import Optional
import urllib.parse

# ── Config ────────────────────────────────────────────────────────────────────
GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")
APOLLO_API_KEY        = os.getenv("APOLLO_API_KEY")
HUBSPOT_API_KEY       = os.getenv("HUBSPOT_API_KEY")
PAGESPEED_API_KEY     = os.getenv("PAGESPEED_API_KEY")   # free from Google Console


@dataclass
class Lead:
    name: str
    website: str
    phone: str
    email: str
    city: str
    source: str                        # "google_maps" | "apollo" | "manual"
    seo_score: Optional[int] = None    # 0–100, lower = hotter lead
    pagespeed_score: Optional[int] = None
    has_google_ads: Optional[bool] = None
    pain_points: list = None           # populated during discovery
    stage: str = "new"                 # new → contacted → qualified → pitched → closed
    created_at: str = ""

    def __post_init__(self):
        if self.pain_points is None:
            self.pain_points = []
        if not self.created_at:
            self.created_at = datetime.utcnow().isoformat()


# ── Source 1: Google Maps (Places API) ───────────────────────────────────────
class GoogleMapsLeadScraper:
    BASE_URL = "https://maps.googleapis.com/maps/api/place"

    def __init__(self):
        self.api_key = GOOGLE_PLACES_API_KEY

    def search_leads(self, query: str, location: str, max_results: int = 50) -> list[Lead]:
        """
        Example:
            scraper.search_leads("online clothing store", "Mumbai", max_results=50)
        """
        leads = []
        params = {
            "query": f"{query} in {location}",
            "key": self.api_key,
            "type": "store"
        }
        url = f"{self.BASE_URL}/textsearch/json"
        
        while len(leads) < max_results:
            resp = requests.get(url, params=params).json()
            
            for place in resp.get("results", []):
                details = self._get_place_details(place["place_id"])
                lead = Lead(
                    name=place.get("name", ""),
                    website=details.get("website", ""),
                    phone=details.get("formatted_phone_number", ""),
                    email="",           # enriched via Apollo in step 2
                    city=location,
                    source="google_maps"
                )
                leads.append(lead)
                if len(leads) >= max_results:
                    break
            
            next_page = resp.get("next_page_token")
            if not next_page:
                break
            params = {"pagetoken": next_page, "key": self.api_key}
            time.sleep(2)  # Google requires delay before next_page_token works
        
        print(f"[Google Maps] Found {len(leads)} leads in {location}")
        return leads

    def _get_place_details(self, place_id: str) -> dict:
        resp = requests.get(
            f"{self.BASE_URL}/details/json",
            params={"place_id": place_id, "fields": "website,formatted_phone_number", "key": self.api_key}
        ).json()
        return resp.get("result", {})


# ── Source 2: Apollo.io – Email + Decision Maker Enrichment ──────────────────
class ApolloEnricher:
    BASE_URL = "https://api.apollo.io/v1"

    def __init__(self):
        self.headers = {
            "Content-Type": "application/json",
            "x-api-key": APOLLO_API_KEY
        }

    def enrich_lead(self, lead: Lead) -> Lead:
        """Find the email + decision maker name for a given website domain."""
        if not lead.website:
            return lead
        
        domain = urllib.parse.urlparse(lead.website).netloc.replace("www.", "")
        
        payload = {
            "domain": domain,
            "titles": ["CEO", "Founder", "Marketing Manager", "Owner", "CMO", "Head of Marketing"]
        }
        resp = requests.post(f"{self.BASE_URL}/mixed_people/search", headers=self.headers, json=payload).json()
        people = resp.get("people", [])
        
        if people:
            top = people[0]
            lead.name = top.get("name", lead.name)
            lead.email = top.get("email", "")
            print(f"  [Apollo] Enriched: {lead.name} <{lead.email}> @ {domain}")
        
        return lead

    def search_ecommerce_companies(self, industry: str = "ecommerce", country: str = "India", max: int = 100) -> list[Lead]:
        """Search Apollo directly for e-commerce companies."""
        payload = {
            "q_organization_keyword_tags": [industry, "online store", "shopify"],
            "organization_locations": [country],
            "person_titles": ["CEO", "Founder", "Owner", "Marketing Head"],
            "per_page": min(max, 100)
        }
        resp = requests.post(f"{self.BASE_URL}/mixed_people/search", headers=self.headers, json=payload).json()
        leads = []
        
        for person in resp.get("people", []):
            org = person.get("organization", {})
            leads.append(Lead(
                name=person.get("name", ""),
                website=org.get("website_url", ""),
                phone=person.get("phone", ""),
                email=person.get("email", ""),
                city=org.get("city", ""),
                source="apollo"
            ))
        
        print(f"[Apollo] Found {len(leads)} e-commerce leads")
        return leads


# ── Source 3: SEO & PageSpeed Scorer (hotter leads = worse scores) ───────────
class SEOScorer:
    def score_lead(self, lead: Lead) -> Lead:
        """
        Scores a lead's website using:
          - Google PageSpeed API (performance score)
        Lower score = more pain = hotter prospect for your pitch.
        """
        if not lead.website:
            return lead
        
        url = (
            f"https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
            f"?url={urllib.parse.quote(lead.website)}&strategy=mobile&key={PAGESPEED_API_KEY}"
        )
        try:
            resp = requests.get(url, timeout=15).json()
            categories = resp.get("lighthouseResult", {}).get("categories", {})
            perf = categories.get("performance", {}).get("score", 1)
            seo  = categories.get("seo", {}).get("score", 1)
            
            lead.pagespeed_score = int(perf * 100)
            lead.seo_score       = int(seo * 100)
            
            # Auto-tag pain points based on scores
            if lead.pagespeed_score < 50:
                lead.pain_points.append("slow website speed")
            if lead.seo_score < 60:
                lead.pain_points.append("poor SEO ranking")
            
            print(f"  [SEO] {lead.website} → Speed: {lead.pagespeed_score}, SEO: {lead.seo_score}")
        except Exception as e:
            print(f"  [SEO] Failed for {lead.website}: {e}")
        
        return lead

    def prioritize(self, leads: list[Lead]) -> list[Lead]:
        """Sort leads: worst SEO + worst speed first (hottest prospects)."""
        def score(l):
            s = (l.seo_score or 100) + (l.pagespeed_score or 100)
            return s
        return sorted(leads, key=score)


# ── HubSpot CRM Sync ──────────────────────────────────────────────────────────
class HubSpotSync:
    BASE_URL = "https://api.hubapi.com/crm/v3"

    def __init__(self):
        self.headers = {
            "Authorization": f"Bearer {HUBSPOT_API_KEY}",
            "Content-Type": "application/json"
        }

    def upsert_contact(self, lead: Lead) -> str:
        """Create or update a contact in HubSpot. Returns contact ID."""
        payload = {
            "properties": {
                "firstname": lead.name.split()[0] if lead.name else "",
                "lastname":  " ".join(lead.name.split()[1:]) if lead.name else "",
                "email":     lead.email,
                "phone":     lead.phone,
                "website":   lead.website,
                "city":      lead.city,
                "hs_lead_status": lead.stage.upper(),
                "lead_source": lead.source,
                "notes_last_contacted": ", ".join(lead.pain_points)
            }
        }
        # Try create, fallback to update
        resp = requests.post(f"{self.BASE_URL}/objects/contacts", headers=self.headers, json=payload)
        if resp.status_code == 409:
            contact_id = resp.json().get("message", "").split("ID: ")[-1]
            requests.patch(f"{self.BASE_URL}/objects/contacts/{contact_id}", headers=self.headers, json=payload)
            return contact_id
        return resp.json().get("id", "")


# ── Main Pipeline ─────────────────────────────────────────────────────────────
class LeadSourcingPipeline:
    def __init__(self):
        self.maps_scraper = GoogleMapsLeadScraper()
        self.apollo       = ApolloEnricher()
        self.seo_scorer   = SEOScorer()
        self.hubspot      = HubSpotSync()

    def run(self, cities: list[str] = None, max_leads: int = 200) -> list[Lead]:
        if cities is None:
            cities = ["Mumbai", "Delhi", "Bangalore", "Hyderabad", "Chennai"]
        
        all_leads: list[Lead] = []

        # 1. Google Maps
        print("\n=== STEP 1: Google Maps Scraping ===")
        for city in cities:
            leads = self.maps_scraper.search_leads("ecommerce store", city, max_results=20)
            all_leads.extend(leads)

        # 2. Apollo direct search
        print("\n=== STEP 2: Apollo.io Search ===")
        apollo_leads = self.apollo.search_ecommerce_companies(max=100)
        all_leads.extend(apollo_leads)

        # 3. Enrich emails (for Google Maps leads missing email)
        print("\n=== STEP 3: Email Enrichment ===")
        for lead in all_leads:
            if not lead.email and lead.website:
                lead = self.apollo.enrich_lead(lead)

        # 4. Score SEO (batch, rate-limited)
        print("\n=== STEP 4: SEO Scoring ===")
        for i, lead in enumerate(all_leads):
            if lead.website:
                all_leads[i] = self.seo_scorer.score_lead(lead)
            time.sleep(0.5)  # rate limit

        # 5. Prioritize hottest leads
        all_leads = self.seo_scorer.prioritize(all_leads)

        # 6. Save locally
        with open("leads.json", "w") as f:
            json.dump([asdict(l) for l in all_leads], f, indent=2)
        print(f"\n✅ Saved {len(all_leads)} leads to leads.json")

        # 7. Sync to HubSpot
        print("\n=== STEP 5: HubSpot CRM Sync ===")
        for lead in all_leads[:max_leads]:
            self.hubspot.upsert_contact(lead)
        print(f"✅ Synced {min(len(all_leads), max_leads)} leads to HubSpot")

        return all_leads


# ── Entry Point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    pipeline = LeadSourcingPipeline()
    leads = pipeline.run(
        cities=["Mumbai", "Delhi", "Bangalore"],
        max_leads=200
    )
    print(f"\nTop 5 hottest leads:")
    for l in leads[:5]:
        print(f"  {l.name} | {l.website} | SEO: {l.seo_score} | Speed: {l.pagespeed_score} | Pain: {l.pain_points}")
