import os
import sys
import re
import json
import torch
from typing import List, Dict

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.lg import summarize_meeting
from services.llm_service import get_llm
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

# ── Load DeBERTa NLI Model ──
print("Loading DeBERTa-v3-base NLI Model (this might take a minute on first run)...")
from transformers import AutoTokenizer, AutoModelForSequenceClassification

device = "cuda" if torch.cuda.is_available() else "cpu"
model_name = "cross-encoder/nli-deberta-v3-base"

tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForSequenceClassification.from_pretrained(model_name).to(device)
model.eval()

# Retrieve label mappings from the model config
# For deberta-v3 NLI models, typically:
# 0: entailment, 1: neutral, 2: contradiction
id2label = model.config.id2label
print(f"Model labels: {id2label}")

# ── Helper: Decompose Sentence into Atomic Claims using LLM ──
def decompose_claims(sentence: str) -> List[str]:
    """Decompose a complex sentence into a list of atomic, single-claim assertions."""
    llm = get_llm(temperature=0.0, purpose="general")
    
    system_prompt = """You are a precise statement analyst.
Your task is to decompose a complex sentence from a meeting summary into a list of simple, single-claim assertions (atomic claims).
Each claim must contain exactly one subject, one action, and one object/context, and be standalone (resolve pronouns like 'he', 'they', 'the switch' to actual nouns where clear).

Example:
Sentence: "He has to create the Jira tickets and update the PRD and RFP."
Output format:
[
  "Speaker 3 has to create the Jira tickets",
  "Speaker 3 has to update the PRD",
  "Speaker 3 has to update the RFP"
]

Return ONLY a JSON array of strings. Do not include markdown code blocks or explanations."""

    prompt = ChatPromptTemplate.from_messages([
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"Sentence: {sentence}")
    ])
    
    try:
        chain = prompt | llm | JsonOutputParser()
        claims = chain.invoke({})
        if isinstance(claims, list):
            return claims
        return [sentence]
    except Exception as e:
        print(f"Error decomposing sentence: {e}")
        return [sentence]

# ── Helper: Retrieve Best Transcript Segment ──
def get_best_segment(claim: str, transcript_lines: List[str], window_size: int = 6, step: int = 2) -> str:
    """Retrieve the transcript segment (sliding window of lines) most relevant to the claim."""
    claim_words = set(re.findall(r'\b\w+\b', claim.lower()))
    
    # Filter out common stopwords to focus on semantic content
    stopwords = {
        'the', 'a', 'an', 'and', 'or', 'but', 'is', 'are', 'was', 'were', 
        'to', 'of', 'in', 'on', 'at', 'for', 'with', 'by', 'that', 'this', 
        'these', 'those', 'it', 'he', 'she', 'they', 'we', 'i', 'you', 'my', 'your'
    }
    claim_words = claim_words - stopwords
    
    if not claim_words:
        return "\n".join(transcript_lines[:window_size])
        
    best_window = ""
    best_score = -1
    
    for i in range(0, len(transcript_lines) - window_size + 1, step):
        window = transcript_lines[i:i+window_size]
        window_text = "\n".join(window)
        window_words = set(re.findall(r'\b\w+\b', window_text.lower()))
        
        # Word overlap count
        overlap = claim_words.intersection(window_words)
        score = len(overlap)
        
        if score > best_score:
            best_score = score
            best_window = window_text
            
    return best_window

# ── Helper: Run NLI Inference ──
def run_nli(premise: str, hypothesis: str) -> Dict[str, float]:
    """Run DeBERTa NLI on a (Premise, Hypothesis) pair."""
    # Tokenize the pair
    inputs = tokenizer(premise, hypothesis, return_tensors="pt", truncation=True, max_length=512).to(device)
    
    with torch.no_grad():
        outputs = model(**inputs)
        
    # Get softmax probabilities
    probs = torch.softmax(outputs.logits, dim=1).cpu().numpy()[0]
    
    # Map probabilities to labels
    results = {}
    for idx, prob in enumerate(probs):
        label = id2label[idx].lower()
        results[label] = float(prob)
        
    return results

