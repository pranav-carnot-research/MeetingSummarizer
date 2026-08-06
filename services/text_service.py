import re
from typing import List, Optional, Dict, Any
import logging

# Configure logging
logger = logging.getLogger("text-service")

def extract_participants(transcript: str) -> List[str]:
    """
    Extract participant names from the meeting transcript.
    Supports multiple languages by looking for patterns rather than specific words.
    
    Args:
        transcript (str): The meeting transcript
        
    Returns:
        list: Unique participant names
    """
    participants = set()
    
    # Pattern 1: Name (Role): Text - works for English and transliterated Hindi
    pattern1 = r'([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)\s*\([^)]+\):'
    matches1 = re.findall(pattern1, transcript)
    for name in matches1:
        participants.add(name.strip())
    
    # Pattern 2: Name: Text - works for English and transliterated Hindi
    pattern2 = r'(?:^|\n)[^\S\r\n]*([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)\s*:'
    matches2 = re.findall(pattern2, transcript)
    for name in matches2:
        participants.add(name.strip())
        
    # Pattern 3: Speaker X (from audio transcription) - language independent
    pattern3 = r'Speaker[\s_](\d+)'
    matches3 = re.findall(pattern3, transcript)
    for speaker_num in matches3:
        participants.add(f"Speaker {speaker_num}")
    
    # If we found participants, return them
    if participants:
        return sorted(list(participants))
    
    # If no participants found, try a more general approach for names
    # This is a fallback method that might catch more names but could include false positives.
    # We split by sentence boundaries (. ! ?) and newlines to find sentences/lines,
    # then for each sentence/line we skip the first word to avoid capitalization due to grammar.
    sentences = re.split(r'[.!?]|\n', transcript)
    potential_names = set()
    
    exclude_words = {
        # Original common words
        "I", "We", "The", "This", "They", "Monday", "Tuesday", "Wednesday", 
        "Thursday", "Friday", "Saturday", "Sunday", "January", "February", 
        "March", "April", "May", "June", "July", "August", "September",
        "October", "November", "December", "Hello", "Hi", "Thanks", "Yes",
        "No", "Ok", "Okay", "Perfect", "Great", "Good", "Today", "Tomorrow",
        # English pronouns, prepositions, conjunctions, and common sentence starters
        "Actually", "Basically", "Obviously", "Please", "Let", "Lets", "Why", "How", 
        "Who", "What", "Where", "When", "Which", "Whose", "Whatever", "Whoever", 
        "Yeah", "Not", "So", "But", "And", "Or", "For", "With", "Without", "About", 
        "Above", "Below", "After", "Before", "During", "Under", "Over", "Through", 
        "Between", "Among", "Against", "Into", "Onto", "Upon", "Out", "From", "To", 
        "By", "At", "In", "On", "Of", "He", "She", "It", "Them", "Their", "Theirs", 
        "Him", "Her", "Hers", "His", "Its", "Your", "Yours", "My", "Mine", "Our", 
        "Ours", "Us", "Me", "You", "Yourself", "Themselves", "Ourselves", "Myself", 
        "Himself", "Herself", "Itself", "Someone", "Somebody", "Something", "Anyone", 
        "Anybody", "Anything", "Everyone", "Everybody", "Everything", "Nothing", "None",
        # Common verbs, helping verbs, and modals
        "Am", "Is", "Are", "Was", "Were", "Be", "Been", "Being", "Have", "Has", "Had", 
        "Do", "Does", "Did", "Can", "Could", "Shall", "Should", "Will", "Would", "May", 
        "Might", "Must", "Get", "Got", "Go", "Went", "Make", "Made", "Take", "Took",
        # Adverbs, adjectives, and other fillers
        "Speaker", "Anyway", "Anyways", "Generally", "Specifically", "Normally", 
        "Usually", "Sometimes", "Always", "Never", "Often", "Seldom", "Rarely", 
        "Maybe", "Perhaps", "Probably", "Definitely", "Absolutely", "Certainly", 
        "Sure", "Surely", "Indeed", "Exactly", "Really", "Right", "Wrong", "True", 
        "False", "Alright", "Yep", "Naw", "Nope", "Design", "Earlier", "Every", 
        "Just", "Like", "Many", "Now", "Nowadays", "Oh", "One", "Recent", "Senior", 
        "Technically", "That", "Then", "There", "Two", "Using", "Whether", "Another",
        # Project/Tech stack specific terms
        "Langchain", "Langra", "Ollama", "Whisper", "Pyannote", "Fastapi", "Streamlit", 
        "Uvicorn", "Python", "Markdown", "Github", "Docker", "Api", "Llm", "App",
        "Karma"
    }

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        # Split sentence into words, keeping punctuation-free tokens
        words = re.findall(r'\b\w+\b', sentence)
        if len(words) <= 1:
            continue
        # Ignore the first word as it's capitalized for grammar
        candidate_words = words[1:]
        for word in candidate_words:
            # Match words starting with a capital letter followed by lowercase letters
            if re.match(r'^[A-Z][a-z]+$', word):
                if word not in exclude_words:
                    potential_names.add(word)

    # Only use this method if the others failed and we found potential names
    if not participants and potential_names:
        return sorted(list(potential_names))

    return sorted(list(participants))

