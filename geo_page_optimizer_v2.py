import streamlit as st
import requests
from bs4 import BeautifulSoup
import json
import re
import time
from urllib.parse import urlparse, urljoin
from collections import defaultdict

# ─────────────────────────────────────────────
# PAGE INTENT DETECTION ENGINE
# ─────────────────────────────────────────────

PAGE_INTENTS = {
    "homepage": {
        "label": "🏠 Domain Homepage",
        "description": "Digital storefront — brand trust and navigation hub",
        "primary_frameworks": ["SEO", "AEO", "LLMO"],
        "secondary_frameworks": [],
        "skip_frameworks": ["GEO", "AIO"],
        "skip_reason": "Homepages are for navigation and brand trust, not for answering complex research questions.",
        "optimization_focus": {
            "schema": {"weight": 1.0, "focus": "Organization, LegalService/MedicalBusiness entity — brand identity for AI models"},
            "crawlability": {"weight": 1.0, "focus": "All pages reachable, AI bots allowed, sitemap present"},
            "faq": {"weight": 0.3, "focus": "Light FAQ only (3-5 basic brand questions). Skip deep FAQ."},
            "citability": {"weight": 0.3, "focus": "Entity signals only (address, phone, core service). Skip deep content analysis."},
            "accessibility": {"weight": 1.0, "focus": "Full technical audit — base for entire site"}
        },
        "aeo_checks": True,
        "geo_checks": False,
        "cannibalization_warning": None
    },
    "informational": {
        "label": "📝 Informational Article",
        "description": "Research capture — answer complex questions with citable depth",
        "primary_frameworks": ["AIO", "GEO", "SEO"],
        "secondary_frameworks": ["LLMO"],
        "skip_frameworks": ["VSEO"],
        "skip_reason": "Skip VSEO unless embedding motion graphics explainer video directly into the post.",
        "optimization_focus": {
            "schema": {"weight": 1.0, "focus": "Article, FAQPage, Person (author), BreadcrumbList"},
            "crawlability": {"weight": 0.8, "focus": "Standard checks — heading hierarchy especially important"},
            "faq": {"weight": 1.0, "focus": "Full FAQ extraction and schema generation — feeds AI answer boxes"},
            "citability": {"weight": 1.0, "focus": "MAXIMUM: definitions, statistics, expert quotes, source citations, structured data tables"},
            "accessibility": {"weight": 0.8, "focus": "Readability critical — Flesch-Kincaid Grade 8 target"}
        },
        "aeo_checks": False,
        "geo_checks": True,
        "cannibalization_warning": "⚠️ METRIC CANNIBALIZATION RISK: If you provide the perfect, complete answer at the top (AIO optimization), traditional SEO metrics (clicks) will likely drop. The user gets their answer without visiting your site. Decide if AI Overview brand visibility is worth the trade-off in direct traffic for this query."
    },
    "lead_gen": {
        "label": "🎯 Lead Generation / Service Page",
        "description": "Conversion-focused — drive appointments, calls, form submissions",
        "primary_frameworks": ["SEO", "AEO"],
        "secondary_frameworks": [],
        "skip_frameworks": ["GEO"],
        "skip_reason": "Heavy GEO is counterproductive here. Dense research and citations distract from the conversion goal. Users should fill a form, not read a thesis.",
        "optimization_focus": {
            "schema": {"weight": 1.0, "focus": "LegalService/HealthcareService + LocalBusiness + AggregateRating + FAQ (buying objections only)"},
            "crawlability": {"weight": 0.8, "focus": "Standard — ensure page is indexable"},
            "faq": {"weight": 0.7, "focus": "Buying-objection FAQs only: cost, timeline, eligibility, insurance. NOT deep educational FAQ."},
            "citability": {"weight": 0.3, "focus": "Light touch — trust signals and social proof only. Skip deep citation analysis."},
            "accessibility": {"weight": 1.0, "focus": "CTA visibility, form accessibility, mobile optimization critical"}
        },
        "aeo_checks": True,
        "geo_checks": False,
        "cannibalization_warning": None
    },
    "hybrid": {
        "label": "🔀 Hybrid — Educate & Convert",
        "description": "Must build medical/legal authority (GEO) while driving appointments (AEO). Common in YMYL: treatment pages, state-specific legal guides, condition + service pages.",
        "primary_frameworks": ["SEO", "AEO", "GEO"],
        "secondary_frameworks": ["AIO", "LLMO"],
        "skip_frameworks": ["VSEO"],
        "skip_reason": "VSEO optional unless embedding video explainer.",
        "optimization_focus": {
            "schema": {"weight": 1.0, "focus": "BOTH service entity (LegalService/HealthcareService) AND content schemas (Article, FAQPage, Person). Full stack."},
            "crawlability": {"weight": 1.0, "focus": "Full audit — heading hierarchy for GEO + indexability for SEO"},
            "faq": {"weight": 1.0, "focus": "TWO-TIER FAQ: educational questions (GEO tier — comprehensive) + buying objection questions (AEO tier — cost, eligibility, timeline)"},
            "citability": {"weight": 0.8, "focus": "Authority content in educational sections, social proof in conversion sections. Not full-article GEO density — focused on the educational portion."},
            "accessibility": {"weight": 1.0, "focus": "Full audit — readability for educational content + CTA accessibility for conversion elements"}
        },
        "aeo_checks": True,
        "geo_checks": True,
        "cannibalization_warning": "⚠️ HYBRID STRATEGY NOTE: This page serves dual intent. The educational content should be comprehensive enough for AI citation (GEO) but the page structure must still funnel toward conversion (AEO). Recommended layout: Educational authority content in top 60-70% → transition to conversion CTA block in bottom 30-40%. Do NOT bury CTAs below 2000+ words of pure education.",
        "structure_guidance": {
            "recommended_layout": [
                "H1: [Condition/Topic] — [Service/Location Context]",
                "Key Takeaway box (AIO summary — 2-3 sentences)",
                "Educational Section 1: Definition & overview (GEO — citable, sourced)",
                "Educational Section 2: Process, options, or treatment details (GEO — statistics, expert quotes)",
                "Comparison table or pros/cons (GEO — structured data AI can extract)",
                "TRANSITION: 'How [Brand] can help' or 'Your options at [Brand]'",
                "Service details + differentiators (AEO — buying objection answers)",
                "FAQ Section — mixed: educational Qs first, then buying objection Qs",
                "CTA block: form, phone, scheduling (AEO — clear conversion path)"
            ],
            "content_ratio": "60-70% educational / 30-40% conversion",
            "min_words_educational": 800,
            "min_words_total": 1200
        }
    }
}

def detect_page_intent(url, soup, profile=None):
    """Auto-detect whether a page is homepage, informational article, or lead-gen/service page."""
    path = urlparse(url).path.strip("/").lower()
    domain = urlparse(url).netloc.lower()
    title = soup.title.string.strip().lower() if soup.title and soup.title.string else ""
    meta_desc = ""
    md_tag = soup.find("meta", attrs={"name": "description"})
    if md_tag and md_tag.get("content"):
        meta_desc = md_tag["content"].lower()

    body_text = soup.body.get_text(separator=" ", strip=True).lower() if soup.body else ""
    h1_text = ""
    h1_tag = soup.find("h1")
    if h1_tag:
        h1_text = h1_tag.get_text(strip=True).lower()

    # Signals collection
    signals = {"homepage": 0, "informational": 0, "lead_gen": 0}
    reasoning = []

    # ── HOMEPAGE SIGNALS ──
    if path == "" or path == "/" or path == "index" or path == "index.html":
        signals["homepage"] += 10
        reasoning.append("URL is root domain path")

    if not path or len(path.split("/")) <= 1:
        signals["homepage"] += 3
        reasoning.append("Short/root URL path")

    # Navigation-heavy pages
    nav_links = soup.find_all("a", href=True)
    internal_links = [a for a in nav_links if domain in a.get("href", "") or a["href"].startswith("/")]
    if len(internal_links) > 30:
        signals["homepage"] += 2
        reasoning.append(f"High internal link count ({len(internal_links)})")

    # ── INFORMATIONAL ARTICLE SIGNALS ──
    article_path_patterns = [
        r"/blog/", r"/article", r"/learn/", r"/guide/", r"/how-to",
        r"/what-is", r"/resources/", r"/education/", r"/info/",
        r"/advice/", r"/tips/", r"/understanding-"
    ]
    for pattern in article_path_patterns:
        if re.search(pattern, "/" + path):
            signals["informational"] += 5
            reasoning.append(f"URL matches article pattern: {pattern}")
            break

    # Article schema or semantic elements
    if soup.find("article") or soup.find(attrs={"class": re.compile(r"article|post|blog|entry", re.I)}):
        signals["informational"] += 3
        reasoning.append("Article/post semantic element found")

    # Question-based titles
    question_words = ["how", "what", "why", "when", "where", "who", "can", "does", "is", "are", "should", "will"]
    if any(h1_text.startswith(w + " ") for w in question_words) or h1_text.endswith("?"):
        signals["informational"] += 4
        reasoning.append("H1 is a question — informational intent")

    # Date published signals
    if soup.find("time") or soup.find(attrs={"class": re.compile(r"date|published|updated|posted", re.I)}):
        signals["informational"] += 2
        reasoning.append("Publication date element found")

    # Author byline
    if soup.find(attrs={"class": re.compile(r"author|byline|writer", re.I)}):
        signals["informational"] += 2
        reasoning.append("Author byline element found")

    # Long-form content
    word_count = len(body_text.split())
    if word_count > 1500:
        signals["informational"] += 2
        reasoning.append(f"Long-form content ({word_count} words)")

    # ── LEAD GEN / SERVICE PAGE SIGNALS ──
    lead_gen_path_patterns = [
        r"/service", r"/program", r"/solution", r"/pricing",
        r"/contact", r"/consultation", r"/apply", r"/get-started",
        r"/free-", r"/schedule", r"/book-"
    ]
    for pattern in lead_gen_path_patterns:
        if re.search(pattern, "/" + path):
            signals["lead_gen"] += 5
            reasoning.append(f"URL matches service/lead-gen pattern: {pattern}")
            break

    # Location-specific service pages
    state_patterns = [
        r"/(alabama|alaska|arizona|arkansas|california|colorado|connecticut|delaware|florida|georgia|hawaii|idaho|illinois|indiana|iowa|kansas|kentucky|louisiana|maine|maryland|massachusetts|michigan|minnesota|mississippi|missouri|montana|nebraska|nevada|new-hampshire|new-jersey|new-mexico|new-york|north-carolina|north-dakota|ohio|oklahoma|oregon|pennsylvania|rhode-island|south-carolina|south-dakota|tennessee|texas|utah|vermont|virginia|washington|west-virginia|wisconsin|wyoming)",
        r"/(al|ak|az|ar|ca|co|ct|de|fl|ga|hi|id|il|in|ia|ks|ky|la|me|md|ma|mi|mn|ms|mo|mt|ne|nv|nh|nj|nm|ny|nc|nd|oh|ok|or|pa|ri|sc|sd|tn|tx|ut|vt|va|wa|wv|wi|wy)[-/]"
    ]
    for pattern in state_patterns:
        if re.search(pattern, "/" + path):
            signals["lead_gen"] += 4
            reasoning.append("Location-specific service page")
            break

    # Forms and CTAs
    forms = soup.find_all("form")
    cta_buttons = soup.find_all(attrs={"class": re.compile(r"cta|btn|button|apply|submit|get-started|schedule|consult", re.I)})
    phone_links = soup.find_all("a", href=re.compile(r"^tel:", re.I))
    if forms:
        signals["lead_gen"] += 3
        reasoning.append(f"Contains {len(forms)} form(s)")
    if len(cta_buttons) >= 2:
        signals["lead_gen"] += 2
        reasoning.append(f"Multiple CTA buttons ({len(cta_buttons)})")
    if phone_links:
        signals["lead_gen"] += 2
        reasoning.append("Click-to-call phone link")

    # Conversion language in title/H1
    conversion_terms = ["free consultation", "get help", "apply now", "contact us", "schedule", "book",
                       "get started", "request", "enroll", "sign up", "call us", "programs", "services in"]
    for term in conversion_terms:
        if term in title or term in h1_text:
            signals["lead_gen"] += 3
            reasoning.append(f"Conversion language in title: '{term}'")
            break

    # ── HOMEPAGE CONFIDENCE FIX (Q4) ──
    # Problem: OVLG homepage has article elements, date elements, author bylines (blog feed),
    # AND forms + CTA buttons + phone links — standard on law firm/clinic homepages.
    # These noise signals leak into informational and lead_gen, dragging confidence to 52%.
    # Fix: When root-domain signal is dominant, these elements are navigation/design patterns,
    # not intent indicators (blog feed widget ≠ article page, header form ≠ lead-gen page).
    if signals["homepage"] >= 10:
        signals["informational"] = round(signals["informational"] * 0.5)
        signals["lead_gen"] = round(signals["lead_gen"] * 0.5)
        reasoning.append(f"Homepage dampening — competing signals halved (info→{signals['informational']}, lead→{signals['lead_gen']})")

    # Determine winner — with hybrid detection
    detected = max(signals, key=signals.get)
    confidence = signals[detected] / max(sum(signals.values()), 1) * 100

    # ── HYBRID DETECTION ──
    # A page is hybrid when it has strong signals for BOTH informational AND lead_gen
    # This is the norm in YMYL: treatment pages, condition guides, state-specific legal pages
    info_score = signals["informational"]
    lead_score = signals["lead_gen"]
    total_non_home = info_score + lead_score

    is_hybrid = False
    hybrid_reasoning = []

    if total_non_home > 0 and detected != "homepage":
        info_ratio = info_score / max(total_non_home, 1)
        lead_ratio = lead_score / max(total_non_home, 1)

        # Condition 1: Both intents have meaningful signal strength (neither < 25%)
        both_present = info_ratio >= 0.25 and lead_ratio >= 0.25
        if both_present:
            hybrid_reasoning.append(f"Both intents strong — informational: {info_ratio:.0%}, lead-gen: {lead_ratio:.0%}")

        # Condition 2: YMYL content patterns — educational content + conversion elements
        has_educational_depth = word_count > 800 and (
            soup.find("article") or
            any(h1_text.startswith(w + " ") for w in question_words) or
            bool(re.search(r"(?:treatment|therapy|program|law|regulation|process|how|guide)", h1_text))
        )
        has_conversion_elements = bool(forms) or bool(phone_links) or len(cta_buttons) >= 1

        if has_educational_depth and has_conversion_elements:
            hybrid_reasoning.append(f"Educational depth ({word_count} words) + conversion elements (forms: {len(forms)}, CTAs: {len(cta_buttons)}, phone: {len(phone_links)})")

        # Condition 3: Industry-specific hybrid patterns (treatment pages, state legal pages, condition + service)
        hybrid_url_patterns = [
            r"(?:treatment|therapy|disorder|condition|symptom|diagnosis)",   # Mental health treatment pages
            r"(?:law|legal|statute|regulation|rights)\S*(?:state|california|texas|florida|new-york)",  # State legal guides
            r"(?:settlement|consolidation|relief|management)\S*(?:program|service|option|plan)",  # Debt service + education
        ]
        for pattern in hybrid_url_patterns:
            if re.search(pattern, path + " " + h1_text):
                hybrid_reasoning.append(f"YMYL hybrid URL/title pattern: {pattern}")
                break

        # Condition 4: Page has both author byline (informational) AND a form/CTA (lead-gen)
        has_author = bool(soup.find(attrs={"class": re.compile(r"author|byline|writer", re.I)}))
        if has_author and has_conversion_elements:
            hybrid_reasoning.append("Author byline (informational signal) + conversion element (lead-gen signal)")

        # Trigger hybrid if 2+ hybrid signals detected
        if len(hybrid_reasoning) >= 2:
            is_hybrid = True

        # Also trigger if the gap between informational and lead_gen is small (competitive signals)
        if both_present and abs(info_score - lead_score) <= 3:
            is_hybrid = True
            if "Close signal scores" not in str(hybrid_reasoning):
                hybrid_reasoning.append(f"Close signal scores — info: {info_score}, lead-gen: {lead_score} (gap ≤ 3)")

    if is_hybrid:
        detected = "hybrid"
        # Confidence for hybrid = how balanced the two intents are (more balanced = higher confidence)
        balance = 1 - abs(info_ratio - lead_ratio) if total_non_home > 0 else 0.5
        confidence = balance * 100
        reasoning.extend([f"🔀 HYBRID DETECTED: {r}" for r in hybrid_reasoning])

    return {
        "detected_intent": detected,
        "confidence": confidence,
        "signals": signals,
        "reasoning": reasoning,
        "intent_config": PAGE_INTENTS[detected],
        "hybrid_detail": {
            "is_hybrid": is_hybrid,
            "informational_strength": info_score,
            "lead_gen_strength": lead_score,
            "hybrid_triggers": hybrid_reasoning
        } if is_hybrid else None
    }


# ─────────────────────────────────────────────
# AEO (Answer Engine Optimization) MODULE
# ─────────────────────────────────────────────

