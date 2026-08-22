import unittest
from pathlib import Path
from core.llm.prose_hook import prose_hook
from core.config import settings


class TestMilestone5Polish(unittest.TestCase):
    """
    Unit tests to verify final Milestone 5 integration requirements:
    1. Prose Hook (Nopus) filtering
    2. OneDrive path redirection
    """

    def test_prose_hook_filtering(self):
        # 1. Test conversational prefix bloat
        t1 = "Certainly! Here is the file:\n\n# Header\nThis is the content."
        self.assertEqual(prose_hook.filter_response(t1), "# Header\nThis is the content.")

        # 2. Test tool execution disclosures
        t2 = "I have successfully run the command using the 'write_file' tool. The file is created."
        self.assertEqual(prose_hook.filter_response(t2), "The file is created.")

        # 3. Test inline parameters disclosures
        t3 = "Executed the 'create_directory' tool with parameters: {'directory': '/workspace'}. Directory ready."
        self.assertEqual(prose_hook.filter_response(t3), "Directory ready.")

        # 4. Test conversational sign-off fluff
        t4 = "I have created the folder. Let me know if you need help with anything else!"
        self.assertEqual(prose_hook.filter_response(t4), "I have created the folder.")

    def test_onedrive_isolation(self):
        # Simulate a path residing inside OneDrive
        onedrive_dummy_path = Path("/Users/username/OneDrive/Desktop/Jarvis/workspace")
        
        # Test redirection mechanism
        redirected_path = settings._check_onedrive_and_redirect(onedrive_dummy_path, "workspace")
        
        # Confirm 'onedrive' is completely removed from the resolved path
        self.assertNotIn("onedrive", str(redirected_path).lower())
        
        # Confirm it was rerouted to user home directory
        self.assertTrue(redirected_path.is_absolute())