# ── Test Execution ──
if __name__ == "__main__":
    # 1. Defined Double-Length Transcript for Testing
    test_transcript = """Aarav: Alright, let’s get started. Thanks for jumping on quickly, guys. We have two main things on the agenda today. First, we need to lock down the feature scope for the Q3 release of the analytics dashboard. Second, Priya, we need to make a final call on whether we are migrating the database backend to PostgreSQL this quarter or pushing it to Q4.

Priya: Hey Aarav. Yeah, regarding the database migration—my team ran some benchmarks last week. MySQL is choking on our heavy aggregation queries for the sports analytics data, especially when extracting the IPL live-feed JSON stats. PostgreSQL handles those JSONB operations significantly faster. I strongly recommend we do the switch now rather than waiting.

Kabir: Wait, if we do the migration now, will it impact the Q3 product launch timeline? We promised marketing a hard launch date of September 1st. If the database transition causes downtime or delays the dashboard features, it's going to mess up the entire campaign.

Priya: It shouldn't delay the frontend features if we split the team. I can have Rohan handle the schema migration and data transfer script, while Meera continues working on the dashboard's UI components. We will need a 2-hour scheduled maintenance window for the actual cutover, likely on a Sunday morning to minimize user impact.

Aarav: Okay, a 2-hour window on a Sunday is manageable. Let's make the executive decision here: we are officially greenlighting the PostgreSQL migration for Q3. Priya, please own the migration blueprint and make sure Rohan starts on that data script early next week.

Priya: Sounds good. I'll document the schema changes in Confluence by this Friday so everyone is aligned.

Aarav: Perfect. Now let's pivot to the dashboard features. We have three main items on the table: the real-time scoreboard extraction widget, the automated PDF report generator, and the predictive trends chart. Kabir, what are you seeing from the user feedback side?

Kabir: The real-time scoreboard widget is a must-have. Users are explicitly asking for the ability to pull match data instantly. However, the automated PDF report generator is less urgent. Most users say they just screenshot the UI anyway. I say we push the PDF reports to Q4 and prioritize the predictive trends chart instead.

Aarav: I agree with dropping the PDF generator for now. Let's scope Q3 to just the Scoreboard Extraction Widget and the Predictive Trends Chart. Kabir, can you update the PRD (Product Requirement Document) to reflect this new scope?

Kabir: On it. I'll update the PRD and update the Jira tickets by tomorrow afternoon.

Aarav: Great. Priya, from a technical standpoint, do we have everything we need for the predictive trends feature? I know it relies on that new ML model pipeline.

Priya: Mostly, yes. The model is ready, but we need to verify its API latency when under heavy load. I'll set up a load test for the model endpoint this week to ensure it doesn't slow down the dashboard rendering. I'll need until next Wednesday to share those performance numbers.

Aarav: Perfect, let's target next Thursday's sync to review those latency numbers. That's all for today. Thanks, team!"""

    participants = ["Speaker 1", "Speaker 2", "Speaker 3", "Charlie"]
    
    # 2. Generate Summary using our Refactored Agent Code (runs the sequential chunk loop!)
    print("\n--- Generating Summary and Actions from Agent Node... ---")
    result = summarize_meeting(test_transcript, participants)
    
    meeting_summary = result.get("meeting_summary", {})
    action_items = result.get("action_items", [])
    
    print("\n[GENERATED MEETING SUMMARY]")
    print(f"Summary Paragraph: {meeting_summary.get('summary')}")
    print(f"Key Points: {meeting_summary.get('key_points')}")
    print(f"Decisions: {meeting_summary.get('decisions')}")
    print(f"Action Items: {action_items}")
    
    # 3. Deconstruct and Test Factual Consistency
    print("\n--- Starting Deconstruct & NLI Verification ---")
    
    transcript_lines = [line.strip() for line in test_transcript.split('\n') if line.strip()]
    
    # Compile all draft statements to verify
    summary_sentences = [s.strip() for s in re.split(r'(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\?)\s', meeting_summary.get('summary', '')) if s.strip()]
    key_points = meeting_summary.get('key_points', [])
    decisions = meeting_summary.get('decisions', [])
    actions = [f"{item.get('assignee', 'Unassigned')} is assigned to: {item.get('action')}" for item in action_items if isinstance(item, dict)]
    
    all_statements = []
    for s in summary_sentences:
        all_statements.append(("Summary Sentence", s))
    for kp in key_points:
        all_statements.append(("Key Point", kp))
    for dec in decisions:
        all_statements.append(("Decision", dec))
    for act in actions:
        all_statements.append(("Action Item", act))
        
    print(f"Total Statements to Verify: {len(all_statements)}")
    
    contradiction_count = 0
    
    for category, statement in all_statements:
        print(f"\n──────────────────────────────────────────────────")
        print(f"[{category.upper()}]: {statement}")
        
        # Decompose statement into atomic claims using LLM
        print("Decomposing into atomic claims...")
        claims = decompose_claims(statement)
        
        for idx, claim in enumerate(claims):
            # Retrieve premise
            premise = get_best_segment(claim, transcript_lines, window_size=5, step=2)
            
            # Run NLI
            nli_probs = run_nli(premise, claim)
            
            # Print metrics
            entail = nli_probs.get('entailment', nli_probs.get('entail', 0.0))
            neutral = nli_probs.get('neutral', 0.0)
            contradict = nli_probs.get('contradiction', nli_probs.get('contradict', 0.0))
            
            print(f"  Claim {idx+1}: '{claim}'")
            print(f"    -> Entailment: {entail:.3f} | Neutral: {neutral:.3f} | Contradiction: {contradict:.3f}")
            
            if contradict > 0.5:
                print(f"    [ALERT - FACTUAL INCONSISTENCY DETECTED!]")
                print(f"    Premise used (Transcript Segment):")
                print(f"    ---------------------------------------")
                print(premise)
                print(f"    ---------------------------------------")
                contradiction_count += 1
            else:
                print(f"    [Factual Integrity Verified]")
                
    print("\n==================================================")
    print(f"NLI Verification Complete. Total Contradictions Found: {contradiction_count}")
    print("==================================================")