def audit_aeo(soup, url, profile, page_intent):
    """AEO checks for homepage and lead-gen pages — entity data clarity for voice/answer engines."""
    results = {
        "checks": [],
        "score": 0,
        "max_score": 15,
        "fixes": []
    }
    points = 0
    text = soup.body.get_text(separator=" ", strip=True) if soup.body else ""

    # 1. NAP (Name, Address, Phone) consistency
    phone_patterns = re.findall(r"[\(]?\d{3}[\)]?[-.\s]?\d{3}[-.\s]?\d{4}", text)
    address_patterns = soup.find_all(attrs={"class": re.compile(r"address|location", re.I)})
    address_schema = soup.find_all(attrs={"itemprop": "address"})

    if phone_patterns:
        results["checks"].append({"name": "Phone Number Visible", "status": "PASS", "detail": f"Found phone: {phone_patterns[0]}"})
        points += 2
    else:
        results["checks"].append({"name": "Phone Number Visible", "status": "FAIL", "detail": "No phone number found on page"})
        results["fixes"].append({
            "issue": "No visible phone number — critical for AEO/voice search",
            "fix_type": "html_body",
            "code": '<a href="tel:+1XXXXXXXXXX" class="phone-cta">(XXX) XXX-XXXX</a>'
        })

    if address_patterns or address_schema:
        results["checks"].append({"name": "Address Visible", "status": "PASS", "detail": "Address element found"})
        points += 2
    else:
        results["checks"].append({"name": "Address Visible", "status": "WARN", "detail": "No structured address element found"})

    # 2. Core service declaration (first 500 chars)
    first_content = text[:500].lower()
    if profile:
        industry = profile.get("industry", "")
        if industry == "legal_debt":
            service_terms = ["debt settlement", "debt relief", "debt negotiation", "attorney", "law"]
        elif industry == "financial_services":
            service_terms = ["debt consolidation", "debt management", "credit counseling", "debt relief"]
        elif industry == "mental_health":
            service_terms = ["therapy", "psychiatry", "mental health", "counseling", "telehealth"]
        else:
            service_terms = []

        found_terms = [t for t in service_terms if t in first_content]
        if found_terms:
            results["checks"].append({"name": "Core Service in First Fold", "status": "PASS", "detail": f"Service terms in first 500 chars: {', '.join(found_terms)}"})
            points += 3
        else:
            results["checks"].append({"name": "Core Service in First Fold", "status": "FAIL", "detail": "Core service not clearly stated in above-the-fold content"})
            results["fixes"].append({
                "issue": "Core service not declared early on page",
                "fix_type": "content_recommendation",
                "code": f"Ensure your primary service ({', '.join(service_terms)}) is clearly stated within the first paragraph/heading visible on the page."
            })

    # 3. Buying objection answers (for lead-gen pages)
    if page_intent == "lead_gen":
        objection_patterns = {
            "cost/pricing": r"(?:cost|price|fee|how much|afford|payment|free)",
            "timeline": r"(?:how long|timeline|duration|weeks|months|process time)",
            "eligibility": r"(?:qualify|eligible|requirement|who can|minimum|do i need)",
            "trust/credibility": r"(?:bbb|accredited|licensed|certified|rating|review|testimonial)"
        }
        answered = []
        missing = []
        for objection, pattern in objection_patterns.items():
            if re.search(pattern, text, re.I):
                answered.append(objection)
            else:
                missing.append(objection)

        if len(answered) >= 3:
            results["checks"].append({"name": "Buying Objections Answered", "status": "PASS", "detail": f"Addresses: {', '.join(answered)}"})
            points += 4
        elif answered:
            results["checks"].append({"name": "Buying Objections Answered", "status": "WARN", "detail": f"Addresses: {', '.join(answered)}. Missing: {', '.join(missing)}"})
            points += 2
            results["fixes"].append({
                "issue": f"Missing buying objection answers: {', '.join(missing)}",
                "fix_type": "content_recommendation",
                "code": f"Add clear answers to common objections: {', '.join(missing)}. These should be concise (1-2 sentences each) and visible without scrolling. Example: 'How much does it cost? → Free consultation, fees only charged on successful settlements.'"
            })
        else:
            results["checks"].append({"name": "Buying Objections Answered", "status": "FAIL", "detail": "No common buying objections addressed"})
            results["fixes"].append({
                "issue": "No buying objections answered on this lead-gen page",
                "fix_type": "content_recommendation",
                "code": "Add a brief FAQ or bullet section addressing: cost/pricing, timeline, eligibility, and trust/credibility."
            })

    # 4. Speakable content (for voice assistants)
    speakable = soup.find(attrs={"itemprop": "speakable"})
    if speakable:
        results["checks"].append({"name": "Speakable Markup", "status": "PASS", "detail": "Speakable content marked up"})
        points += 2
    else:
        results["checks"].append({"name": "Speakable Markup", "status": "WARN", "detail": "No speakable markup — helps voice assistants select answer text"})
        results["fixes"].append({
            "issue": "Missing speakable structured data",
            "fix_type": "html_head",
            "code": json.dumps({
                "@context": "https://schema.org",
                "@type": "WebPage",
                "speakable": {
                    "@type": "SpeakableSpecification",
                    "cssSelector": [".main-description", "h1", ".service-summary"]
                }
            }, indent=2)
        })

    # 5. LocalBusiness / Service Area
    schemas = extract_existing_schema(soup)
    schema_types = get_schema_types(schemas)
    local_types = {"LocalBusiness", "LegalService", "FinancialService", "MedicalBusiness", "ProfessionalService"}
    if local_types & schema_types:
        results["checks"].append({"name": "Local Entity Schema", "status": "PASS", "detail": f"Found: {', '.join(local_types & schema_types)}"})
        points += 2
    else:
        results["checks"].append({"name": "Local Entity Schema", "status": "FAIL", "detail": "No local business/service schema found"})

    results["score"] = min(round(points), 15)
    return results


# ─────────────────────────────────────────────
# GEO (Generative Engine Optimization) MODULE
# ─────────────────────────────────────────────

def audit_geo(soup, url, profile, page_intent):
    """GEO checks for informational articles — verifiable depth for AI citation."""
    results = {
        "checks": [],
        "score": 0,
        "max_score": 20,
        "fixes": [],
        "resource_estimate": None
    }
    points = 0
    text = soup.body.get_text(separator=" ", strip=True) if soup.body else ""
    paragraphs = [p.get_text(strip=True) for p in soup.body.find_all("p") if len(p.get_text(strip=True)) > 20] if soup.body else []

    # 1. Verifiable statistics with sources
    stat_with_source = re.findall(
        r"(?:according to|per|source:|data from|based on|reported by|published by|as noted by|cited in)\s+[^.]{5,60}[^.]*\d+",
        text, re.I
    )
    standalone_stats = re.findall(r"\d+(?:\.\d+)?%", text)
    dollar_amounts = re.findall(r"\$[\d,]+(?:\.\d+)?", text)
    total_stats = len(standalone_stats) + len(dollar_amounts)
    sourced_stats = len(stat_with_source)

    if sourced_stats >= 3 and total_stats >= 5:
        results["checks"].append({"name": "Verifiable Statistics", "status": "PASS", "detail": f"{total_stats} data points, {sourced_stats} with source attribution"})
        points += 4
    elif total_stats >= 3:
        results["checks"].append({"name": "Verifiable Statistics", "status": "WARN", "detail": f"{total_stats} data points but only {sourced_stats} with source attribution. AI models prefer sourced stats."})
        points += 2
        results["fixes"].append({
            "issue": "Statistics lack source attribution",
            "fix_type": "content_recommendation",
            "code": "Attach sources to every statistic. Instead of '40% of consumers...' write 'According to the CFPB (2024), 40% of consumers...' — AI models cite sourced claims 3x more often."
        })
    else:
        results["checks"].append({"name": "Verifiable Statistics", "status": "FAIL", "detail": f"Only {total_stats} data points found"})
        results["fixes"].append({
            "issue": "Insufficient verifiable data for GEO",
            "fix_type": "content_recommendation",
            "code": "Add at minimum 5 sourced statistics. Pull from CFPB, FTC, Federal Reserve, NCUA, APA, SAMHSA, industry association reports."
        })

    # 2. Expert quotes / credentials
    quote_patterns = re.findall(r'[""\u201c][^"""\u201d]{20,200}["""\u201d]', text)
    expert_mentions = re.findall(r"(?:attorney|lawyer|counselor|therapist|psychiatrist|Dr\.|MD|JD|PhD|LCSW|LMFT|CPA)\s+[A-Z][a-z]+", text)

    if quote_patterns and expert_mentions:
        results["checks"].append({"name": "Expert Quotes", "status": "PASS", "detail": f"{len(quote_patterns)} quotes, {len(expert_mentions)} expert mentions"})
        points += 3
    elif expert_mentions:
        results["checks"].append({"name": "Expert Quotes", "status": "WARN", "detail": f"Expert names found but no direct quotes"})
        points += 1
        results["fixes"].append({
            "issue": "Add direct expert quotes",
            "fix_type": "content_recommendation",
            "code": "Include at least 1-2 direct quotes from named experts. Example: '\"Consumers should always verify that a debt settlement company is accredited before enrolling,\" says Lyle Solomon, attorney at Oak View Law Group.'"
        })
    else:
        results["checks"].append({"name": "Expert Quotes", "status": "FAIL", "detail": "No expert quotes or credentials found"})
        results["fixes"].append({
            "issue": "No expert authority signals for GEO",
            "fix_type": "content_recommendation",
            "code": "Add named expert quotes with credentials. This is a top GEO ranking factor."
        })

    # 3. Structural clarity (AI extraction patterns)
    # Check for definition pattern at top
    first_500 = text[:500]
    has_early_definition = bool(re.search(r"(?:is|are|refers to|defined as)\s+(?:a|an|the)\s+", first_500, re.I))

    # Check for comparison tables
    tables = soup.find_all("table")
    has_comparison = any("vs" in str(t).lower() or "comparison" in str(t).lower() or len(t.find_all("tr")) >= 3 for t in tables)

    # Check for step-by-step / process
    has_process = bool(re.search(r"(?:step\s+\d|first,?\s+|next,?\s+|then,?\s+|finally)", text, re.I))

    # Check for pros/cons
    has_pros_cons = bool(re.search(r"(?:pros?\s+and\s+cons?|advantages?\s+and\s+disadvantages?|benefits?\s+and\s+(?:risks?|drawbacks?))", text, re.I))

    structural_score = sum([has_early_definition, has_comparison, has_process, has_pros_cons])
    if structural_score >= 3:
        results["checks"].append({"name": "Structural Clarity", "status": "PASS", "detail": f"Definition: {'✓' if has_early_definition else '✗'}, Comparison: {'✓' if has_comparison else '✗'}, Process: {'✓' if has_process else '✗'}, Pros/Cons: {'✓' if has_pros_cons else '✗'}"})
        points += 4
    elif structural_score >= 1:
        results["checks"].append({"name": "Structural Clarity", "status": "WARN", "detail": f"Definition: {'✓' if has_early_definition else '✗'}, Comparison: {'✓' if has_comparison else '✗'}, Process: {'✓' if has_process else '✗'}, Pros/Cons: {'✓' if has_pros_cons else '✗'}"})
        points += 2
        missing_structures = []
        if not has_early_definition: missing_structures.append("definitional opening")
        if not has_comparison: missing_structures.append("comparison table")
        if not has_process: missing_structures.append("step-by-step process")
        if not has_pros_cons: missing_structures.append("pros/cons section")
        results["fixes"].append({
            "issue": f"Missing structural elements: {', '.join(missing_structures)}",
            "fix_type": "content_recommendation",
            "code": f"Add these AI-extractable structures: {', '.join(missing_structures)}. AI models preferentially cite content with clear structural patterns."
        })
    else:
        results["checks"].append({"name": "Structural Clarity", "status": "FAIL", "detail": "No AI-extractable structural patterns found"})

    # 4. Government/authoritative source links
    ext_links = soup.find_all("a", href=True)
    auth_domains = [".gov", ".edu", "cfpb.gov", "ftc.gov", "nih.gov", "samhsa.gov", "apa.org", "nimh.nih.gov"]
    auth_links = [a for a in ext_links if any(d in a.get("href", "").lower() for d in auth_domains)]

    if len(auth_links) >= 3:
        results["checks"].append({"name": "Authoritative Sources", "status": "PASS", "detail": f"{len(auth_links)} links to authoritative domains"})
        points += 3
    elif auth_links:
        results["checks"].append({"name": "Authoritative Sources", "status": "WARN", "detail": f"Only {len(auth_links)} authoritative link(s)"})
        points += 1
    else:
        results["checks"].append({"name": "Authoritative Sources", "status": "FAIL", "detail": "No links to .gov, .edu, or recognized authority sites"})
        results["fixes"].append({
            "issue": "No authoritative external sources linked",
            "fix_type": "content_recommendation",
            "code": "Link to at least 3 authoritative sources: CFPB (cfpb.gov), FTC (ftc.gov), Federal Reserve, NCUA, APA, SAMHSA, NIMH."
        })

    # 5. Content freshness
    date_elements = soup.find_all("time")
    date_meta = soup.find("meta", attrs={"property": "article:modified_time"})
    date_visible = soup.find(attrs={"class": re.compile(r"updated|modified|date", re.I)})
    freshness_signals = len(date_elements) + (1 if date_meta else 0) + (1 if date_visible else 0)

    if freshness_signals >= 2:
        results["checks"].append({"name": "Content Freshness Signals", "status": "PASS", "detail": f"{freshness_signals} date/freshness indicators"})
        points += 3
    elif freshness_signals:
        results["checks"].append({"name": "Content Freshness Signals", "status": "WARN", "detail": "Minimal freshness signals"})
        points += 1
    else:
        results["checks"].append({"name": "Content Freshness Signals", "status": "FAIL", "detail": "No date or freshness signals found"})
        results["fixes"].append({
            "issue": "No content freshness signals",
            "fix_type": "html_body",
            "code": f'<time datetime="{time.strftime("%Y-%m-%d")}">Last updated: {time.strftime("%B %d, %Y")}</time>\n\n<!-- Also add to head: -->\n<meta property="article:modified_time" content="{time.strftime("%Y-%m-%dT%H:%M:%S")}+00:00" />'
        })

    # 6. AIO summary block (concise answer at top)
    first_element = soup.body.find(["p", "div"]) if soup.body else None
    first_text = first_element.get_text(strip=True) if first_element else ""
    word_count_first = len(first_text.split())

    # Check for TL;DR, summary, or key takeaway pattern
    has_summary = bool(soup.find(attrs={"class": re.compile(r"summary|tldr|takeaway|key-point|overview|highlight", re.I)}))
    has_summary = has_summary or bool(re.search(r"(?:key takeaway|in summary|tl;?dr|at a glance|quick answer)", text[:1000], re.I))

    if has_summary:
        results["checks"].append({"name": "AIO Summary Block", "status": "PASS", "detail": "Summary/key takeaway section found at top"})
        points += 3
    else:
        results["checks"].append({"name": "AIO Summary Block", "status": "WARN", "detail": "No concise summary block for AI Overview extraction"})
        results["fixes"].append({
            "issue": "No AIO-optimized summary block",
            "fix_type": "html_body",
            "code": """<!-- Add immediately after H1, before main content -->
<div class="key-takeaway" style="background: #f0f9ff; padding: 1rem; border-left: 4px solid #0284c7; margin-bottom: 1.5rem;">
  <strong>Key Takeaway:</strong> [2-3 sentence concise answer to the page's primary question. This is what AI Overviews will extract.]
</div>"""
        })

    # Resource estimate
    word_count = len(text.split())
    results["resource_estimate"] = {
        "current_words": word_count,
        "target_words": max(1500, word_count),
        "estimated_hours": round(max(2, (1500 - word_count) / 300 + 1), 1) if word_count < 1500 else 1,
        "note": "GEO-quality content requires deep research, verifiable facts, and structured data tables. Budget 2-4 hours per article vs ~1 hour for standard SEO content."
    }

    results["score"] = min(round(points), 20)
    return results


# ─────────────────────────────────────────────
# HYBRID STRUCTURE AUDIT
# ─────────────────────────────────────────────

