"""
OmniAI Intent Classifier (Task #33.5)

Uses Groq Llama 3.3 70B to classify user message intent into structured JSON.
Replaces brittle regex with AI-powered understanding that handles:
- Natural language phrasings
- Hindi / Hinglish / regional languages
- Slang, typos, ambiguous queries
- Param extraction (duration, dates, emails, etc.)

The frontend retains regex detection as a fallback when AI is uncertain or unavailable.
"""

import os
import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


INTENT_SYSTEM_PROMPT = """You are OmniAI's intent classifier. Classify user messages into structured JSON.

OUTPUT FORMAT (strict JSON, no other text):
{
  "domain": "gmail" | "calendar" | "code" | "general",
  "action": "<see actions below>",
  "params": { ... },
  "confidence": 0.0 to 1.0
}

DOMAINS AND ACTIONS:

Domain "gmail" — actions:
- "show_inbox" — user wants to see emails ("show my inbox", "मेरे emails दिखाओ", "any new mail?")
- "show_unread" — only unread emails ("unread emails", "kya naya aaya?")
- "search_emails" — search by sender/topic ("find email from Rahul", "search emails about invoice")
- "send_email" — compose new email ("send email to alice@example.com", "draft a mail to my CA")
- "ask_about_emails" — AI reasoning over emails ("any urgent emails?", "what action items?", "kaun ne reply nahi kiya?", "summarize my inbox")

Domain "calendar" — actions:
- "show_events" — view scheduled events ("what's on tomorrow?", "kal ka schedule", "this week's meetings")
- "find_free_slots" — find open time ("when am I free?", "got any time tomorrow?", "suggest a meeting time", "kal free hu kya?", "find a 30 min slot")
- "create_event" — book new event ("book meeting tomorrow 3pm", "schedule call with Priya Friday", "block my calendar Tuesday afternoon")
- "ask_about_calendar" — AI reasoning ("am I overbooked?", "busy day kal?")

Domain "code" — actions:
- "execute_code" — run Python code ("run this", "execute: print(1+1)", code blocks)

Domain "general" — actions:
- "chat" — anything else (greetings, general questions, normal AI chat)

PARAM EXTRACTION RULES:

For "show_events" / "find_free_slots":
- "range": "today" | "tomorrow" | "week" | "month" | null
- "duration_minutes": integer (if mentioned, e.g. "30 min" → 30, "1 hour" → 60, "1.5 hr" → 90)

For "create_event":
- "title": string (event title)
- "datetime_hint": string (raw text describing when, e.g. "tomorrow 3pm", "Friday afternoon")
- "duration_minutes": integer (default 30 if not mentioned)
- "attendees": list of email strings if mentioned
- "add_meet": boolean (true if "video call", "meet", "zoom", "online")

For "search_emails":
- "query": string (what to search for)

For "send_email":
- "to": string (recipient email if mentioned)
- "topic": string (what the email is about)

For "ask_about_emails" / "ask_about_calendar":
- "raw_query": original message (passed to deeper AI handler)

For all: include "confidence" 0.0 to 1.0 (be honest, use <0.7 when ambiguous)

EXAMPLES:

User: "show me my inbox"
→ {"domain":"gmail","action":"show_inbox","params":{},"confidence":0.95}

User: "kya aaj koi urgent email hai?"
→ {"domain":"gmail","action":"ask_about_emails","params":{"raw_query":"kya aaj koi urgent email hai?"},"confidence":0.9}

User: "find emails from rahul about Q3 budget"
→ {"domain":"gmail","action":"search_emails","params":{"query":"from:rahul Q3 budget"},"confidence":0.95}

User: "got any time tomorrow?"
→ {"domain":"calendar","action":"find_free_slots","params":{"range":"tomorrow","duration_minutes":30},"confidence":0.9}

User: "kal mujhe 1 ghante ka time chahiye"
→ {"domain":"calendar","action":"find_free_slots","params":{"range":"tomorrow","duration_minutes":60},"confidence":0.9}

User: "schedule a call with Priya tomorrow at 3pm for 45 mins"
→ {"domain":"calendar","action":"create_event","params":{"title":"Call with Priya","datetime_hint":"tomorrow 3pm","duration_minutes":45,"add_meet":true},"confidence":0.92}

User: "what's on my calendar this week?"
→ {"domain":"calendar","action":"show_events","params":{"range":"week"},"confidence":0.95}

User: "block Friday afternoon for deep work"
→ {"domain":"calendar","action":"create_event","params":{"title":"Deep work","datetime_hint":"Friday afternoon","duration_minutes":120,"add_meet":false},"confidence":0.85}

User: "run this: print('hello')"
→ {"domain":"code","action":"execute_code","params":{},"confidence":0.95}

User: "what is the capital of France?"
→ {"domain":"general","action":"chat","params":{},"confidence":0.95}

User: "hi"
→ {"domain":"general","action":"chat","params":{},"confidence":0.99}

User: "december"  (ambiguous, just a word)
→ {"domain":"general","action":"chat","params":{},"confidence":0.4}

CRITICAL RULES:
- Output ONLY the JSON object. No markdown, no preamble, no explanation.
- If user message is in Hindi/Hinglish/regional language, classify same way.
- If unsure, set confidence below 0.7 and pick best guess.
- Never invent params that weren't in the message.
"""


async def classify_intent(message: str, current_mode: str = "normal") -> Dict[str, Any]:
    """
    Classify a user message into structured intent JSON using Groq.
    
    Args:
        message: User's raw message
        current_mode: Active mode pill ('normal' | 'email' | 'calendar' | 'code')
                      Used as a HINT only, doesn't override clear AI classification.
    
    Returns:
        Dict with: domain, action, params, confidence
        On failure: returns low-confidence general fallback
    """
    try:
        from groq import Groq
        
        client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        
        # Append mode hint to system prompt (soft hint, not override)
        mode_hint = ""
        if current_mode != "normal":
            mode_labels = {
                "email": "User has Email mode active — bias toward gmail domain when ambiguous.",
                "calendar": "User has Calendar mode active — bias toward calendar domain when ambiguous.",
                "code": "User has Code mode active — bias toward code domain when ambiguous."
            }
            mode_hint = f"\n\nCONTEXT: {mode_labels.get(current_mode, '')}"
        
        full_system = INTENT_SYSTEM_PROMPT + mode_hint
        
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": full_system},
                {"role": "user", "content": message}
            ],
            temperature=0.1,
            max_tokens=300,
            response_format={"type": "json_object"}
        )
        
        raw_response = completion.choices[0].message.content
        result = json.loads(raw_response)
        
        # Validate required fields
        if not isinstance(result, dict):
            raise ValueError("Response is not a dict")
        if "domain" not in result or "action" not in result:
            raise ValueError("Missing required fields")
        
        # Ensure params and confidence exist
        result.setdefault("params", {})
        result.setdefault("confidence", 0.5)
        
        # Clamp confidence
        try:
            result["confidence"] = max(0.0, min(1.0, float(result["confidence"])))
        except (ValueError, TypeError):
            result["confidence"] = 0.5
        
        logger.info(f"Intent classified: domain={result['domain']}, action={result['action']}, confidence={result['confidence']:.2f}")
        return result
        
    except Exception as e:
        logger.warning(f"Intent classification failed, returning fallback: {e}")
        # Fallback: low-confidence general chat → frontend will use regex
        return {
            "domain": "general",
            "action": "chat",
            "params": {},
            "confidence": 0.0,
            "_error": str(e)
        }