def parse_timestamp(timestamp_str: str) -> Optional[float]:
    """
    Parse a timestamp string in HH:MM:SS format to seconds
    
    Args:
        timestamp_str: Timestamp string in HH:MM:SS format
        
    Returns:
        Seconds as float or None if invalid format
    """
    try:
        if not timestamp_str:
            return None
            
        # Remove brackets if present
        timestamp_str = timestamp_str.strip('[]')
        
        parts = timestamp_str.split(':')
        if len(parts) == 3:
            # HH:MM:SS format
            hours, minutes, seconds = parts
            return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
        elif len(parts) == 2:
            # MM:SS format
            minutes, seconds = parts
            return int(minutes) * 60 + float(seconds)
        else:
            return float(timestamp_str)
    except:
        return None

def extract_timestamps_and_speakers(transcript: str) -> List[Dict[str, Any]]:
    """
    Extract timestamps and speaker information from a transcript
    
    Args:
        transcript: Text transcript with timestamps and speakers
        
    Returns:
        List of segments with speaker, text, and time information
    """
    segments = []
    
    # Pattern for lines with timestamps: [HH:MM:SS] Speaker X: Text
    pattern = r'\[([0-9:]+)\]\s*(\w+(?:\s+\w+)*)\s*:\s*(.+)'
    
    for line in transcript.split('\n'):
        line = line.strip()
        if not line:
            continue
            
        match = re.match(pattern, line)
        if match:
            timestamp_str, speaker, text = match.groups()
            timestamp = parse_timestamp(timestamp_str)
            
            # If we have a valid timestamp and speaker
            if timestamp is not None:
                # Extract speaker number if this is "Speaker X"
                speaker_num = None
                if "Speaker" in speaker:
                    speaker_match = re.search(r'Speaker\s+(\d+)', speaker)
                    if speaker_match:
                        speaker_num = speaker_match.group(1)
                
                segments.append({
                    "speaker": speaker_num if speaker_num else speaker,
                    "text": text.strip(),
                    "start_time": timestamp,
                    # Estimate end time as start + 0.2s per character (rough approximation)
                    "end_time": timestamp + len(text) * 0.2,
                    "is_parsed": True
                })
        else:
            # Try alternate patterns or add as plain text
            segments.append({
                "speaker": "Unknown",
                "text": line,
                "start_time": 0 if not segments else segments[-1].get("end_time", 0),
                "end_time": 0 if not segments else segments[-1].get("end_time", 0) + len(line) * 0.2,
                "is_parsed": False
            })
    
    return segments

def deduplicate_actions(actions: List[Any]) -> List[Any]:
    """
    Remove duplicate action items based on assignee and semantic word overlap.
    Handles both dictionaries (from raw JSON parser) and Pydantic/object models.
    """
    def normalize_word(word):
        synonyms = {
            'db': 'database',
            'websocket': 'web_socket',
            'app': 'application',
            'repo': 'repository',
            'doc': 'documentation',
            'docs': 'documentation',
            'config': 'configure',
            'configurations': 'configure',
            'configuration': 'configure',
            'setup': 'set_up',
        }
        word = synonyms.get(word, word)
        
        # Split compound synonyms to help matching (e.g. web_socket -> web, socket)
        if '_' in word:
            return word.split('_')
        
        if len(word) > 4:
            return [word[:4]]
        return [word]

    deduplicated = []
    stop_words = {'to', 'the', 'a', 'an', 'and', 'or', 'for', 'of', 'in', 'on', 'at', 'with', 'by', 'speaker', '1', '2', '3', '4', '5', '6', '7', '8', '9'}
    
    for item in actions:
        is_dup = False
        
        # Extract action and assignee whether item is a dict or an object
        if isinstance(item, dict):
            action_text = item.get("action", "")
            assignee = item.get("assignee", "Unassigned")
        else:
            action_text = getattr(item, "action", "")
            assignee = getattr(item, "assignee", "Unassigned")
            
        if not action_text:
            continue
            
        # Extract clean words, normalize them and filter stop words
        clean_new = "".join(c for c in action_text.lower() if c.isalnum() or c.isspace()).split()
        words_new = set()
        for w in clean_new:
            if w not in stop_words:
                words_new.update(normalize_word(w))
        
        for existing in deduplicated:
            if isinstance(existing, dict):
                ex_action = existing.get("action", "")
                ex_assignee = existing.get("assignee", "Unassigned")
            else:
                ex_action = getattr(existing, "action", "")
                ex_assignee = getattr(existing, "assignee", "Unassigned")
                
            # Only compare items assigned to the same person (case insensitive)
            if assignee.lower().strip() == ex_assignee.lower().strip():
                clean_ex = "".join(c for c in ex_action.lower() if c.isalnum() or c.isspace()).split()
                words_ex = set()
                for w in clean_ex:
                    if w not in stop_words:
                        words_ex.update(normalize_word(w))
                
                if words_new and words_ex:
                    intersection = words_new.intersection(words_ex)
                    overlap = len(intersection) / min(len(words_new), len(words_ex))
                    if overlap >= 0.50: # 50% key-word similarity threshold after normalization
                        is_dup = True
                        break
        if not is_dup:
            deduplicated.append(item)
            
    return deduplicated