def audit_hybrid_structure(soup, url, profile, page_intent_data):
    """Evaluates whether a hybrid page properly balances education (GEO) and conversion (AEO).
    Checks content flow: does the page educate first, then convert?"""
    results = {
        "checks": [],
        "score": 0,
        "max_score": 15,
        "fixes": [],
        "content_map": [],
        "structure_assessment": None
    }
    points = 0
    body = soup.body
    if not body:
        return results

    text = body.get_text(separator=" ", strip=True)
    word_count = len(text.split())

    # ── 1. CONTENT RATIO: Educational vs. Conversion ──
    # Walk through all major elements to map content zones
    elements = body.find_all(["h1", "h2", "h3", "h4", "p", "form", "table", "ul", "ol", "details"])
    content_zones = []  # list of {"type": "educational"|"conversion"|"neutral", "element": tag, "position": float}
    total_elements = len(elements)

    conversion_signals = re.compile(r"contact|call|schedule|book|appointment|consult|get started|apply|enroll|sign up|free quote|phone|form|submit|request", re.I)
    educational_signals = re.compile(r"what is|how does|definition|overview|understand|cause|symptom|treatment|option|research|study|according|statistic|fact|process|step|compare|difference|law|regulation|right|affect|impact", re.I)

    edu_count = 0
    conv_count = 0
    first_conversion_position = None

    for i, el in enumerate(elements):
        el_text = el.get_text(strip=True)
        position = i / max(total_elements, 1)

        if el.name == "form":
            conv_count += 1
            if first_conversion_position is None:
                first_conversion_position = position
            content_zones.append({"type": "conversion", "tag": el.name, "text": el_text[:60], "position": round(position * 100)})
        elif conversion_signals.search(el_text) and el.name in ["h2", "h3", "h4"]:
            conv_count += 1
            if first_conversion_position is None:
                first_conversion_position = position
            content_zones.append({"type": "conversion", "tag": el.name, "text": el_text[:60], "position": round(position * 100)})
        elif educational_signals.search(el_text):
            edu_count += 1
            content_zones.append({"type": "educational", "tag": el.name, "text": el_text[:60], "position": round(position * 100)})

    results["content_map"] = content_zones

    # Educational ratio check
    total_classified = edu_count + conv_count
    if total_classified > 0:
        edu_ratio = edu_count / total_classified
        conv_ratio = conv_count / total_classified

        if 0.55 <= edu_ratio <= 0.80:
            results["checks"].append({"name": "Content Ratio", "status": "PASS", "detail": f"Educational {edu_ratio:.0%} / Conversion {conv_ratio:.0%} — ideal hybrid balance"})
            points += 4
        elif 0.40 <= edu_ratio <= 0.90:
            results["checks"].append({"name": "Content Ratio", "status": "WARN", "detail": f"Educational {edu_ratio:.0%} / Conversion {conv_ratio:.0%} — target 60-70% educational"})
            points += 2
            if edu_ratio > 0.85:
                results["fixes"].append({"issue": "Too much education, not enough conversion elements", "fix_type": "content_recommendation",
                    "code": "Add a clear 'How We Can Help' or 'Your Options at [Brand]' section in the bottom 30-40% of the page. Include: service differentiators, pricing/cost clarity, CTA button or form, phone number."})
            else:
                results["fixes"].append({"issue": "Too much conversion, not enough educational authority", "fix_type": "content_recommendation",
                    "code": "Expand educational content in the top 60% of the page. Add: sourced statistics, expert quotes, comparison tables, process steps. This is what AI models need to cite your page."})
        else:
            results["checks"].append({"name": "Content Ratio", "status": "FAIL", "detail": f"Educational {edu_ratio:.0%} / Conversion {conv_ratio:.0%} — severely unbalanced"})
    else:
        results["checks"].append({"name": "Content Ratio", "status": "WARN", "detail": "Could not classify content zones"})

    # ── 2. STRUCTURE FLOW: Educate first, then convert ──
    if first_conversion_position is not None:
        if first_conversion_position >= 0.50:
            results["checks"].append({"name": "Educate-First Flow", "status": "PASS", "detail": f"First conversion element at {first_conversion_position:.0%} of page — education leads"})
            points += 3
        elif first_conversion_position >= 0.30:
            results["checks"].append({"name": "Educate-First Flow", "status": "WARN", "detail": f"First conversion element at {first_conversion_position:.0%} — consider moving CTAs lower"})
            points += 1
            results["fixes"].append({"issue": "Conversion elements appear too early", "fix_type": "content_recommendation",
                "code": "Move the first form/CTA block below the educational content. Recommended flow: H1 → Key Takeaway → Educational sections (definitions, statistics, expert content) → THEN conversion block. The educational content builds the trust that makes the CTA effective."})
        else:
            results["checks"].append({"name": "Educate-First Flow", "status": "FAIL", "detail": f"Conversion elements at {first_conversion_position:.0%} of page — too early, undermines authority"})
            results["fixes"].append({"issue": "CTAs above educational content", "fix_type": "content_recommendation",
                "code": "Restructure: educational authority content must come BEFORE the conversion pitch. AI models evaluating this page for citations will see the sales content first and rank it as promotional, not authoritative."})
    else:
        results["checks"].append({"name": "Educate-First Flow", "status": "FAIL", "detail": "No conversion elements found — hybrid page needs both"})
        results["fixes"].append({"issue": "No conversion elements on hybrid page", "fix_type": "content_recommendation",
            "code": "Add a conversion section in the bottom 30-40%: service details, CTAs, phone number, scheduling form."})

    # ── 3. TWO-TIER FAQ CHECK ──
    faq_headings = [h for h in soup.find_all(re.compile(r"^h[2-4]$"))
                     if h.get_text(strip=True).endswith("?") or
                     any(h.get_text(strip=True).lower().startswith(w + " ") for w in ["what", "how", "why", "can", "does", "is", "will", "should", "do"])]

    edu_faqs = []
    buying_faqs = []
    buying_keywords = re.compile(r"cost|price|fee|how much|afford|insurance|accept|cover|pay|eligible|qualify|require|how long|timeline|duration|week|month|appointment|schedule|book|start", re.I)

    for faq_h in faq_headings:
        q_text = faq_h.get_text(strip=True)
        if buying_keywords.search(q_text):
            buying_faqs.append(q_text)
        else:
            edu_faqs.append(q_text)

    has_edu_faqs = len(edu_faqs) >= 2
    has_buying_faqs = len(buying_faqs) >= 2

    if has_edu_faqs and has_buying_faqs:
        results["checks"].append({"name": "Two-Tier FAQ", "status": "PASS", "detail": f"Educational Qs: {len(edu_faqs)}, Buying Qs: {len(buying_faqs)} — both tiers present"})
        points += 4
    elif has_edu_faqs or has_buying_faqs:
        missing = "buying objection" if not has_buying_faqs else "educational"
        results["checks"].append({"name": "Two-Tier FAQ", "status": "WARN", "detail": f"Only {'educational' if has_edu_faqs else 'buying'} FAQs found. Missing {missing} tier."})
        points += 2
        if not has_buying_faqs:
            results["fixes"].append({"issue": "Missing buying-objection FAQs", "fix_type": "content_recommendation",
                "code": "Add FAQ section with buying questions: 'How much does [service] cost?', 'How long does the process take?', 'Do I qualify for [service]?', 'Do you accept [insurance/payment plans]?', 'How do I get started?'"})
        else:
            results["fixes"].append({"issue": "Missing educational FAQs", "fix_type": "content_recommendation",
                "code": "Add educational FAQ questions that AI models can cite: 'What is [condition/topic]?', 'How does [process] work?', 'What are the risks/benefits?', 'What research supports [treatment/approach]?'"})
    else:
        results["checks"].append({"name": "Two-Tier FAQ", "status": "FAIL", "detail": "No FAQ questions detected"})
        results["fixes"].append({"issue": "Hybrid page needs both educational and buying FAQs", "fix_type": "content_recommendation",
            "code": "Add a comprehensive FAQ section with two tiers:\n\n## Educational Questions (for AI citation):\n- What is [topic]?\n- How does [process] work?\n- What are the options for [condition]?\n\n## Practical/Buying Questions (for conversion):\n- How much does it cost?\n- How long does it take?\n- Do I qualify?\n- How do I get started?"})

    # ── 4. WORD COUNT MINIMUMS ──
    if word_count >= 1200:
        results["checks"].append({"name": "Content Depth", "status": "PASS", "detail": f"{word_count} words (minimum 1200 for hybrid)"})
        points += 2
    elif word_count >= 800:
        results["checks"].append({"name": "Content Depth", "status": "WARN", "detail": f"{word_count} words — thin for hybrid. Target 1200+."})
        points += 1
    else:
        results["checks"].append({"name": "Content Depth", "status": "FAIL", "detail": f"{word_count} words — too thin for hybrid intent"})

    # ── 5. CTA PRESENCE AND CLARITY ──
    forms = soup.find_all("form")
    phone_links = soup.find_all("a", href=re.compile(r"^tel:", re.I))
    scheduling_patterns = soup.find_all(attrs={"class": re.compile(r"schedule|book|appointment|calendly|cta", re.I)})
    cta_count = len(forms) + len(phone_links) + len(scheduling_patterns)

    if cta_count >= 2:
        results["checks"].append({"name": "Conversion Elements", "status": "PASS", "detail": f"Forms: {len(forms)}, Phone: {len(phone_links)}, CTAs: {len(scheduling_patterns)}"})
        points += 2
    elif cta_count >= 1:
        results["checks"].append({"name": "Conversion Elements", "status": "WARN", "detail": f"Only {cta_count} conversion element. Add more."})
        points += 1
    else:
        results["checks"].append({"name": "Conversion Elements", "status": "FAIL", "detail": "No forms, phone links, or CTA elements"})

    # Structure assessment summary
    results["structure_assessment"] = {
        "content_ratio": f"{edu_count} educational / {conv_count} conversion elements",
        "first_conversion_at": f"{first_conversion_position:.0%}" if first_conversion_position else "None found",
        "edu_faqs": edu_faqs[:5],
        "buying_faqs": buying_faqs[:5],
        "word_count": word_count,
        "verdict": "PASS" if points >= 10 else "NEEDS WORK" if points >= 5 else "RESTRUCTURE REQUIRED"
    }

    results["score"] = min(round(points), 15)
    return results


# ─────────────────────────────────────────────
# YMYL / E-E-A-T DEEP AUDIT (Q2)
# ─────────────────────────────────────────────

