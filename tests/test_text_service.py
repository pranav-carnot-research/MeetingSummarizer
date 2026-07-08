import unittest
import sys
import os

# Add the parent directory to the path so we can import our modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.text_service import extract_participants, parse_timestamp

class TestTextService(unittest.TestCase):
    
    def test_extract_participants_pattern1(self):
        # Test Pattern 1: Name (Role): Text
        transcript = """
        Alice (Manager): Welcome to the meeting everyone.
        Bob (Developer): Thanks for having us.
        Charlie (Designer): I'm excited to discuss the project.
        """
        
        participants = extract_participants(transcript)
        self.assertEqual(set(participants), {"Alice", "Bob", "Charlie"})
    
    def test_extract_participants_pattern2(self):
        # Test Pattern 2: Name: Text
        transcript = """
        Alice: Hello everyone, let's start the meeting.
        Bob: Sure, I've prepared some slides.
        Charlie: I have some design ideas to share.
        """
        
        participants = extract_participants(transcript)
        self.assertEqual(set(participants), {"Alice", "Bob", "Charlie"})
    
    def test_extract_participants_pattern3(self):
        # Test Pattern 3: Speaker X
        transcript = """
        [00:01:15] Speaker 1: Let's begin the discussion.
        [00:01:30] Speaker 2: I agree with the approach.
        [00:01:45] Speaker 3: I have some concerns about the timeline.
        """
        
        participants = extract_participants(transcript)
        self.assertEqual(set(participants), {"Speaker 1", "Speaker 2", "Speaker 3"})
    
    def test_extract_participants_mixed(self):
        # Test mixed patterns
        transcript = """
        Alice (Product Manager): Welcome everyone.
        Bob: Thanks Alice.
        [00:02:15] Speaker 3: I'd like to add something.
        Charlie (Designer): Sure, go ahead.
        """
        
        participants = extract_participants(transcript)
        self.assertEqual(set(participants), {"Alice", "Bob", "Charlie", "Speaker 3"})
    
    def test_parse_timestamp_hhmmss(self):
        # Test HH:MM:SS format
        timestamp = "01:23:45"
        seconds = parse_timestamp(timestamp)
        self.assertEqual(seconds, 5025.0)  # 1*3600 + 23*60 + 45
    
    def test_parse_timestamp_mmss(self):
        # Test MM:SS format
        timestamp = "12:34"
        seconds = parse_timestamp(timestamp)
        self.assertEqual(seconds, 754.0)  # 12*60 + 34
    
    def test_parse_timestamp_with_brackets(self):
        # Test timestamp with brackets
        timestamp = "[00:45:30]"
        seconds = parse_timestamp(timestamp)
        self.assertEqual(seconds, 2730.0)  # 45*60 + 30
    
    def test_parse_timestamp_invalid(self):
        # Test invalid timestamp
        timestamp = "invalid"
        seconds = parse_timestamp(timestamp)
        self.assertIsNone(seconds)

    def test_deduplicate_actions_dicts(self):
        from services.text_service import deduplicate_actions
        
        actions = [
            {"action": "set up the web socket connection wrapper", "assignee": "Speaker 1", "due_date": "Friday", "priority": "high"},
            {"action": "Speaker 1 to build websocket connection wrapper", "assignee": "Speaker 1", "due_date": "Not specified", "priority": "medium"},
            {"action": "deploy app to staging environment", "assignee": "Speaker 2", "due_date": "Monday", "priority": "high"},
            {"action": "deploying the application to staging", "assignee": "Speaker 2", "due_date": "Monday", "priority": "high"},
            {"action": "review database indexing schema", "assignee": "Speaker 1", "due_date": "Not specified", "priority": "low"}
        ]
        
        deduped = deduplicate_actions(actions)
        
        # Verify count: should be 3 unique items
        self.assertEqual(len(deduped), 3)
        
        # Check that we kept unique tasks
        actions_list = [item["action"] for item in deduped]
        self.assertIn("set up the web socket connection wrapper", actions_list)
        self.assertIn("deploy app to staging environment", actions_list)
        self.assertIn("review database indexing schema", actions_list)

    def test_deduplicate_actions_objects(self):
        from services.text_service import deduplicate_actions
        
        class DummyActionItem:
            def __init__(self, action, assignee):
                self.action = action
                self.assignee = assignee
        
        actions = [
            DummyActionItem("configure postgres db instance", "Alice"),
            DummyActionItem("configuring the postgres database", "Alice"),
            DummyActionItem("configure postgres db instance", "Bob"), # Different assignee
            DummyActionItem("write documentation", "Alice")
        ]
        
        deduped = deduplicate_actions(actions)
        
        # Verify count: should be 3 items (the first Alice db task, the Bob db task, and the Alice doc task)
        self.assertEqual(len(deduped), 3)
        self.assertEqual(deduped[0].action, "configure postgres db instance")
        self.assertEqual(deduped[0].assignee, "Alice")
        self.assertEqual(deduped[1].assignee, "Bob")
        self.assertEqual(deduped[2].action, "write documentation")

if __name__ == '__main__':
    unittest.main()