def audit_ymyl_eeat(soup, url, profile, page_intent):
    """Deep YMYL and E-E-A-T signal verification.
    Goes beyond basic byline detection to check:
    - YMYL-specific schemas (MedicalWebPage, MedicalScholarlyArticle, LegalService)
    - Author bio page verification (does the linked bio page actually exist?)
    - Credential specificity (not just 'reviewed by' but actual license/degree info)
    - Compliance disclaimers (medical, legal, financial)
    """
    results = {
        "checks": [],
        "score": 0,
        "max_score": 15,
        "fixes": [],
        "eeat_profile": {}
    }
    points = 0
    text = soup.body.get_text(separator=" ", strip=True) if soup.body else ""
    schemas = extract_existing_schema(soup)
    schema_types = get_schema_types(schemas)
    all_items = get_all_schema_items(schemas)

    industry = profile.get("industry", "general") if profile else "general"

    # ── 1. YMYL-SPECIFIC SCHEMAS ──
    ymyl_schemas_by_industry = {
        "legal_debt": {
            "critical": ["LegalService"],
            "recommended": ["Attorney", "LegalForceStatus"],
            "page_type_schemas": {"MedicalWebPage": False, "LegalService": True, "FinancialProduct": False}
        },
        "financial_services": {
            "critical": ["FinancialService"],
            "recommended": ["FinancialProduct", "MonetaryAmount"],
            "page_type_schemas": {"MedicalWebPage": False, "LegalService": False, "FinancialProduct": True}
        },
        "mental_health": {
            "critical": ["MedicalBusiness", "HealthcareService"],
            "recommended": ["MedicalWebPage", "MedicalCondition", "PsychologicalTreatment", "Physician", "MedicalScholarlyArticle"],
            "page_type_schemas": {"MedicalWebPage": True, "MedicalScholarlyArticle": True, "HealthcareService": True}
        }
    }

    industry_config = ymyl_schemas_by_industry.get(industry, {})
    critical_schemas = industry_config.get("critical", [])
    recommended_schemas = industry_config.get("recommended", [])

    found_critical = [s for s in critical_schemas if s in schema_types]
    missing_critical = [s for s in critical_schemas if s not in schema_types]
    found_recommended = [s for s in recommended_schemas if s in schema_types]
    missing_recommended = [s for s in recommended_schemas if s not in schema_types]

    if found_critical:
        results["checks"].append({"name": "YMYL Critical Schemas", "status": "PASS", "detail": f"Found: {', '.join(found_critical)}"})
        points += 3
    elif critical_schemas:
        results["checks"].append({"name": "YMYL Critical Schemas", "status": "FAIL", "detail": f"Missing: {', '.join(missing_critical)}"})
        for ms in missing_critical:
            results["fixes"].append({"issue": f"Missing YMYL schema: {ms}", "fix_type": "html_head", "code": f"Add {ms} schema — see Schema Audit module for generated template."})

    if found_recommended:
        results["checks"].append({"name": "YMYL Recommended Schemas", "status": "PASS", "detail": f"Found: {', '.join(found_recommended)}"})
        points += 1
    elif recommended_schemas:
        results["checks"].append({"name": "YMYL Recommended Schemas", "status": "WARN", "detail": f"Consider adding: {', '.join(missing_recommended[:3])}"})

    # Check for MedicalWebPage (mental health) or specific YMYL page type schema
    if industry == "mental_health" and page_intent in ["informational", "hybrid"]:
        if "MedicalWebPage" in schema_types:
            results["checks"].append({"name": "MedicalWebPage Schema", "status": "PASS", "detail": "Present — signals medical content to Google and AI models"})
            points += 2
        else:
            results["checks"].append({"name": "MedicalWebPage Schema", "status": "WARN", "detail": "Not found — Google uses this to identify health content requiring higher E-E-A-T"})
            results["fixes"].append({
                "issue": "Missing MedicalWebPage schema for mental health content",
                "fix_type": "html_head",
                "code": json.dumps({"@context": "https://schema.org", "@type": "MedicalWebPage", "name": "[PAGE TITLE]", "description": "[META DESCRIPTION]", "lastReviewed": time.strftime("%Y-%m-%d"), "reviewedBy": {"@type": "Person", "name": "[REVIEWER NAME]", "jobTitle": "[LICENSE TYPE, e.g., LMFT, PsyD]"}, "medicalAudience": {"@type": "MedicalAudience", "audienceType": "Patient"}, "about": {"@type": "MedicalCondition", "name": "[CONDITION]"}}, indent=2)
            })

    # ── 2. AUTHOR/REVIEWER CREDENTIAL VERIFICATION ──
    # Level 1: Byline present?
    author_elements = soup.find_all(attrs={"class": re.compile(r"author|byline|writer|reviewer", re.I)})
    reviewer_text = re.findall(r"(?:reviewed|verified|fact[- ]?checked|medically reviewed|legally reviewed)\s+by\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})", text)

    has_byline = len(author_elements) > 0 or bool(reviewer_text)

    # Level 2: Credentials specified? (not just name, but degree/license)
    credential_patterns = re.findall(
        r"(?:MD|DO|PhD|PsyD|JD|Esq|LCSW|LMFT|LPC|LMHC|CPA|CFP|RN|NP|PA-C|BCBA|Bar (?:No\.|Number|#)\s*\d+)",
        text
    )
    credential_in_schema = False
    for item in all_items:
        if item.get("@type") == "Person":
            if item.get("hasCredential") or item.get("qualification"):
                credential_in_schema = True
            if item.get("jobTitle") and any(c in str(item.get("jobTitle", "")) for c in ["Attorney", "MD", "PhD", "Therapist", "Counselor"]):
                credential_in_schema = True

    if has_byline and credential_patterns and credential_in_schema:
        results["checks"].append({"name": "Author Credentials", "status": "PASS", "detail": f"Byline + credentials ({', '.join(set(credential_patterns)[:5])}) + schema"})
        points += 3
    elif has_byline and credential_patterns:
        results["checks"].append({"name": "Author Credentials", "status": "WARN", "detail": f"Byline and credentials visible ({', '.join(list(set(credential_patterns))[:3])}) but not in Person schema"})
        points += 2
        results["fixes"].append({"issue": "Add credentials to Person schema", "fix_type": "html_head",
            "code": "Add 'hasCredential' property to the Person schema. See schema template in Schema Audit module."})
    elif has_byline:
        results["checks"].append({"name": "Author Credentials", "status": "WARN", "detail": "Byline found but no specific credentials (degree, license number, title)"})
        points += 1
        results["fixes"].append({"issue": "Author byline lacks credential specificity", "fix_type": "content_recommendation",
            "code": "Change 'Reviewed by John Smith' to 'Reviewed by John Smith, JD, Licensed Attorney (State Bar #12345)' or 'Medically reviewed by Dr. Jane Doe, PsyD, Licensed Clinical Psychologist'. AI models weight specific credentials much higher than bare names."})
    else:
        results["checks"].append({"name": "Author Credentials", "status": "FAIL", "detail": "No author/reviewer byline found"})
        results["fixes"].append({"issue": "No author or reviewer attribution on YMYL content", "fix_type": "html_body",
            "code": '<div class="author-byline">\n  <p>Written by <a href="/about/[slug]">[Name]</a>, [Degree/License]</p>\n  <p>Reviewed by <a href="/about/[slug]">[Name]</a>, [Credential, License #]</p>\n  <p>Last reviewed: [Date]</p>\n</div>'})

    # Level 3: Author bio page link exists and is reachable?
    author_links = []
    for el in author_elements:
        link = el.find("a", href=True)
        if link:
            href = link.get("href", "")
            if href.startswith("/") or urlparse(url).netloc in href:
                author_links.append(urljoin(url, href))

    # Also check Person schema for URL
    for item in all_items:
        if item.get("@type") == "Person" and item.get("url"):
            p_url = item["url"]
            if p_url.startswith("/") or urlparse(url).netloc in p_url:
                author_links.append(urljoin(url, p_url))

    bio_pages_verified = 0
    bio_pages_broken = 0
    if author_links:
        for bio_url in list(set(author_links))[:3]:  # Check up to 3 bio pages
            try:
                bio_resp = requests.head(bio_url, headers=HEADERS, timeout=5, allow_redirects=True)
                if bio_resp.status_code == 200:
                    bio_pages_verified += 1
                else:
                    bio_pages_broken += 1
            except:
                bio_pages_broken += 1

        if bio_pages_verified > 0 and bio_pages_broken == 0:
            results["checks"].append({"name": "Author Bio Pages", "status": "PASS", "detail": f"{bio_pages_verified} author bio page(s) verified (HTTP 200)"})
            points += 2
        elif bio_pages_verified > 0:
            results["checks"].append({"name": "Author Bio Pages", "status": "WARN", "detail": f"{bio_pages_verified} verified, {bio_pages_broken} broken"})
            points += 1
        else:
            results["checks"].append({"name": "Author Bio Pages", "status": "FAIL", "detail": f"All {bio_pages_broken} author bio links are broken"})
            results["fixes"].append({"issue": "Author bio page links are broken (404)", "fix_type": "content_recommendation",
                "code": "Fix author bio page URLs. Each author/reviewer needs a dedicated page with: full name, credentials, professional background, areas of expertise. This page is what AI models use to verify author authority."})
    else:
        results["checks"].append({"name": "Author Bio Pages", "status": "FAIL", "detail": "No links to author bio pages found"})
        results["fixes"].append({"issue": "No author bio page links", "fix_type": "content_recommendation",
            "code": "Link each author/reviewer name to their dedicated bio page. Bio pages should include: full credentials, professional history, areas of expertise, professional affiliations, and links to published work."})

    # ── 3. DISCLAIMER VALIDATION (topic-aware) ──
    # Canonical disclaimer templates — must match what writers use
    DISCLAIMER_TEMPLATES = {
        "legal_debt": {
            "base": {
                "name": "Base Legal/Financial Disclaimer",
                "key_phrases": [
                    r"educational\s+purposes\s+only",
                    r"does\s+not\s+constitute\s+(?:legal|financial|professional)\s+advice",
                    r"(?:individual\s+)?results?\s+may\s+vary",
                    r"consult\s+(?:a\s+)?(?:licensed\s+)?(?:attorney|financial\s+advisor|qualified)"
                ],
                "min_matches": 3,
                "canonical_text": "Disclaimer: This article is for educational purposes only and does not constitute legal, financial, or professional advice. Individual results may vary based on your specific financial situation and applicable state laws. Consult a licensed attorney or qualified financial advisor before making decisions about your debt. Verify current information with the Consumer Financial Protection Bureau (cfpb.gov) and your state's regulatory agencies."
            },
            "attorney_ad": {
                "name": "Attorney Advertising Notice",
                "key_phrases": [r"attorney\s+advertising", r"past\s+results\s+(?:do\s+not|don.t)\s+guarantee"],
                "min_matches": 1,
                "canonical_text": "Attorney Advertising. Past results do not guarantee future outcomes.",
                "ovlg_only": True
            },
            "topic_addendums": {
                "settlement": {
                    "name": "Debt Settlement Risk Addendum",
                    "triggers": [r"(?:debt\s+)?settlement", r"settle\s+(?:your|my|the)\s+debt", r"negotiate\s+(?:with\s+)?creditor"],
                    "key_phrases": [r"(?:credit\s+score\s+impact|creditor\s+lawsuits?|tax\s+liability|forgiven\s+debt|not\s+all\s+creditors)"],
                    "canonical_text": "Debt settlement involves risks including potential credit score impact, possible creditor lawsuits, and tax liability on forgiven debt. Not all creditors agree to settle."
                },
                "bankruptcy": {
                    "name": "Bankruptcy Risk Addendum",
                    "triggers": [r"bankruptcy", r"chapter\s+[7913]", r"file\s+(?:for\s+)?bankruptcy"],
                    "key_phrases": [r"(?:legal\s+and\s+financial\s+consequences|eligibility.*vary|bankruptcy\s+attorney)"],
                    "canonical_text": "Bankruptcy has significant legal and financial consequences. Eligibility, exemptions, and outcomes vary by chapter and state. Consult a bankruptcy attorney for advice specific to your case."
                },
                "consolidation": {
                    "name": "Consolidation Loan Addendum",
                    "triggers": [r"(?:debt\s+)?consolidation\s+loan", r"consolidate\s+(?:your|my)\s+debt", r"(?:loan|interest)\s+rate"],
                    "key_phrases": [r"(?:(?:terms|rates|eligibility)\s+vary|does\s+not\s+reduce\s+the\s+total)"],
                    "canonical_text": "Loan terms, interest rates, and eligibility requirements vary by lender and state regulations. A consolidation loan does not reduce the total amount owed."
                },
                "payday": {
                    "name": "Payday Loan Addendum",
                    "triggers": [r"payday\s+loan", r"payday\s+(?:lending|lender)"],
                    "key_phrases": [r"(?:regulations?\s+vary|state\s+(?:laws?|prohibit)|payday\s+(?:loan\s+)?consolidation)"],
                    "canonical_text": "Payday loan terms and regulations vary significantly by state. Some states prohibit payday lending entirely. Check your state's laws before pursuing any payday loan consolidation option."
                }
            }
        },
        "financial_services": {
            "base": {
                "name": "Base Financial Disclaimer",
                "key_phrases": [
                    r"educational\s+purposes\s+only",
                    r"does\s+not\s+constitute\s+(?:financial|professional)\s+advice",
                    r"(?:individual\s+)?results?\s+may\s+vary",
                    r"consult\s+(?:a\s+)?(?:qualified\s+)?(?:financial\s+advisor|licensed\s+attorney)"
                ],
                "min_matches": 3,
                "canonical_text": "Disclaimer: This article is for educational purposes only and does not constitute financial or professional advice. DebtConsolidationCare provides information and community support but is not a financial services provider. Individual results may vary. Consult a qualified financial advisor or licensed attorney before making debt relief decisions. Verify current information with the Consumer Financial Protection Bureau (cfpb.gov) and your state's regulatory agencies."
            },
            "topic_addendums": {
                "settlement": {
                    "name": "Debt Settlement Risk Addendum",
                    "triggers": [r"(?:debt\s+)?settlement", r"settle\s+(?:your|my|the)\s+debt"],
                    "key_phrases": [r"(?:credit\s+score\s+impact|creditor\s+lawsuits?|tax\s+liability|forgiven\s+debt)"],
                    "canonical_text": "Debt settlement involves risks including potential credit score impact, possible creditor lawsuits, and tax liability on forgiven debt. Not all creditors agree to settle."
                },
                "bankruptcy": {
                    "name": "Bankruptcy Risk Addendum",
                    "triggers": [r"bankruptcy", r"chapter\s+[7913]"],
                    "key_phrases": [r"(?:legal\s+and\s+financial\s+consequences|eligibility.*vary|bankruptcy\s+attorney)"],
                    "canonical_text": "Bankruptcy has significant legal and financial consequences. Eligibility, exemptions, and outcomes vary by chapter and state. Consult a bankruptcy attorney for advice specific to your case."
                },
                "consolidation": {
                    "name": "Consolidation Loan Addendum",
                    "triggers": [r"(?:debt\s+)?consolidation\s+loan", r"consolidate\s+(?:your|my)\s+debt"],
                    "key_phrases": [r"(?:(?:terms|rates|eligibility)\s+vary|does\s+not\s+reduce\s+the\s+total)"],
                    "canonical_text": "Loan terms, interest rates, and eligibility requirements vary by lender and state regulations. A consolidation loan does not reduce the total amount owed."
                },
                "payday": {
                    "name": "Payday Loan Addendum",
                    "triggers": [r"payday\s+loan"],
                    "key_phrases": [r"(?:regulations?\s+vary|state\s+(?:laws?|prohibit))"],
                    "canonical_text": "Payday loan terms and regulations vary significantly by state. Some states prohibit payday lending entirely. Check your state's laws before pursuing any payday loan consolidation option."
                }
            }
        },
        "mental_health": {
            "base": {
                "name": "Base Medical Disclaimer",
                "key_phrases": [
                    r"educational\s+purposes\s+only",
                    r"does\s+not\s+(?:replace|constitute)\s+(?:professional\s+)?medical\s+advice",
                    r"(?:diagnosis|treatment)",
                    r"consult\s+(?:a\s+)?(?:licensed\s+)?(?:mental\s+health\s+professional|healthcare)"
                ],
                "min_matches": 3,
                "canonical_text": "Disclaimer: This article is for educational purposes only and does not replace professional medical advice, diagnosis, or treatment. Mental health conditions and treatment responses vary by individual. Always consult a licensed mental health professional for guidance specific to your situation."
            },
            "topic_addendums": {
                "condition": {
                    "name": "Crisis Resources Addendum",
                    "triggers": [r"(?:bipolar|depression|anxiety|ptsd|ocd|adhd|schizophren|suicid|self[- ]harm|eating\s+disorder|panic|trauma|borderline|psychosis)"],
                    "key_phrases": [r"(?:988|crisis|741741|call\s+911)"],
                    "canonical_text": "If you or someone you know is in crisis, call 988 (Suicide & Crisis Lifeline), text HOME to 741741, or call 911."
                },
                "medication": {
                    "name": "Medication Safety Addendum",
                    "triggers": [r"(?:medication|prescri|antidepressant|antipsychotic|SSRI|SNRI|benzo|stimulant|mood\s+stabilizer|dosage|mg\b|milligram)"],
                    "key_phrases": [r"(?:never\s+(?:start|stop|change)|prescribing\s+physician|without\s+consulting)"],
                    "canonical_text": "Never start, stop, or change the dosage of any medication without consulting your prescribing physician."
                },
                "therapy": {
                    "name": "Therapy Outcomes Addendum",
                    "triggers": [r"(?:therap|somatic|yoga\s+therap|CBT|DBT|EMDR|counseling\s+session|psychotherap)"],
                    "key_phrases": [r"(?:individual\s+(?:therapeutic\s+)?outcomes|many\s+factors|personal\s+history)"],
                    "canonical_text": "Individual therapeutic outcomes depend on many factors, including the nature of the concern, personal history, and engagement in the therapeutic process."
                }
            }
        }
    }

    industry_templates = DISCLAIMER_TEMPLATES.get(industry, {})
    h1_text = soup.find("h1").get_text(strip=True) if soup.find("h1") else ""
    title_text = soup.title.string.strip() if soup.title and soup.title.string else ""
    page_topic_text = (h1_text + " " + title_text).lower()

    # Check base disclaimer
    base_tmpl = industry_templates.get("base", {})
    if base_tmpl:
        matches = sum(1 for p in base_tmpl.get("key_phrases", []) if re.search(p, text, re.I))
        min_needed = base_tmpl.get("min_matches", 2)

        if matches >= min_needed:
            results["checks"].append({"name": f"Base Disclaimer", "status": "PASS", "detail": f"Found {matches}/{len(base_tmpl['key_phrases'])} key phrases"})
            points += 1

            # Check for phrasing problems — "does not constitute" vs "does not replace" for medical
            if industry == "mental_health":
                uses_constitute = bool(re.search(r"does\s+not\s+constitute\s+medical", text, re.I))
                uses_replace = bool(re.search(r"does\s+not\s+replace.*medical\s+advice", text, re.I))
                if uses_constitute and not uses_replace:
                    results["checks"].append({"name": "Disclaimer Phrasing", "status": "WARN", "detail": "Uses 'does not constitute' — should use 'does not replace professional medical advice, diagnosis, or treatment'"})
                    results["fixes"].append({"issue": "Weak disclaimer phrasing", "fix_type": "content_recommendation",
                        "code": "Change 'does not constitute medical advice' to 'does not replace professional medical advice, diagnosis, or treatment.' The latter is the standard phrasing."})

            # Check for topic-mismatch in existing disclaimer
            if industry in ["legal_debt", "financial_services"]:
                has_loan_mention = bool(re.search(r"loan\s+consolidation|lender|interest\s+rate", text[-2000:], re.I))  # check last 2000 chars (where disclaimers usually are)
                page_about_bankruptcy = bool(re.search(r"bankruptcy|chapter\s+[7913]", page_topic_text))
                page_about_settlement = bool(re.search(r"settlement|settle.*debt|negotiate.*creditor", page_topic_text))
                if has_loan_mention and page_about_bankruptcy:
                    results["checks"].append({"name": "Disclaimer Topic Match", "status": "FAIL", "detail": "Disclaimer mentions 'loan consolidation' but article is about bankruptcy — topic mismatch"})
                    results["fixes"].append({"issue": "Disclaimer topic mismatch — loan consolidation disclaimer on bankruptcy page", "fix_type": "content_recommendation",
                        "code": f"Replace the loan consolidation disclaimer with the bankruptcy addendum:\n\n{industry_templates.get('topic_addendums', {}).get('bankruptcy', {}).get('canonical_text', '')}"})
                elif has_loan_mention and page_about_settlement:
                    results["checks"].append({"name": "Disclaimer Topic Match", "status": "FAIL", "detail": "Disclaimer mentions 'loan consolidation' but article is about debt settlement — topic mismatch"})
                    results["fixes"].append({"issue": "Disclaimer topic mismatch — loan consolidation disclaimer on settlement page", "fix_type": "content_recommendation",
                        "code": f"Replace the loan consolidation disclaimer with the settlement addendum:\n\n{industry_templates.get('topic_addendums', {}).get('settlement', {}).get('canonical_text', '')}"})
                else:
                    results["checks"].append({"name": "Disclaimer Topic Match", "status": "PASS", "detail": "No obvious topic mismatch"})
        else:
            results["checks"].append({"name": f"Base Disclaimer", "status": "FAIL", "detail": f"Only {matches}/{len(base_tmpl['key_phrases'])} key phrases found (need {min_needed})"})
            # Check if there's a link to a disclaimers page
            disclaimer_link = soup.find("a", href=re.compile(r"disclaimer", re.I))
            if disclaimer_link:
                results["checks"].append({"name": "Disclaimer Page Link", "status": "WARN", "detail": f"Link to disclaimers page found ({disclaimer_link.get('href', '')}), but no inline disclaimer on this page"})
                results["fixes"].append({"issue": "Disclaimer exists on separate page but not inline", "fix_type": "content_recommendation",
                    "code": f"Add the base disclaimer inline on every article page. AI models and search engines evaluate pages individually. A link to a separate disclaimers page does not count as having a disclaimer on this page.\n\nCanonical text:\n{base_tmpl.get('canonical_text', '')}"})
            else:
                results["fixes"].append({"issue": "Missing base disclaimer", "fix_type": "content_recommendation",
                    "code": f"Add the following disclaimer to this page:\n\n{base_tmpl.get('canonical_text', '')}"})

    # Check attorney advertising (OVLG only)
    atty_tmpl = industry_templates.get("attorney_ad", {})
    if atty_tmpl and profile and profile.get("domain") == "ovlg.com":
        atty_matches = sum(1 for p in atty_tmpl.get("key_phrases", []) if re.search(p, text, re.I))
        if atty_matches >= atty_tmpl.get("min_matches", 1):
            results["checks"].append({"name": "Attorney Advertising Notice", "status": "PASS", "detail": "Present"})
            points += 1
        else:
            results["checks"].append({"name": "Attorney Advertising Notice", "status": "FAIL", "detail": "Missing — required for law firm content per California State Bar rules"})
            results["fixes"].append({"issue": "Missing Attorney Advertising notice", "fix_type": "content_recommendation",
                "code": f"Add to every OVLG article:\n\n{atty_tmpl.get('canonical_text', '')}"})

    # Check topic-specific addendums
    topic_addendums = industry_templates.get("topic_addendums", {})
    required_addendums = []
    found_addendums = []
    missing_addendums = []

    for topic_key, addendum in topic_addendums.items():
        # Does the page topic trigger this addendum?
        topic_triggered = any(re.search(t, page_topic_text + " " + text[:2000], re.I) for t in addendum.get("triggers", []))
        if topic_triggered:
            required_addendums.append(addendum["name"])
            # Is the addendum present?
            addendum_present = any(re.search(p, text, re.I) for p in addendum.get("key_phrases", []))
            if addendum_present:
                found_addendums.append(addendum["name"])
            else:
                missing_addendums.append(addendum)

    if required_addendums:
        if found_addendums and not missing_addendums:
            results["checks"].append({"name": "Topic-Specific Addendums", "status": "PASS", "detail": f"Found: {', '.join(found_addendums)}"})
            points += 1
        elif found_addendums:
            results["checks"].append({"name": "Topic-Specific Addendums", "status": "WARN", "detail": f"Found: {', '.join(found_addendums)}. Missing: {', '.join(a['name'] for a in missing_addendums)}"})
            for ma in missing_addendums:
                results["fixes"].append({"issue": f"Missing topic addendum: {ma['name']}", "fix_type": "content_recommendation",
                    "code": f"This article's topic requires the following addendum:\n\n{ma.get('canonical_text', '')}"})
        else:
            results["checks"].append({"name": "Topic-Specific Addendums", "status": "FAIL", "detail": f"Missing all required: {', '.join(a['name'] for a in missing_addendums)}"})
            for ma in missing_addendums:
                results["fixes"].append({"issue": f"Missing topic addendum: {ma['name']}", "fix_type": "content_recommendation",
                    "code": f"Add:\n\n{ma.get('canonical_text', '')}"})
    else:
        results["checks"].append({"name": "Topic-Specific Addendums", "status": "PASS", "detail": "No topic-specific addendums required for this page"})

    # ── 4. CROSS-REVIEW ATTRIBUTION (your dual-attorney model) ──
    if industry in ["legal_debt", "financial_services"]:
        cross_review = bool(re.search(r"(?:reviewed\s+by|fact[- ]?checked\s+by|verified\s+by)\s+(?:an?\s+)?(?:attorney|lawyer|counsel)", text, re.I))
        if cross_review:
            results["checks"].append({"name": "Cross-Review (E-E-A-T)", "status": "PASS", "detail": "Attorney review attribution found"})
            points += 2
        else:
            results["checks"].append({"name": "Cross-Review (E-E-A-T)", "status": "WARN", "detail": "No attorney cross-review attribution found"})
            results["fixes"].append({"issue": "Add cross-review attribution", "fix_type": "content_recommendation",
                "code": "Add 'Legally reviewed by [Attorney Name], [Bar Number]' — the dual-attorney cross-review model (Lyle on DebtCC, Loretta on OVLG) is a significant E-E-A-T differentiator."})

    elif industry == "mental_health":
        medical_review = bool(re.search(r"(?:medically\s+reviewed|clinically\s+reviewed|reviewed\s+by\s+(?:a\s+)?(?:doctor|physician|psychiatrist|psychologist|therapist|licensed))", text, re.I))
        if medical_review:
            results["checks"].append({"name": "Medical Review (E-E-A-T)", "status": "PASS", "detail": "Medical/clinical review attribution found"})
            points += 2
        else:
            results["checks"].append({"name": "Medical Review (E-E-A-T)", "status": "WARN", "detail": "No medical review attribution found"})
            results["fixes"].append({"issue": "Add medical review attribution", "fix_type": "content_recommendation",
                "code": "Add 'Medically reviewed by [Clinician Name], [License Type]' to all clinical content."})

    results["eeat_profile"] = {
        "industry": industry,
        "ymyl_schemas_found": found_critical + found_recommended,
        "credentials_detected": list(set(credential_patterns))[:5],
        "disclaimers_base_found": bool(base_tmpl and sum(1 for p in base_tmpl.get("key_phrases", []) if re.search(p, text, re.I)) >= base_tmpl.get("min_matches", 2)),
        "disclaimers_addendums_required": required_addendums if 'required_addendums' in dir() else [],
        "disclaimers_addendums_found": found_addendums if 'found_addendums' in dir() else [],
        "disclaimers_addendums_missing": [a["name"] for a in missing_addendums] if 'missing_addendums' in dir() else [],
        "bio_pages_verified": bio_pages_verified,
        "bio_pages_broken": bio_pages_broken
    }

    results["score"] = min(round(points), 15)
    return results


# ─────────────────────────────────────────────
# LLMO AUDIT (Q3) — On-page + Feasible Off-page
# ─────────────────────────────────────────────

def audit_llmo(soup, url, profile):
    """LLMO (Large Language Model Optimization) audit.
    
    LLMO is primarily OFF-PAGE — it depends on how AI training data includes your brand.
    This tool CANNOT:
    - Query ChatGPT/Gemini/Claude APIs to test brand knowledge (requires separate API calls + costs)
    - Crawl the entire web for brand mentions (requires SERP API subscription)
    - Access AI model training data directly
    
    This tool CAN check:
    - On-page entity signals that help AI models learn your brand identity
    - Schema.org sameAs links that connect your entity across the web
    - Structured brand data that feeds knowledge graphs
    - 'As Seen In' / press mention signals
    - Wikipedia/Wikidata linkage indicators
    """
    results = {
        "checks": [],
        "score": 0,
        "max_score": 10,
        "fixes": [],
        "off_page_recommendations": [],
        "limitations": "LLMO is primarily off-page. This audit covers on-page entity signals only. For full LLMO measurement, manually test: (1) Ask ChatGPT/Gemini/Perplexity 'What is [Brand]?' (2) Use a SERP API to count brand mentions on authority sites. (3) Check if your brand has a Wikipedia/Wikidata entry."
    }
    points = 0
    text = soup.body.get_text(separator=" ", strip=True) if soup.body else ""
    schemas = extract_existing_schema(soup)
    all_items = get_all_schema_items(schemas)
    domain = urlparse(url).netloc

    # ── 1. ENTITY IDENTITY IN SCHEMA (sameAs links) ──
    same_as_links = []
    for item in all_items:
        if "sameAs" in item:
            sa = item["sameAs"]
            if isinstance(sa, list): same_as_links.extend(sa)
            elif isinstance(sa, str): same_as_links.append(sa)

    # Categorize sameAs links
    social_platforms = {"facebook.com", "linkedin.com", "twitter.com", "x.com", "instagram.com", "youtube.com", "tiktok.com"}
    authority_platforms = {"wikipedia.org", "wikidata.org", "crunchbase.com", "bbb.org", "yelp.com", "healthgrades.com", "avvo.com", "martindale.com"}

    social_links = [l for l in same_as_links if any(p in l.lower() for p in social_platforms)]
    authority_links = [l for l in same_as_links if any(p in l.lower() for p in authority_platforms)]

    if social_links and authority_links:
        results["checks"].append({"name": "Entity sameAs Links", "status": "PASS", "detail": f"Social: {len(social_links)}, Authority: {len(authority_links)} — strong entity graph"})
        points += 3
    elif social_links:
        results["checks"].append({"name": "Entity sameAs Links", "status": "WARN", "detail": f"Social links only ({len(social_links)}). Add authority platform links."})
        points += 1
        missing_authority = []
        if profile and profile.get("industry") == "legal_debt":
            missing_authority = ["BBB (bbb.org)", "Avvo", "Martindale-Hubbell"]
        elif profile and profile.get("industry") == "mental_health":
            missing_authority = ["Healthgrades", "Psychology Today", "Zocdoc"]
        elif profile and profile.get("industry") == "financial_services":
            missing_authority = ["BBB (bbb.org)", "Trustpilot"]
        results["fixes"].append({"issue": "Missing authority platform sameAs links", "fix_type": "html_head",
            "code": f"Add to Organization schema sameAs array: {', '.join(missing_authority)}. These external profiles strengthen entity recognition in AI training data."})
    else:
        results["checks"].append({"name": "Entity sameAs Links", "status": "FAIL", "detail": "No sameAs links in schema — AI models can't connect your brand across the web"})
        results["fixes"].append({"issue": "No sameAs links in Organization schema", "fix_type": "html_head",
            "code": "Add sameAs array to Organization schema with all official profiles: social media, BBB, industry directories, Wikipedia (if exists)."})

    # ── 2. BRAND NAME CONSISTENCY ──
    brand_name = profile.get("name", "").split("(")[0].strip() if profile else ""
    if brand_name:
        # Check title, H1, meta description, schema for consistent brand name
        title_text = soup.title.string.strip() if soup.title and soup.title.string else ""
        h1_text = soup.find("h1").get_text(strip=True) if soup.find("h1") else ""
        meta_desc = soup.find("meta", attrs={"name": "description"})
        meta_text = meta_desc.get("content", "") if meta_desc else ""

        brand_in = []
        if brand_name.lower() in title_text.lower(): brand_in.append("title")
        if brand_name.lower() in h1_text.lower(): brand_in.append("H1")
        if brand_name.lower() in meta_text.lower(): brand_in.append("meta description")

        # Check schema
        for item in all_items:
            if item.get("name") and brand_name.lower() in str(item.get("name", "")).lower():
                brand_in.append("schema")
                break

        if len(brand_in) >= 3:
            results["checks"].append({"name": "Brand Name Consistency", "status": "PASS", "detail": f"Found in: {', '.join(brand_in)}"})
            points += 2
        elif brand_in:
            results["checks"].append({"name": "Brand Name Consistency", "status": "WARN", "detail": f"Found in: {', '.join(brand_in)}. Missing from other locations."})
            points += 1
        else:
            results["checks"].append({"name": "Brand Name Consistency", "status": "FAIL", "detail": f"Brand name '{brand_name}' not found in key locations"})

    # ── 3. PRESS / MEDIA MENTIONS (on-page signals) ──
    press_patterns = re.findall(r"(?:as\s+(?:seen|featured|mentioned)\s+(?:in|on)|press|media|news|coverage|featured\s+(?:in|on)|recognized\s+by)", text, re.I)
    press_logos = soup.find_all(attrs={"class": re.compile(r"press|media|logo|featured|as-seen|trusted", re.I)})
    # Also check for specific publisher names
    publishers = re.findall(r"(?:Forbes|Bloomberg|CNBC|Wall Street Journal|WSJ|New York Times|NYT|Reuters|AP News|USA Today|NerdWallet|Bankrate|Investopedia|WebMD|Healthline|Psychology Today|BuzzFeed|HuffPost)", text, re.I)

    total_press = len(press_patterns) + len(press_logos) + len(set(publishers))
    if total_press >= 3:
        results["checks"].append({"name": "Press/Media Signals", "status": "PASS", "detail": f"Press mentions: {len(press_patterns)}, Logo sections: {len(press_logos)}, Publishers: {', '.join(list(set(publishers))[:5])}"})
        points += 2
    elif total_press >= 1:
        results["checks"].append({"name": "Press/Media Signals", "status": "WARN", "detail": f"Limited press signals ({total_press})"})
        points += 1
    else:
        results["checks"].append({"name": "Press/Media Signals", "status": "WARN", "detail": "No press/media mention signals found on page"})
        results["fixes"].append({"issue": "No press mention signals", "fix_type": "content_recommendation",
            "code": "If you have media coverage, add an 'As Seen In' or 'Featured In' section with publisher logos/links. If not, this is a priority for off-page LLMO strategy."})

    # ── 4. KNOWLEDGE GRAPH INDICATORS ──
    has_org_schema = "Organization" in get_schema_types(schemas)
    has_founder = any(item.get("founder") for item in all_items)
    has_founding_date = any(item.get("foundingDate") for item in all_items)
    has_description = any(item.get("description") and len(str(item.get("description", ""))) > 50 for item in all_items)

    kg_signals = sum([has_org_schema, has_founder, has_founding_date, has_description])
    if kg_signals >= 3:
        results["checks"].append({"name": "Knowledge Graph Data", "status": "PASS", "detail": f"Organization schema with founder, founding date, description"})
        points += 2
    elif kg_signals >= 1:
        results["checks"].append({"name": "Knowledge Graph Data", "status": "WARN", "detail": f"Partial entity data ({kg_signals}/4 signals)"})
        points += 1
        missing_kg = []
        if not has_org_schema: missing_kg.append("Organization schema")
        if not has_founder: missing_kg.append("founder")
        if not has_founding_date: missing_kg.append("foundingDate")
        if not has_description: missing_kg.append("description (50+ chars)")
        results["fixes"].append({"issue": f"Incomplete knowledge graph data: missing {', '.join(missing_kg)}", "fix_type": "html_head",
            "code": "Complete the Organization schema with all entity properties. AI models build brand knowledge from structured entity data."})
    else:
        results["checks"].append({"name": "Knowledge Graph Data", "status": "FAIL", "detail": "No knowledge graph entity data found"})

    # ── OFF-PAGE RECOMMENDATIONS (cannot be automated without APIs) ──
    results["off_page_recommendations"] = [
        "🔍 MANUAL TEST: Ask ChatGPT, Gemini, and Perplexity: 'What is [Brand]?' and 'What are the best [service] companies?' — document which AI knows your brand and what it says.",
        "📰 PUBLISHER STRATEGY: Get mentioned on sites AI models cite: NerdWallet, Bankrate, Investopedia (debt), WebMD, Healthline, Psychology Today (mental health). These drive AI training data inclusion more than your own site.",
        "📊 SERP API MONITORING: Use a SERP API (Ahrefs, SEMrush, or SerpAPI) to track brand mentions across the web. This is the true LLMO metric.",
        "📖 WIKIPEDIA: If your brand qualifies for notability, a Wikipedia page is the single strongest LLMO signal. AI models weight Wikipedia extremely heavily.",
        "🔗 WIKIDATA: Even without Wikipedia, creating a Wikidata entity (wikidata.org) for your organization feeds Google Knowledge Graph directly."
    ]

    results["score"] = min(round(points), 10)
    return results


# ─────────────────────────────────────────────
# SITE PROFILES (same as v1 but referenced)
# ─────────────────────────────────────────────

SITE_PROFILES = {
    "ovlg": {
        "name": "Oak View Law Group (OVLG)",
        "domain": "ovlg.com",
        "industry": "legal_debt",
        "schema_types": ["LegalService", "Organization", "Attorney", "Person", "FAQPage", "Article", "Review", "AggregateRating", "BreadcrumbList", "WebSite", "WebPage"],
        "required_schema": {
            "LegalService": {"priority": "CRITICAL", "reason": "Primary service type for attorney-led debt settlement", "properties": ["name", "description", "provider", "areaServed", "serviceType", "url", "telephone", "address"]},
            "Organization": {"priority": "CRITICAL", "reason": "Establishes entity identity for AI models", "properties": ["name", "url", "logo", "description", "founder", "foundingDate", "address", "telephone", "sameAs", "contactPoint"]},
            "Person": {"priority": "HIGH", "reason": "Attorney E-E-A-T signals (Lyle Solomon, Loretta Kilday)", "properties": ["name", "jobTitle", "worksFor", "url", "sameAs", "knowsAbout", "hasCredential"]},
            "FAQPage": {"priority": "HIGH", "reason": "Directly feeds AI answer generation", "properties": ["mainEntity"]},
            "Article": {"priority": "MEDIUM", "reason": "Content attribution and freshness signals", "properties": ["headline", "author", "datePublished", "dateModified", "publisher", "description"]},
            "Review": {"priority": "MEDIUM", "reason": "Trust signals for YMYL content", "properties": ["reviewRating", "author", "reviewBody", "itemReviewed"]},
            "BreadcrumbList": {"priority": "MEDIUM", "reason": "Navigation structure for crawlers", "properties": ["itemListElement"]}
        },
        "ai_bots": ["GPTBot", "ClaudeBot", "Google-Extended", "Googlebot", "Bingbot", "PerplexityBot"],
        "eeat_keywords": ["attorney", "lawyer", "licensed", "bar", "JD", "legal counsel", "law firm", "Lyle Solomon", "Loretta Kilday"]
    },
    "debtcc": {
        "name": "DebtConsolidationCare (DebtCC)",
        "domain": "debtconsolidationcare.com",
        "industry": "financial_services",
        "schema_types": ["FinancialService", "Organization", "FAQPage", "Article", "Review", "AggregateRating", "BreadcrumbList", "WebSite", "WebPage"],
        "required_schema": {
            "FinancialService": {"priority": "CRITICAL", "reason": "Primary service type for debt consolidation guidance", "properties": ["name", "description", "provider", "areaServed", "serviceType", "url"]},
            "Organization": {"priority": "CRITICAL", "reason": "Establishes entity identity", "properties": ["name", "url", "logo", "description", "address", "telephone", "sameAs", "contactPoint"]},
            "Person": {"priority": "HIGH", "reason": "Attorney reviewer E-E-A-T (Loretta Kilday reviewing)", "properties": ["name", "jobTitle", "worksFor", "url", "sameAs", "knowsAbout"]},
            "FAQPage": {"priority": "HIGH", "reason": "Directly feeds AI answer generation", "properties": ["mainEntity"]},
            "Article": {"priority": "MEDIUM", "reason": "Content attribution", "properties": ["headline", "author", "datePublished", "dateModified", "publisher"]},
            "BreadcrumbList": {"priority": "MEDIUM", "reason": "Navigation structure", "properties": ["itemListElement"]}
        },
        "ai_bots": ["GPTBot", "ClaudeBot", "Google-Extended", "Googlebot", "Bingbot", "PerplexityBot"],
        "eeat_keywords": ["attorney", "reviewed by", "Loretta Kilday", "financial counselor", "certified", "accredited"]
    },
    "savantcare": {
        "name": "SavantCare",
        "domain": "savantcare.com",
        "industry": "mental_health",
        "schema_types": ["MedicalBusiness", "MedicalOrganization", "Physician", "PsychologicalTreatment", "HealthcareService", "FAQPage", "Article", "Review", "BreadcrumbList", "WebSite", "WebPage"],
        "required_schema": {
            "MedicalBusiness": {"priority": "CRITICAL", "reason": "Primary entity type for telehealth mental health provider", "properties": ["name", "description", "url", "telephone", "address", "medicalSpecialty", "availableService", "isAcceptingNewPatients"]},
            "HealthcareService": {"priority": "CRITICAL", "reason": "Service categorization for AI matching", "properties": ["name", "description", "provider", "serviceType", "areaServed", "availableChannel"]},
            "PsychologicalTreatment": {"priority": "HIGH", "reason": "Unique somatic yoga therapy positioning", "properties": ["name", "description", "howPerformed", "status", "study"]},
            "Physician": {"priority": "HIGH", "reason": "Provider credentials for E-E-A-T", "properties": ["name", "medicalSpecialty", "hospitalAffiliation", "availableService", "url"]},
            "FAQPage": {"priority": "HIGH", "reason": "Feeds AI answer generation for mental health queries", "properties": ["mainEntity"]},
            "Article": {"priority": "MEDIUM", "reason": "Content attribution and freshness", "properties": ["headline", "author", "datePublished", "dateModified", "publisher"]},
            "BreadcrumbList": {"priority": "MEDIUM", "reason": "Navigation structure", "properties": ["itemListElement"]}
        },
        "ai_bots": ["GPTBot", "ClaudeBot", "Google-Extended", "Googlebot", "Bingbot", "PerplexityBot"],
        "eeat_keywords": ["therapist", "psychiatrist", "licensed", "LMFT", "LCSW", "PsyD", "MD", "somatic", "yoga therapy", "telehealth"]
    }
}

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}


# ─────────────────────────────────────────────
# UTILITY FUNCTIONS (from v1)
# ─────────────────────────────────────────────

def fetch_page(url, timeout=15):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        return resp, soup
    except Exception as e:
        return None, None

def fetch_robots_txt(domain):
    """Fetch robots.txt, handling Next.js apps that may return HTML instead of the actual file."""
    # Try with and without www prefix
    domains_to_try = [domain]
    if not domain.startswith("www."):
        domains_to_try.append(f"www.{domain}")
    else:
        domains_to_try.append(domain.replace("www.", ""))

    for d in domains_to_try:
        for protocol in ["https", "http"]:
            try:
                url = f"{protocol}://{d}/robots.txt"
                resp = requests.get(url, headers=HEADERS, timeout=10)
                if resp.status_code == 200:
                    content = resp.text
                    # Detect if server returned HTML instead of robots.txt (common Next.js issue)
                    if content.strip().startswith("<!DOCTYPE") or content.strip().startswith("<html"):
                        continue  # Skip — server returned app shell, not robots.txt
                    # Basic validation — should contain User-agent or Sitemap
                    if "user-agent" in content.lower() or "sitemap" in content.lower() or "disallow" in content.lower():
                        return content
            except:
                continue
    return None

def fetch_sitemap(domain):
    """Fetch sitemap, trying multiple paths and also checking robots.txt for Sitemap directive."""
    results = {"found": False, "urls": [], "location": None}

    # Try with and without www prefix
    domains_to_try = [domain]
    if not domain.startswith("www."):
        domains_to_try.append(f"www.{domain}")
    else:
        domains_to_try.append(domain.replace("www.", ""))

    for d in domains_to_try:
        for path in ["/sitemap.xml", "/sitemap_index.xml", "/sitemap/"]:
            for protocol in ["https", "http"]:
                try:
                    url = f"{protocol}://{d}{path}"
                    resp = requests.get(url, headers=HEADERS, timeout=10)
                    if resp.status_code == 200 and ("<?xml" in resp.text[:100] or "<urlset" in resp.text[:500] or "<sitemapindex" in resp.text[:500]):
                        results["found"] = True
                        results["location"] = url
                        soup = BeautifulSoup(resp.text, "lxml")
                        locs = soup.find_all("loc")
                        results["urls"] = [loc.text.strip() for loc in locs[:50]]
                        return results
                except:
                    continue
    return results

def detect_site_profile(url):
    domain = urlparse(url).netloc.lower().replace("www.", "")
    for key, profile in SITE_PROFILES.items():
        if profile["domain"] in domain:
            return key, profile
    return "generic", None

def extract_existing_schema(soup):
    schemas = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string)
            if isinstance(data, list):
                schemas.extend(data)
            else:
                schemas.append(data)
        except:
            continue
    return schemas

def get_schema_types(schemas):
    types = set()
    for s in schemas:
        if "@type" in s:
            t = s["@type"]
            if isinstance(t, list): types.update(t)
            else: types.add(t)
        if "@graph" in s:
            for item in s["@graph"]:
                if "@type" in item:
                    t = item["@type"]
                    if isinstance(t, list): types.update(t)
                    else: types.add(t)
    return types

def get_all_schema_items(schemas):
    items = []
    for s in schemas:
        if "@graph" in s: items.extend(s["@graph"])
        else: items.append(s)
    return items


# ─────────────────────────────────────────────
# MODULE 1: SCHEMA AUDIT (intent-aware)
# ─────────────────────────────────────────────

def audit_schema(soup, url, profile, page_intent):
    results = {"existing_schemas": [], "existing_types": set(), "missing_critical": [], "missing_high": [], "missing_medium": [], "generated_fixes": {}, "score": 0, "max_score": 20, "intent_notes": []}
    schemas = extract_existing_schema(soup)
    results["existing_schemas"] = schemas
    existing_types = get_schema_types(schemas)
    results["existing_types"] = existing_types
    all_items = get_all_schema_items(schemas)

    if not profile:
        results["missing_critical"].append({"type": "N/A", "priority": "N/A", "reason": "No site profile — generic audit", "required_properties": []})
        return results

    required = profile.get("required_schema", {})
    intent_config = PAGE_INTENTS.get(page_intent, {})
    schema_weight = intent_config.get("optimization_focus", {}).get("schema", {}).get("weight", 1.0)
    schema_focus = intent_config.get("optimization_focus", {}).get("schema", {}).get("focus", "")

    if schema_focus:
        results["intent_notes"].append(f"Schema focus for {intent_config.get('label', page_intent)}: {schema_focus}")

    # Adjust which schemas matter based on intent
    intent_schema_priority = {}
    if page_intent == "homepage":
        # Homepage: Organization and primary service entity are CRITICAL, Article is irrelevant
        intent_schema_priority = {"Organization": "CRITICAL", "LegalService": "CRITICAL", "FinancialService": "CRITICAL", "MedicalBusiness": "CRITICAL", "HealthcareService": "HIGH", "Person": "MEDIUM", "FAQPage": "LOW", "Article": "SKIP", "Review": "MEDIUM", "BreadcrumbList": "MEDIUM"}
    elif page_intent == "informational":
        # Articles: Article, FAQPage, Person are CRITICAL
        intent_schema_priority = {"Article": "CRITICAL", "FAQPage": "CRITICAL", "Person": "HIGH", "BreadcrumbList": "HIGH", "Organization": "MEDIUM", "LegalService": "LOW", "FinancialService": "LOW", "MedicalBusiness": "LOW", "Review": "LOW"}
    elif page_intent == "lead_gen":
        # Lead gen: Service entity, FAQ (buying objections), Review are key
        intent_schema_priority = {"LegalService": "CRITICAL", "FinancialService": "CRITICAL", "MedicalBusiness": "CRITICAL", "HealthcareService": "CRITICAL", "FAQPage": "HIGH", "Review": "HIGH", "AggregateRating": "HIGH", "Person": "MEDIUM", "Organization": "MEDIUM", "Article": "SKIP", "BreadcrumbList": "MEDIUM"}
    elif page_intent == "hybrid":
        # Hybrid: BOTH service entity AND content schemas are CRITICAL — full stack
        intent_schema_priority = {"LegalService": "CRITICAL", "FinancialService": "CRITICAL", "MedicalBusiness": "CRITICAL", "HealthcareService": "CRITICAL", "Article": "CRITICAL", "FAQPage": "CRITICAL", "Person": "HIGH", "Review": "HIGH", "AggregateRating": "HIGH", "Organization": "HIGH", "BreadcrumbList": "HIGH", "PsychologicalTreatment": "HIGH"}

    points = 0
    for schema_type, info in required.items():
        effective_priority = intent_schema_priority.get(schema_type, info["priority"])
        if effective_priority == "SKIP":
            results["intent_notes"].append(f"⏭️ {schema_type} skipped — not relevant for {page_intent} pages")
            continue
        if effective_priority == "LOW":
            continue

        found = schema_type in existing_types
        if found:
            matching_items = [item for item in all_items if item.get("@type") == schema_type or (isinstance(item.get("@type"), list) and schema_type in item["@type"])]
            missing_props = [prop for prop in info["properties"] if not any(prop in item for item in matching_items)]

            if not missing_props:
                points += {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2}.get(effective_priority, 1)
            else:
                points += {"CRITICAL": 2, "HIGH": 1.5, "MEDIUM": 1}.get(effective_priority, 0.5)
                results["generated_fixes"][f"{schema_type}_props"] = {"action": "ADD_PROPERTIES", "type": schema_type, "missing_properties": missing_props, "priority": effective_priority}
        else:
            gap = {"type": schema_type, "priority": effective_priority, "reason": info["reason"], "required_properties": info["properties"]}
            if effective_priority == "CRITICAL":
                results["missing_critical"].append(gap)
            elif effective_priority == "HIGH":
                results["missing_high"].append(gap)
            else:
                results["missing_medium"].append(gap)
            results["generated_fixes"][schema_type] = generate_schema_block(schema_type, url, profile)

    results["score"] = min(round(points * schema_weight), 20)
    return results


def generate_schema_block(schema_type, url, profile):
    """Generate complete JSON-LD blocks — same templates as v1."""
    domain = urlparse(url).netloc
    base_url = f"https://{domain}"
    templates = {
        "LegalService": {"@context": "https://schema.org", "@type": "LegalService", "name": "[FIRM NAME]", "description": "[Attorney-led debt settlement description]", "url": base_url, "telephone": "[PHONE]", "address": {"@type": "PostalAddress", "streetAddress": "[STREET]", "addressLocality": "[CITY]", "addressRegion": "[STATE]", "postalCode": "[ZIP]", "addressCountry": "US"}, "areaServed": {"@type": "Country", "name": "United States"}, "serviceType": ["Debt Settlement", "Debt Negotiation", "Debt Relief"], "priceRange": "[e.g., Free consultation]"},
        "FinancialService": {"@context": "https://schema.org", "@type": "FinancialService", "name": "[COMPANY NAME]", "description": "[Description]", "url": base_url, "telephone": "[PHONE]", "address": {"@type": "PostalAddress", "streetAddress": "[STREET]", "addressLocality": "[CITY]", "addressRegion": "[STATE]", "postalCode": "[ZIP]", "addressCountry": "US"}, "serviceType": ["Debt Consolidation", "Debt Management"]},
        "Organization": {"@context": "https://schema.org", "@type": "Organization", "name": "[NAME]", "url": base_url, "logo": f"{base_url}/[LOGO.png]", "description": "[DESCRIPTION]", "founder": {"@type": "Person", "name": "[FOUNDER]"}, "foundingDate": "[YYYY]", "telephone": "[PHONE]", "sameAs": ["[FACEBOOK]", "[LINKEDIN]", "[TWITTER]"], "contactPoint": {"@type": "ContactPoint", "telephone": "[PHONE]", "contactType": "customer service"}},
        "Person": {"@context": "https://schema.org", "@type": "Person", "name": "[NAME]", "jobTitle": "[TITLE]", "worksFor": {"@type": "Organization", "name": "[FIRM]", "url": base_url}, "url": f"{base_url}/[AUTHOR-PAGE]", "sameAs": ["[LINKEDIN]"], "knowsAbout": ["[SPECIALTY]"], "hasCredential": {"@type": "EducationalOccupationalCredential", "credentialCategory": "[e.g., Juris Doctor]", "recognizedBy": {"@type": "Organization", "name": "[State Bar]"}}},
        "FAQPage": {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": "[QUESTION]", "acceptedAnswer": {"@type": "Answer", "text": "[ANSWER]"}}]},
        "Article": {"@context": "https://schema.org", "@type": "Article", "headline": "[TITLE]", "author": {"@type": "Person", "name": "[AUTHOR]", "jobTitle": "[TITLE]"}, "datePublished": "[YYYY-MM-DD]", "dateModified": "[YYYY-MM-DD]", "publisher": {"@type": "Organization", "name": "[PUBLISHER]", "logo": {"@type": "ImageObject", "url": f"{base_url}/[LOGO.png]"}}, "description": "[META DESCRIPTION]", "mainEntityOfPage": {"@type": "WebPage", "@id": url}},
        "Review": {"@context": "https://schema.org", "@type": "Review", "reviewRating": {"@type": "Rating", "ratingValue": "[1-5]", "bestRating": "5"}, "author": {"@type": "Person", "name": "[REVIEWER]"}, "reviewBody": "[REVIEW TEXT]", "itemReviewed": {"@type": "LegalService", "name": "[SERVICE]", "url": base_url}},
        "BreadcrumbList": {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [{"@type": "ListItem", "position": 1, "name": "Home", "item": base_url}, {"@type": "ListItem", "position": 2, "name": "[SECTION]", "item": f"{base_url}/[SECTION]"}, {"@type": "ListItem", "position": 3, "name": "[PAGE]", "item": url}]},
        "MedicalBusiness": {"@context": "https://schema.org", "@type": "MedicalBusiness", "name": "[PRACTICE NAME]", "description": "[DESCRIPTION]", "url": base_url, "telephone": "[PHONE]", "medicalSpecialty": ["Psychiatry", "Psychology", "CounselingAndTherapy"], "isAcceptingNewPatients": True},
        "HealthcareService": {"@context": "https://schema.org", "@type": "HealthcareService", "name": "[SERVICE]", "description": "[DESCRIPTION]", "provider": {"@type": "MedicalOrganization", "name": "[PRACTICE]", "url": base_url}, "serviceType": "[e.g., Telepsychiatry]", "areaServed": [{"@type": "State", "name": "California"}, {"@type": "State", "name": "Texas"}]},
        "PsychologicalTreatment": {"@context": "https://schema.org", "@type": "PsychologicalTreatment", "name": "[TREATMENT NAME]", "description": "[DESCRIPTION]", "howPerformed": "[METHOD]"},
        "Physician": {"@context": "https://schema.org", "@type": "Physician", "name": "[PROVIDER NAME]", "medicalSpecialty": "[SPECIALTY]", "url": f"{base_url}/[PROVIDER-PAGE]"},
        "AggregateRating": {"@context": "https://schema.org", "@type": "LegalService", "name": "[FIRM]", "aggregateRating": {"@type": "AggregateRating", "ratingValue": "[e.g., 4.8]", "reviewCount": "[COUNT]", "bestRating": "5"}}
    }
    if schema_type in templates:
        return {"action": "ADD_SCHEMA", "type": schema_type, "json_ld": templates[schema_type]}
    return {"action": "ADD_SCHEMA", "type": schema_type, "json_ld": {"@context": "https://schema.org", "@type": schema_type, "name": "[FILL IN]"}}


# ─────────────────────────────────────────────
# MODULE 2: AI CRAWLABILITY (from v1, unchanged)
# ─────────────────────────────────────────────

def audit_crawlability(soup, url, robots_txt, sitemap_info, profile):
    results = {"checks": [], "score": 0, "max_score": 20, "fixes": []}
    domain = urlparse(url).netloc.replace("www.", "")
    points = 0

    if robots_txt:
        results["checks"].append({"name": "robots.txt exists", "status": "PASS", "detail": "File found and accessible"})
        points += 1
        ai_bots = profile["ai_bots"] if profile else ["GPTBot", "ClaudeBot", "Google-Extended", "Googlebot", "Bingbot", "PerplexityBot"]
        blocked_bots = []
        allowed_bots = []
        for bot in ai_bots:
            bot_lower = bot.lower()
            blocked = False
            current_agent = None
            for line in robots_txt.split("\n"):
                line_stripped = line.strip().lower()
                if line_stripped.startswith("user-agent:"):
                    current_agent = line_stripped.split(":", 1)[1].strip()
                elif line_stripped.startswith("disallow:") and current_agent:
                    disallow_path = line_stripped.split(":", 1)[1].strip()
                    if (current_agent == "*" or current_agent == bot_lower) and disallow_path == "/":
                        blocked = True
                        break
            if blocked: blocked_bots.append(bot)
            else: allowed_bots.append(bot)

        if blocked_bots:
            results["checks"].append({"name": "AI Bot Access", "status": "FAIL", "detail": f"BLOCKED: {', '.join(blocked_bots)}"})
            fix_lines = ["# Add to robots.txt to allow AI crawlers:"]
            for bot in blocked_bots:
                fix_lines.extend([f"User-agent: {bot}", "Allow: /", ""])
            results["fixes"].append({"issue": f"AI crawlers blocked: {', '.join(blocked_bots)}", "fix_type": "robots.txt", "code": "\n".join(fix_lines)})
        else:
            results["checks"].append({"name": "AI Bot Access", "status": "PASS", "detail": f"Accessible to: {', '.join(allowed_bots)}"})
            points += 4

        if "sitemap:" in robots_txt.lower():
            results["checks"].append({"name": "Sitemap in robots.txt", "status": "PASS", "detail": "Sitemap URL declared"})
            points += 1
        else:
            results["checks"].append({"name": "Sitemap in robots.txt", "status": "WARN", "detail": "No Sitemap directive"})
            results["fixes"].append({"issue": "No sitemap in robots.txt", "fix_type": "robots.txt", "code": f"Sitemap: https://{domain}/sitemap.xml"})
    else:
        results["checks"].append({"name": "robots.txt", "status": "WARN", "detail": "No robots.txt — all crawlers allowed by default"})
        points += 3

    if sitemap_info["found"]:
        results["checks"].append({"name": "XML Sitemap", "status": "PASS", "detail": f"Found at {sitemap_info['location']} — {len(sitemap_info['urls'])} URLs"})
        points += 2
    else:
        results["checks"].append({"name": "XML Sitemap", "status": "FAIL", "detail": "No sitemap.xml found"})
        results["fixes"].append({"issue": "Missing XML sitemap", "fix_type": "file_creation", "code": f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n  <url>\n    <loc>https://{domain}/</loc>\n    <lastmod>{time.strftime("%Y-%m-%d")}</lastmod>\n    <priority>1.0</priority>\n  </url>\n</urlset>'})

    meta_robots = soup.find("meta", attrs={"name": "robots"})
    if meta_robots:
        content = meta_robots.get("content", "").lower()
        if "noindex" in content or "nofollow" in content:
            results["checks"].append({"name": "Meta Robots", "status": "FAIL", "detail": f"Restrictive: {content}"})
            results["fixes"].append({"issue": f"Meta robots blocking: {content}", "fix_type": "html_head", "code": '<meta name="robots" content="index, follow">'})
        else:
            results["checks"].append({"name": "Meta Robots", "status": "PASS", "detail": f"Meta robots: {content}"})
            points += 2
    else:
        results["checks"].append({"name": "Meta Robots", "status": "PASS", "detail": "No restrictive meta robots (default: index, follow)"})
        points += 2

    canonical = soup.find("link", rel="canonical")
    if canonical and canonical.get("href"):
        results["checks"].append({"name": "Canonical URL", "status": "PASS", "detail": f"Canonical: {canonical['href']}"})
        points += 1
    else:
        results["checks"].append({"name": "Canonical URL", "status": "WARN", "detail": "No canonical URL"})
        results["fixes"].append({"issue": "Missing canonical URL", "fix_type": "html_head", "code": f'<link rel="canonical" href="{url}" />'})

    headings = []
    for level in range(1, 7):
        for h in soup.find_all(f"h{level}"):
            headings.append({"level": level, "text": h.get_text(strip=True)[:80]})
    h1_count = len([h for h in headings if h["level"] == 1])
    if h1_count == 1:
        results["checks"].append({"name": "H1 Tag", "status": "PASS", "detail": f"Single H1: {headings[0]['text'] if headings else 'N/A'}"})
        points += 2
    elif h1_count == 0:
        results["checks"].append({"name": "H1 Tag", "status": "FAIL", "detail": "No H1 tag"})
    else:
        results["checks"].append({"name": "H1 Tag", "status": "WARN", "detail": f"Multiple H1 tags ({h1_count})"})
        points += 1

    levels_used = sorted(set(h["level"] for h in headings))
    hierarchy_ok = all(levels_used[i+1] - levels_used[i] <= 1 for i in range(len(levels_used)-1)) if len(levels_used) > 1 else True
    if hierarchy_ok and headings:
        results["checks"].append({"name": "Heading Hierarchy", "status": "PASS", "detail": f"Clean: {' → '.join(f'H{l}' for l in levels_used)}"})
        points += 2
    elif headings:
        results["checks"].append({"name": "Heading Hierarchy", "status": "WARN", "detail": f"Skipped levels: {' → '.join(f'H{l}' for l in levels_used)}"})
        points += 1

    body_text = soup.body.get_text(strip=True) if soup.body else ""
    if len(body_text) > 500:
        results["checks"].append({"name": "Server-Side Content", "status": "PASS", "detail": f"{len(body_text)} chars in initial HTML"})
        points += 2
    else:
        results["checks"].append({"name": "Server-Side Content", "status": "WARN", "detail": f"Limited content ({len(body_text)} chars)"})

    results["score"] = min(round(points), 20)
    results["headings"] = headings
    return results


# ─────────────────────────────────────────────
# MODULE 3: FAQ SCHEMA (intent-aware)
# ─────────────────────────────────────────────

def audit_faq(soup, url, profile, page_intent):
    results = {"has_faq_schema": False, "detected_questions": [], "generated_schema": None, "score": 0, "fixes": [], "intent_notes": []}
    schemas = extract_existing_schema(soup)
    if "FAQPage" in get_schema_types(schemas):
        results["has_faq_schema"] = True
        results["score"] = 5
        for item in get_all_schema_items(schemas):
            if item.get("@type") == "FAQPage" and "mainEntity" in item:
                q_count = len(item["mainEntity"]) if isinstance(item["mainEntity"], list) else 1
                results["detected_questions"].append(f"Existing FAQPage schema with {q_count} questions")
        return results

    # Intent-specific FAQ guidance
    if page_intent == "homepage":
        results["intent_notes"].append("Homepage FAQ should be light (3-5 brand questions): 'What services do you offer?', 'How do I get started?', 'Where are you located?'")
    elif page_intent == "lead_gen":
        results["intent_notes"].append("Lead-gen FAQ should address buying objections ONLY: cost, timeline, eligibility, insurance/payment, trust. Do NOT add deep educational content here.")
    elif page_intent == "informational":
        results["intent_notes"].append("Informational FAQ should be comprehensive — extract every Q&A pattern from the content for maximum AI coverage.")

    # Detect Q&A patterns
    questions = []
    all_headings = soup.find_all(re.compile(r"^h[2-4]$"))
    for h in all_headings:
        text = h.get_text(strip=True)
        if text.endswith("?") or text.lower().startswith(("what ", "how ", "why ", "when ", "where ", "who ", "can ", "do ", "does ", "is ", "are ", "will ", "should ")):
            answer_parts = []
            for sib in h.find_next_siblings():
                if sib.name and re.match(r"^h[1-4]$", sib.name): break
                if sib.name in ["p", "div", "ul", "ol"]:
                    answer_parts.append(sib.get_text(strip=True))
            answer = " ".join(answer_parts)[:500]
            if answer:
                questions.append({"question": text, "answer": answer})

    for d in soup.find_all("details"):
        summary = d.find("summary")
        if summary:
            q_text = summary.get_text(strip=True)
            a_text = d.get_text(strip=True).replace(q_text, "").strip()[:500]
            if a_text: questions.append({"question": q_text, "answer": a_text})

    for dt in soup.find_all("dt"):
        dd = dt.find_next_sibling("dd")
        if dd: questions.append({"question": dt.get_text(strip=True), "answer": dd.get_text(strip=True)[:500]})

    results["detected_questions"] = questions
    if questions:
        faq_schema = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": []}
        max_qs = 5 if page_intent in ["homepage", "lead_gen"] else 15
        for q in questions[:max_qs]:
            faq_schema["mainEntity"].append({"@type": "Question", "name": q["question"], "acceptedAnswer": {"@type": "Answer", "text": q["answer"]}})
        results["generated_schema"] = faq_schema
        results["score"] = 3
        results["fixes"].append({"issue": f"Found {len(questions)} Q&A patterns but no FAQPage schema", "fix_type": "html_head", "code": f'<script type="application/ld+json">\n{json.dumps(faq_schema, indent=2)}\n</script>'})
    else:
        results["score"] = 0
        results["fixes"].append({"issue": "No FAQ content detected. Add a FAQ section.", "fix_type": "content_recommendation", "code": None})

    return results


# ─────────────────────────────────────────────
# MODULE 4: CITABILITY (intent-aware)
# ─────────────────────────────────────────────

def audit_citability(soup, url, profile, page_intent, claude_api_key=None):
    results = {"checks": [], "score": 0, "max_score": 20, "fixes": [], "ai_analysis": None}
    intent_config = PAGE_INTENTS.get(page_intent, {})
    cite_weight = intent_config.get("optimization_focus", {}).get("citability", {}).get("weight", 1.0)
    cite_focus = intent_config.get("optimization_focus", {}).get("citability", {}).get("focus", "")

    if cite_focus:
        results["checks"].append({"name": "Intent Focus", "status": "PASS", "detail": f"Citability scope: {cite_focus}"})

    body = soup.body
    if not body:
        return results

    text = body.get_text(separator=" ", strip=True)
    points = 0

    # For homepage and lead_gen, only check entity signals — skip deep content analysis
    if page_intent in ["homepage", "lead_gen"] and cite_weight < 0.5:
        # Light citability check — entity signals only
        schemas = extract_existing_schema(soup)
        schema_types = get_schema_types(schemas)
        local_types = {"LegalService", "FinancialService", "MedicalBusiness", "Organization"}
        if local_types & schema_types:
            results["checks"].append({"name": "Entity Signals", "status": "PASS", "detail": f"Service entity schema present: {', '.join(local_types & schema_types)}"})
            points += 8
        else:
            results["checks"].append({"name": "Entity Signals", "status": "FAIL", "detail": "No service entity schema found"})

        # Check for social proof
        review_patterns = re.findall(r"(?:review|testimonial|rating|star|client said|customer)", text, re.I)
        if len(review_patterns) >= 2:
            results["checks"].append({"name": "Social Proof", "status": "PASS", "detail": f"Found {len(review_patterns)} social proof signals"})
            points += 6
        else:
            results["checks"].append({"name": "Social Proof", "status": "WARN", "detail": "Limited social proof on page"})
            results["fixes"].append({"issue": "Add social proof (reviews/testimonials)", "fix_type": "content_recommendation", "code": "Add 2-3 client testimonials with names and outcomes."})

        results["score"] = min(round(points * cite_weight), 20)
        return results

    # Full citability analysis for informational pages
    paragraphs = [p.get_text(strip=True) for p in body.find_all("p") if len(p.get_text(strip=True)) > 20]

    # 1. Definitional statements
    definition_patterns = [r"(?:is|are|refers to|means|defined as|describes)\s+(?:a|an|the)\s+\w+", r"(?:involves|includes|encompasses)\s+", r"\bis\b\s+(?:a|an|the)\s+(?:process|method|approach|strategy|technique|service|treatment|practice)"]
    definition_count = sum(1 for p in paragraphs if any(re.search(pat, p, re.I) for pat in definition_patterns))

    if definition_count >= 3:
        results["checks"].append({"name": "Definitional Statements", "status": "PASS", "detail": f"Found {definition_count} definitional statements"})
        points += 3
    elif definition_count >= 1:
        results["checks"].append({"name": "Definitional Statements", "status": "WARN", "detail": f"Only {definition_count} definitional statement(s)"})
        points += 1
        results["fixes"].append({"issue": "Add more definitional statements", "fix_type": "content_recommendation", "code": "Add clear definitions: '[Topic] is [definition].' at the start of each major section."})
    else:
        results["checks"].append({"name": "Definitional Statements", "status": "FAIL", "detail": "No definitional statements found"})

    # 2. Statistics
    stat_count = len(re.findall(r"\d+(?:\.\d+)?%", text)) + len(re.findall(r"\$[\d,]+", text))
    if stat_count >= 5:
        results["checks"].append({"name": "Statistics & Data", "status": "PASS", "detail": f"{stat_count} data points"})
        points += 3
    elif stat_count >= 2:
        results["checks"].append({"name": "Statistics & Data", "status": "WARN", "detail": f"Only {stat_count} data points"})
        points += 1
    else:
        results["checks"].append({"name": "Statistics & Data", "status": "FAIL", "detail": "Very few statistics"})
        results["fixes"].append({"issue": "Add statistics with sources", "fix_type": "content_recommendation", "code": "Include 5+ sourced statistics from CFPB, FTC, Federal Reserve, industry reports."})

    # 3. Source citations
    citation_count = len(re.findall(r"(?:according to|source:|cited from|per|as reported by)", text, re.I))
    ext_links = [a for a in soup.find_all("a", href=True) if a["href"].startswith("http") and urlparse(url).netloc not in a["href"] and any(d in a["href"].lower() for d in [".gov", ".edu", ".org", "cfpb", "ftc", "nih", "samhsa"])]
    total_citations = citation_count + len(ext_links)
    if total_citations >= 3:
        results["checks"].append({"name": "Source Citations", "status": "PASS", "detail": f"{total_citations} authoritative references"})
        points += 3
    elif total_citations >= 1:
        results["checks"].append({"name": "Source Citations", "status": "WARN", "detail": f"Only {total_citations} citation(s)"})
        points += 1
    else:
        results["checks"].append({"name": "Source Citations", "status": "FAIL", "detail": "No authoritative citations"})

    # 4. Author attribution
    author_signals = []
    if soup.find("meta", attrs={"name": "author"}): author_signals.append("Meta author tag")
    if soup.find(attrs={"class": re.compile(r"author|byline|writer|reviewer", re.I)}): author_signals.append("Author byline element")
    if re.search(r"(?:reviewed|verified|fact.?checked)\s+by", text, re.I): author_signals.append("Reviewer attribution")
    if profile:
        for kw in profile.get("eeat_keywords", []):
            if kw.lower() in text.lower(): author_signals.append(f"E-E-A-T: '{kw}'")

    if len(author_signals) >= 3:
        results["checks"].append({"name": "Author Attribution", "status": "PASS", "detail": f"{'; '.join(author_signals[:5])}"})
        points += 3
    elif author_signals:
        results["checks"].append({"name": "Author Attribution", "status": "WARN", "detail": f"Partial: {'; '.join(author_signals)}"})
        points += 1
    else:
        results["checks"].append({"name": "Author Attribution", "status": "FAIL", "detail": "No author/reviewer attribution"})
        results["fixes"].append({"issue": "No author attribution", "fix_type": "html_body", "code": '<div class="author-byline">\n  <p>Written by <a href="/about/[slug]">[Author]</a>, [Credentials]</p>\n  <p>Reviewed by <a href="/about/[slug]">[Reviewer]</a>, Attorney at Law</p>\n</div>'})

    # 5. Content depth
    word_count = len(text.split())
    if word_count >= 1500:
        results["checks"].append({"name": "Content Depth", "status": "PASS", "detail": f"{word_count} words"})
        points += 2
    elif word_count >= 800:
        results["checks"].append({"name": "Content Depth", "status": "WARN", "detail": f"{word_count} words"})
        points += 1
    else:
        results["checks"].append({"name": "Content Depth", "status": "FAIL", "detail": f"{word_count} words — too thin"})

    # 6. Structured content
    tables = soup.find_all("table")
    lists = soup.find_all(["ul", "ol"])
    if len(tables) + len(lists) >= 3:
        results["checks"].append({"name": "Structured Content", "status": "PASS", "detail": f"{len(tables)} tables, {len(lists)} lists"})
        points += 2
    elif len(tables) + len(lists) >= 1:
        results["checks"].append({"name": "Structured Content", "status": "WARN", "detail": "Limited structured elements"})
        points += 1
    else:
        results["checks"].append({"name": "Structured Content", "status": "FAIL", "detail": "No tables or structured lists"})

    # Claude AI analysis (optional — runs on informational and hybrid pages)
    if claude_api_key and page_intent in ["informational", "hybrid"]:
        try:
            industry_ctx = f"Industry: {profile.get('industry', 'general')}. Site: {profile.get('name', '')}." if profile else ""
            prompt = f"""Analyze this page content for AI citability — how likely are AI models (ChatGPT, Claude, Gemini, Perplexity) to cite this content when answering user questions? {industry_ctx}\nURL: {url}\nContent (first 3000 chars):\n{text[:3000]}\n\nScore 1-5 each dimension with ONE specific, actionable fix:\n1. DEFINITIONAL_CLARITY: Does the content provide clear, quotable definitions that AI can extract?\n2. UNIQUE_DATA: Does it contain original statistics, case study data, or proprietary research?\n3. AUTHORITY_SIGNALS: Are there named author credentials, source citations, expert quotes?\n4. STRUCTURED_ANSWERS: Does it directly answer common questions in a format AI can parse?\n5. FRESHNESS: Are there date indicators showing the content is recently updated?\n\nRespond ONLY in valid JSON, no markdown backticks, no preamble:\n{{"definitional_clarity":{{"score":N,"fix":"one specific action"}},"unique_data":{{"score":N,"fix":"one specific action"}},"authority_signals":{{"score":N,"fix":"one specific action"}},"structured_answers":{{"score":N,"fix":"one specific action"}},"freshness":{{"score":N,"fix":"one specific action"}}}}"""

            headers = {
                "Content-Type": "application/json",
                "x-api-key": claude_api_key,
                "anthropic-version": "2023-06-01"
            }
            payload = {
                "model": "claude-sonnet-4-5-20250929",
                "max_tokens": 1000,
                "messages": [{"role": "user", "content": prompt}]
            }
            api_resp = requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload, timeout=30)
            if api_resp.status_code == 200:
                api_data = api_resp.json()
                resp_text = ""
                for block in api_data.get("content", []):
                    if block.get("type") == "text":
                        resp_text += block.get("text", "")
                resp_text = resp_text.strip().replace("```json", "").replace("```", "").strip()
                results["ai_analysis"] = json.loads(resp_text)
            else:
                results["ai_analysis"] = {"error": f"API returned {api_resp.status_code}: {api_resp.text[:200]}"}
        except Exception as e:
            results["ai_analysis"] = {"error": str(e)}

    results["score"] = min(round(points * cite_weight), 20)
    return results


# ─────────────────────────────────────────────
# MODULE 5: ACCESSIBILITY (from v1, unchanged)
# ─────────────────────────────────────────────

def audit_accessibility(soup, url, resp):
    results = {"checks": [], "score": 0, "max_score": 10, "fixes": []}
    points = 0

    title = soup.find("title")
    if title and title.string and len(title.string.strip()) > 10:
        results["checks"].append({"name": "Title Tag", "status": "PASS", "detail": f"Title: {title.string.strip()[:70]}"})
        points += 1
    else:
        results["checks"].append({"name": "Title Tag", "status": "FAIL", "detail": "Missing or short title"})
        results["fixes"].append({"issue": "Missing title tag", "fix_type": "html_head", "code": "<title>[Primary Keyword] - [Brand] | [Descriptor]</title>"})

    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc and meta_desc.get("content") and len(meta_desc["content"]) >= 50:
        results["checks"].append({"name": "Meta Description", "status": "PASS", "detail": f"({len(meta_desc['content'])} chars)"})
        points += 1
    else:
        results["checks"].append({"name": "Meta Description", "status": "FAIL", "detail": "Missing or too short"})
        results["fixes"].append({"issue": "Missing meta description", "fix_type": "html_head", "code": '<meta name="description" content="[150-160 chars]" />'})

    og_tags = soup.find_all("meta", attrs={"property": re.compile(r"^og:")})
    og_types = [t.get("property") for t in og_tags]
    missing_og = [t for t in ["og:title", "og:description", "og:type", "og:url"] if t not in og_types]
    if not missing_og:
        results["checks"].append({"name": "Open Graph", "status": "PASS", "detail": "All OG tags present"})
        points += 1
    else:
        results["checks"].append({"name": "Open Graph", "status": "WARN", "detail": f"Missing: {', '.join(missing_og)}"})

    images = soup.find_all("img")
    no_alt = [img for img in images if not img.get("alt") or not img.get("alt", "").strip()]
    if images:
        ratio = (len(images) - len(no_alt)) / len(images)
        if ratio >= 0.9:
            results["checks"].append({"name": "Image Alt Text", "status": "PASS", "detail": f"{int(ratio*100)}% have alt text"})
            points += 1
        else:
            results["checks"].append({"name": "Image Alt Text", "status": "WARN", "detail": f"{len(no_alt)} missing alt text"})
    else:
        points += 1

    html_tag = soup.find("html")
    if html_tag and html_tag.get("lang"):
        results["checks"].append({"name": "Language Attr", "status": "PASS", "detail": f'lang="{html_tag["lang"]}"'})
        points += 1
    else:
        results["checks"].append({"name": "Language Attr", "status": "WARN", "detail": "Missing"})

    if soup.find("meta", attrs={"name": "viewport"}):
        results["checks"].append({"name": "Viewport", "status": "PASS", "detail": "Present"})
        points += 1
    else:
        results["checks"].append({"name": "Viewport", "status": "FAIL", "detail": "Missing"})

    if url.startswith("https://"):
        results["checks"].append({"name": "HTTPS", "status": "PASS", "detail": "Secure"})
        points += 1

    if resp:
        size_kb = len(resp.content) / 1024
        if size_kb < 3000:
            results["checks"].append({"name": "Page Size", "status": "PASS", "detail": f"{size_kb:.0f} KB"})
            points += 1

    body_text = soup.body.get_text(separator=" ", strip=True) if soup.body else ""
    sentences = [s.strip() for s in re.split(r'[.!?]+', body_text) if len(s.strip()) > 10]
    words = body_text.split()
    if sentences and words:
        avg_sl = len(words) / len(sentences)
        syllables = sum(max(1, len(re.findall(r'[aeiouy]+', w, re.I))) for w in words)
        avg_syl = syllables / len(words)
        fk = 0.39 * avg_sl + 11.8 * avg_syl - 15.59
        fk = max(1, min(20, fk))
        if fk <= 10:
            results["checks"].append({"name": "Readability", "status": "PASS", "detail": f"FK Grade {fk:.1f}"})
            points += 1
        elif fk <= 12:
            results["checks"].append({"name": "Readability", "status": "WARN", "detail": f"FK Grade {fk:.1f}"})
        else:
            results["checks"].append({"name": "Readability", "status": "FAIL", "detail": f"FK Grade {fk:.1f} — too complex"})

    results["score"] = min(round(points), 10)
    return results


# ─────────────────────────────────────────────
# STREAMLIT APP
# ─────────────────────────────────────────────

def main():
    st.set_page_config(page_title="GEO Page Optimizer v2", page_icon="🔬", layout="wide", initial_sidebar_state="expanded")

    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');
    .stApp { background: #0a0e17; color: #e2e8f0; }
    .main-header { background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #0f172a 100%); border: 1px solid #1e3a5f; border-radius: 16px; padding: 2rem; margin-bottom: 2rem; text-align: center; }
    .main-header h1 { font-family: 'Plus Jakarta Sans', sans-serif; font-weight: 800; font-size: 2.2rem; background: linear-gradient(135deg, #38bdf8, #818cf8, #c084fc); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    .main-header p { color: #94a3b8; font-family: 'Plus Jakarta Sans', sans-serif; }
    .score-card { background: #111827; border: 1px solid #1e3a5f; border-radius: 12px; padding: 1.5rem; text-align: center; margin: 0.5rem 0; }
    .score-card .score-value { font-family: 'JetBrains Mono', monospace; font-size: 2.2rem; font-weight: 700; }
    .score-card .score-label { font-family: 'Plus Jakarta Sans', sans-serif; color: #94a3b8; font-size: 0.8rem; }
    .score-good { color: #34d399; } .score-warn { color: #fbbf24; } .score-bad { color: #f87171; }
    .status-pass { color: #34d399; font-weight: 600; } .status-warn { color: #fbbf24; font-weight: 600; } .status-fail { color: #f87171; font-weight: 600; }
    .intent-card { background: #111827; border: 2px solid #818cf8; border-radius: 12px; padding: 1.5rem; margin: 1rem 0; }
    .intent-card h3 { font-family: 'Plus Jakarta Sans', sans-serif; color: #c084fc; margin: 0 0 0.5rem 0; }
    .intent-card p { color: #94a3b8; margin: 0.25rem 0; font-size: 0.9rem; }
    .framework-tag { display: inline-block; padding: 3px 10px; border-radius: 12px; font-size: 0.75rem; font-weight: 600; margin: 2px; font-family: 'JetBrains Mono', monospace; }
    .tag-primary { background: #064e3b; color: #6ee7b7; }
    .tag-skip { background: #7f1d1d; color: #fca5a5; text-decoration: line-through; }
    .tag-secondary { background: #1e3a5f; color: #93c5fd; }
    .tag-hybrid { background: #4c1d95; color: #c4b5fd; }
    .cannibalization-warning { background: #451a03; border: 1px solid #92400e; border-radius: 8px; padding: 1rem; margin: 1rem 0; color: #fcd34d; font-size: 0.9rem; }
    .hybrid-note { background: #1e1b4b; border: 1px solid #4c1d95; border-radius: 8px; padding: 1rem; margin: 1rem 0; color: #c4b5fd; font-size: 0.9rem; }
    .resource-note { background: #0c1a2e; border: 1px solid #1e3a5f; border-radius: 8px; padding: 1rem; margin: 0.5rem 0; color: #94a3b8; font-size: 0.85rem; }
    .module-header { font-family: 'Plus Jakarta Sans', sans-serif; font-weight: 700; font-size: 1.3rem; color: #e2e8f0; border-bottom: 2px solid #1e3a5f; padding-bottom: 0.5rem; margin: 1.5rem 0 1rem 0; }
    .site-badge { display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 0.75rem; font-weight: 600; font-family: 'JetBrains Mono', monospace; }
    .badge-ovlg { background: #064e3b; color: #6ee7b7; } .badge-debtcc { background: #1e3a5f; color: #93c5fd; } .badge-savantcare { background: #4c1d95; color: #c4b5fd; } .badge-generic { background: #374151; color: #9ca3af; }
    div[data-testid="stSidebar"] { background: #0f172a; }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="main-header">
        <h1>🔬 GEO Page Optimizer v2</h1>
        <p>Intent-Aware Auditing — Right optimization for the right page type</p>
    </div>
    """, unsafe_allow_html=True)

    with st.sidebar:
        st.markdown("### ⚙️ Configuration")
        url = st.text_input("🔗 Page URL to Audit", placeholder="https://www.ovlg.com/debt-settlement")
        claude_api_key = st.text_input("🔑 Claude API Key (optional — enables AI content analysis)", type="password")

        st.markdown("---")
        st.markdown("### 📋 Sites")
        for key, profile in SITE_PROFILES.items():
            st.markdown(f'<span class="site-badge badge-{key}">{profile["name"]}</span>', unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("### 🧠 Page Intent")
        intent_override = st.selectbox("Override auto-detection:", ["Auto-detect", "Homepage", "Informational Article", "Lead Gen / Service Page", "Hybrid (Educate + Convert)"])

        st.markdown("---")
        run_button = st.button("🚀 Run Full Audit", type="primary", use_container_width=True)

    if run_button and url:
        url = url.strip()
        if not url.startswith("http"):
            url = "https://" + url

        site_key, profile = detect_site_profile(url)
        domain = urlparse(url).netloc.replace("www.", "")

        if profile:
            st.markdown(f'<span class="site-badge badge-{site_key}">Detected: {profile["name"]}</span>', unsafe_allow_html=True)
        else:
            st.markdown('<span class="site-badge badge-generic">Generic audit</span>', unsafe_allow_html=True)

        with st.spinner(f"Crawling {url}..."):
            resp, soup = fetch_page(url)

        if not soup:
            st.error(f"❌ Failed to fetch {url}")
            return

        st.success(f"✅ Fetched ({len(resp.content)/1024:.0f} KB)")

        # ── PAGE INTENT DETECTION ──
        intent_map = {"Auto-detect": None, "Homepage": "homepage", "Informational Article": "informational", "Lead Gen / Service Page": "lead_gen", "Hybrid (Educate + Convert)": "hybrid"}
        override = intent_map.get(intent_override)

        if override:
            page_intent = override
            intent_data = {"detected_intent": override, "confidence": 100, "signals": {}, "reasoning": ["Manual override"], "intent_config": PAGE_INTENTS[override]}
        else:
            intent_data = detect_page_intent(url, soup, profile)
            page_intent = intent_data["detected_intent"]

        ic = intent_data["intent_config"]

        # Intent display card
        primary_tags = " ".join(f'<span class="framework-tag tag-primary">{f}</span>' for f in ic["primary_frameworks"])
        skip_tags = " ".join(f'<span class="framework-tag tag-skip">{f}</span>' for f in ic["skip_frameworks"])
        secondary_tags = " ".join(f'<span class="framework-tag tag-secondary">{f}</span>' for f in ic.get("secondary_frameworks", []))

        st.markdown(f"""
        <div class="intent-card">
            <h3>{ic['label']} — {intent_data['confidence']:.0f}% confidence</h3>
            <p>{ic['description']}</p>
            <p style="margin-top: 0.75rem;"><strong>Primary:</strong> {primary_tags}</p>
            {"<p><strong>Secondary:</strong> " + secondary_tags + "</p>" if secondary_tags else ""}
            <p><strong>Skip:</strong> {skip_tags}</p>
            <p style="color: #64748b; font-size: 0.8rem; margin-top: 0.5rem;">{ic['skip_reason']}</p>
        </div>
        """, unsafe_allow_html=True)

        # Detection reasoning
        if intent_data["reasoning"]:
            with st.expander("🔍 Intent Detection Reasoning", expanded=False):
                for r in intent_data["reasoning"]:
                    st.markdown(f"- {r}")

        # Cannibalization warning
        if ic.get("cannibalization_warning"):
            st.markdown(f'<div class="cannibalization-warning">{ic["cannibalization_warning"]}</div>', unsafe_allow_html=True)

        # Resource allocation note
        if page_intent == "informational":
            st.markdown('<div class="resource-note">💰 <strong>Resource Note:</strong> GEO-quality content requires deep research, verifiable facts, and structured data tables. Budget 2-4 hours per article vs ~1 hour for standard SEO content. Apply GEO selectively to high-value informational pages, not every page on the site.</div>', unsafe_allow_html=True)
        elif page_intent == "hybrid":
            st.markdown('<div class="resource-note">💰 <strong>Resource Note:</strong> Hybrid pages are the most resource-intensive — they need GEO-quality educational content PLUS conversion optimization. Budget 3-5 hours per page. These are your highest-value pages (treatment pages, state legal guides) — the investment pays off in both AI visibility and conversions.</div>', unsafe_allow_html=True)

        # Fetch robots.txt and sitemap
        with st.spinner("Checking robots.txt and sitemap..."):
            robots_txt = fetch_robots_txt(domain)
            sitemap_info = fetch_sitemap(domain)

        # ── RUN MODULES ──
        schema_results = audit_schema(soup, url, profile, page_intent)
        crawl_results = audit_crawlability(soup, url, robots_txt, sitemap_info, profile)
        faq_results = audit_faq(soup, url, profile, page_intent)
        cite_results = audit_citability(soup, url, profile, page_intent, claude_api_key if claude_api_key else None)
        access_results = audit_accessibility(soup, url, resp)
        ymyl_results = audit_ymyl_eeat(soup, url, profile, page_intent)

        # Intent-specific modules
        aeo_results = None
        geo_results = None
        hybrid_results = None
        llmo_results = None
        if ic.get("aeo_checks"):
            aeo_results = audit_aeo(soup, url, profile, page_intent)
        if ic.get("geo_checks"):
            geo_results = audit_geo(soup, url, profile, page_intent)
        if page_intent == "hybrid":
            hybrid_results = audit_hybrid_structure(soup, url, profile, intent_data)
        if page_intent == "homepage" or "LLMO" in ic.get("primary_frameworks", []) + ic.get("secondary_frameworks", []):
            llmo_results = audit_llmo(soup, url, profile)

        # ── SCORES ──
        st.markdown('<div class="module-header">📊 Score Overview</div>', unsafe_allow_html=True)

        all_scores = [
            ("Schema", schema_results, 20),
            ("Crawlability", crawl_results, 20),
            ("FAQ", faq_results, 5),
            ("Citability", cite_results, 20),
            ("Accessibility", access_results, 10),
            ("YMYL/E-E-A-T", ymyl_results, 15),
        ]
        if aeo_results: all_scores.append(("AEO", aeo_results, 15))
        if geo_results: all_scores.append(("GEO", geo_results, 20))
        if hybrid_results: all_scores.append(("Hybrid Structure", hybrid_results, 15))
        if llmo_results: all_scores.append(("LLMO", llmo_results, 10))

        score_cols = st.columns(len(all_scores))
        total_score = 0
        total_max = 0
        for i, (name, result, max_s) in enumerate(all_scores):
            score = result.get("score", 0) if result else 0
            total_score += score
            total_max += max_s
            pct = (score / max_s * 100) if max_s > 0 else 0
            color_class = "score-good" if pct >= 70 else "score-warn" if pct >= 40 else "score-bad"
            with score_cols[i]:
                st.markdown(f'<div class="score-card"><div class="score-value {color_class}">{score}/{max_s}</div><div class="score-label">{name}</div></div>', unsafe_allow_html=True)

        if total_max > 0:
            total_pct = total_score / total_max * 100
            color_class = "score-good" if total_pct >= 70 else "score-warn" if total_pct >= 40 else "score-bad"
            st.markdown(f'<div class="score-card" style="margin-top:1rem; border: 2px solid #1e3a5f;"><div class="score-value {color_class}">{total_score}/{total_max}</div><div class="score-label">TOTAL SCORE ({total_pct:.0f}%)</div></div>', unsafe_allow_html=True)

        # ── RENDER MODULES ──

        def render_checks(result, title, icon):
            st.markdown(f'<div class="module-header">{icon} {title}</div>', unsafe_allow_html=True)
            for note in result.get("intent_notes", []):
                st.info(note)
            for check in result.get("checks", []):
                s = check["status"]
                ic2 = "✅" if s == "PASS" else "⚠️" if s == "WARN" else "❌"
                st.markdown(f"{ic2} <span class='status-{s.lower()}'>{s}</span> **{check['name']}** — {check['detail']}", unsafe_allow_html=True)
            if result.get("fixes"):
                st.markdown("**🔧 Fixes:**")
                for fix in result["fixes"]:
                    with st.expander(f"Fix: {fix.get('issue', 'Fix')}", expanded=True):
                        st.markdown(f"**Location:** `{fix.get('fix_type', 'N/A')}`")
                        if fix.get("code"):
                            if fix.get("fix_type") == "content_recommendation":
                                st.info(fix["code"])
                            else:
                                st.code(fix["code"], language="html")

        # Schema
        st.markdown('<div class="module-header">🏗️ Schema Audit</div>', unsafe_allow_html=True)
        for note in schema_results.get("intent_notes", []):
            st.info(note)
        existing = schema_results.get("existing_types", set())
        st.markdown(f"**Existing:** {', '.join(sorted(existing)) if existing else 'None'}")
        for priority, label, gaps in [("CRITICAL", "🔴 Critical", schema_results.get("missing_critical", [])), ("HIGH", "🟠 High", schema_results.get("missing_high", [])), ("MEDIUM", "🟡 Medium", schema_results.get("missing_medium", []))]:
            if gaps:
                st.markdown(f"**{label} Missing:**")
                for gap in gaps:
                    with st.expander(f"{gap['type']} — {gap['reason']}", expanded=(priority == "CRITICAL")):
                        fix = schema_results["generated_fixes"].get(gap["type"])
                        if fix and "json_ld" in fix:
                            st.code(f'<script type="application/ld+json">\n{json.dumps(fix["json_ld"], indent=2)}\n</script>', language="html")

        # Crawlability
        render_checks(crawl_results, "AI Crawlability", "🕷️")
        if crawl_results.get("headings"):
            with st.expander("📑 Heading Structure"):
                for h in crawl_results["headings"]:
                    st.text(f"{'  ' * (h['level']-1)}H{h['level']}: {h['text']}")

        # AEO (if applicable)
        if aeo_results:
            render_checks(aeo_results, "AEO — Answer Engine Optimization", "🗣️")

        # GEO (if applicable)
        if geo_results:
            render_checks(geo_results, "GEO — Generative Engine Optimization", "🤖")
            if geo_results.get("resource_estimate"):
                re_data = geo_results["resource_estimate"]
                st.markdown(f'<div class="resource-note">📊 <strong>Resource Estimate:</strong> Current: {re_data["current_words"]} words | Target: {re_data["target_words"]}+ | Estimated effort: {re_data["estimated_hours"]} hours<br>{re_data["note"]}</div>', unsafe_allow_html=True)

        # Hybrid Structure (if applicable)
        if hybrid_results:
            render_checks(hybrid_results, "Hybrid Structure — Educate & Convert Balance", "🔀")
            if hybrid_results.get("structure_assessment"):
                sa = hybrid_results["structure_assessment"]
                verdict_color = "score-good" if sa["verdict"] == "PASS" else "score-warn" if sa["verdict"] == "NEEDS WORK" else "score-bad"
                st.markdown(f'<div class="intent-card" style="border-color: #818cf8;">', unsafe_allow_html=True)
                st.markdown(f'**Verdict:** <span class="{verdict_color}">{sa["verdict"]}</span>', unsafe_allow_html=True)
                st.markdown(f'**Content ratio:** {sa["content_ratio"]}', unsafe_allow_html=True)
                st.markdown(f'**First conversion element at:** {sa["first_conversion_at"]}', unsafe_allow_html=True)
                st.markdown(f'**Word count:** {sa["word_count"]}', unsafe_allow_html=True)
                if sa.get("edu_faqs"):
                    st.markdown(f'**Educational FAQs detected:** {len(sa["edu_faqs"])}')
                    for q in sa["edu_faqs"][:3]:
                        st.markdown(f'  - {q}')
                if sa.get("buying_faqs"):
                    st.markdown(f'**Buying FAQs detected:** {len(sa["buying_faqs"])}')
                    for q in sa["buying_faqs"][:3]:
                        st.markdown(f'  - {q}')
                st.markdown('</div>', unsafe_allow_html=True)

            # Show recommended layout for hybrid pages
            if ic.get("structure_guidance"):
                with st.expander("📐 Recommended Hybrid Page Layout", expanded=False):
                    sg = ic["structure_guidance"]
                    st.markdown(f"**Target content ratio:** {sg['content_ratio']}")
                    st.markdown(f"**Minimum words (educational section):** {sg['min_words_educational']}")
                    st.markdown(f"**Minimum words (total):** {sg['min_words_total']}")
                    st.markdown("**Recommended structure:**")
                    for i, item in enumerate(sg["recommended_layout"], 1):
                        st.markdown(f"{i}. {item}")

        # FAQ
        st.markdown('<div class="module-header">❓ FAQ Schema</div>', unsafe_allow_html=True)
        for note in faq_results.get("intent_notes", []):
            st.info(note)
        if faq_results["has_faq_schema"]:
            st.success("✅ FAQPage schema present")
        elif faq_results.get("generated_schema"):
            st.warning(f"Found {len(faq_results['detected_questions'])} Q&A patterns — no FAQPage schema")
            st.code(f'<script type="application/ld+json">\n{json.dumps(faq_results["generated_schema"], indent=2)}\n</script>', language="html")
        else:
            st.warning("No FAQ content detected")

        # Citability
        render_checks(cite_results, "Content Citability", "📝")
        if cite_results.get("ai_analysis") and "error" not in cite_results.get("ai_analysis", {}):
            st.markdown("**🤖 Claude AI Analysis:**")
            for dim, data in cite_results["ai_analysis"].items():
                if isinstance(data, dict):
                    s = data.get("score", 0)
                    color = "score-good" if s >= 4 else "score-warn" if s >= 3 else "score-bad"
                    st.markdown(f"<span class='{color}'>{'●'*s}{'○'*(5-s)}</span> **{dim.replace('_',' ').title()}** ({s}/5) — {data.get('fix','')}", unsafe_allow_html=True)
        elif cite_results.get("ai_analysis", {}).get("error"):
            st.warning(f"Claude API error: {cite_results['ai_analysis']['error'][:100]}")

        # Accessibility
        render_checks(access_results, "Accessibility", "♿")

        # YMYL / E-E-A-T
        render_checks(ymyl_results, "YMYL / E-E-A-T Signals", "🛡️")
        if ymyl_results.get("eeat_profile"):
            ep = ymyl_results["eeat_profile"]
            with st.expander("📋 E-E-A-T Profile Summary", expanded=False):
                st.markdown(f"**Industry:** {ep.get('industry', 'N/A')}")
                st.markdown(f"**YMYL schemas found:** {', '.join(ep.get('ymyl_schemas_found', [])) or 'None'}")
                st.markdown(f"**Credentials detected:** {', '.join(ep.get('credentials_detected', [])) or 'None'}")
                st.markdown(f"**Disclaimers found:** {', '.join(ep.get('disclaimers_found', [])) or 'None'}")
                st.markdown(f"**Disclaimers missing:** {', '.join(ep.get('disclaimers_missing', [])) or 'None'}")
                st.markdown(f"**Bio pages verified:** {ep.get('bio_pages_verified', 0)}")
                if ep.get("bio_pages_broken", 0) > 0:
                    st.markdown(f"**Bio pages broken:** {ep.get('bio_pages_broken', 0)} ⚠️")

        # LLMO (if applicable)
        if llmo_results:
            render_checks(llmo_results, "LLMO — Large Language Model Optimization", "🧠")
            st.markdown(f'<div class="resource-note">⚠️ <strong>LLMO Limitation:</strong> {llmo_results.get("limitations", "")}</div>', unsafe_allow_html=True)
            if llmo_results.get("off_page_recommendations"):
                with st.expander("📋 Off-Page LLMO Actions (manual)", expanded=False):
                    for rec in llmo_results["off_page_recommendations"]:
                        st.markdown(f"- {rec}")

        # ── EXPORT ──
        st.markdown('<div class="module-header">📦 Export</div>', unsafe_allow_html=True)
        all_fixes = []
        for mod_name, result in [("Schema", schema_results), ("Crawlability", crawl_results), ("AEO", aeo_results), ("GEO", geo_results), ("Hybrid Structure", hybrid_results), ("FAQ", faq_results), ("Citability", cite_results), ("Accessibility", access_results), ("YMYL/E-E-A-T", ymyl_results), ("LLMO", llmo_results)]:
            if not result: continue
            for fix in result.get("fixes", []):
                all_fixes.append({"module": mod_name, **fix})
            for key, fix in result.get("generated_fixes", {}).items():
                if "json_ld" in fix:
                    all_fixes.append({"module": mod_name, "issue": f"Missing {fix['type']} schema", "fix_type": "html_head", "code": f'<script type="application/ld+json">\n{json.dumps(fix["json_ld"], indent=2)}\n</script>'})

        if all_fixes:
            export = f"# GEO Page Optimizer v2 Report\n# URL: {url}\n# Date: {time.strftime('%Y-%m-%d %H:%M')}\n# Site: {profile['name'] if profile else 'Generic'}\n# Page Intent: {ic['label']}\n# Primary Frameworks: {', '.join(ic['primary_frameworks'])}\n# Skip: {', '.join(ic['skip_frameworks'])}\n\n"
            if ic.get("cannibalization_warning"):
                export += f"## ⚠️ CANNIBALIZATION WARNING\n{ic['cannibalization_warning']}\n\n---\n\n"
            for fix in all_fixes:
                export += f"## [{fix['module']}] {fix.get('issue', 'Fix')}\nLocation: {fix.get('fix_type', 'N/A')}\n"
                if fix.get('code'): export += f"```\n{fix['code']}\n```\n"
                export += "\n---\n\n"

            st.download_button("⬇️ Download Fixes Report", data=export, file_name=f"geo_v2_{domain}_{time.strftime('%Y%m%d')}.md", mime="text/markdown", use_container_width=True)

    elif run_button:
        st.warning("Enter a URL to audit.")

    st.markdown("---")
    st.markdown('<div style="text-align:center; color:#4b5563; font-size:0.8rem;">GEO Page Optimizer v2 — Intent-Aware Auditing for OVLG, DebtCC & SavantCare</div>', unsafe_allow_html=True)


if __name__ == "__main__":
    main()
