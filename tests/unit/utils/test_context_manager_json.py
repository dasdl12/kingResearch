# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import json
import unittest

from langchain_core.messages import ToolMessage

from src.utils.context_manager import ContextManager


class TestContextManagerJSONCompression(unittest.TestCase):
    """Test JSON compression in ContextManager"""

    def setUp(self):
        self.context_manager = ContextManager(
            token_limit=1000,
            preserve_prefix_message_count=0,
            enable_smart_summary=True,
            sliding_window_size=5
        )

    def test_compress_json_array(self):
        """Test that JSON arrays are compressed while preserving structure"""
        # Create a large JSON array similar to web_search results
        large_array = [
            {"url": f"https://example.com/{i}", "title": f"Title {i}", "score": 0.9}
            for i in range(20)
        ]
        json_content = json.dumps(large_array, ensure_ascii=False)
        
        # Create a ToolMessage with this content
        tool_msg = ToolMessage(content=json_content, tool_call_id="test_id")
        
        # Compress the message
        compressed_msg = self.context_manager._summarize_message(tool_msg, max_tokens=100)
        
        # Verify the compressed content is valid JSON
        try:
            compressed_data = json.loads(compressed_msg.content)
            self.assertIsInstance(compressed_data, list)
            # Should have fewer elements than original
            self.assertLess(len(compressed_data), len(large_array))
            # But should still have some elements
            self.assertGreater(len(compressed_data), 0)
            # First and last elements should be preserved
            if len(compressed_data) >= 2:
                self.assertEqual(compressed_data[0]["url"], large_array[0]["url"])
                self.assertEqual(compressed_data[-1]["url"], large_array[-1]["url"])
        except json.JSONDecodeError as e:
            self.fail(f"Compressed content is not valid JSON: {e}")

    def test_compress_json_object(self):
        """Test that JSON objects are compressed while preserving important fields"""
        # Create a JSON object with many fields
        large_object = {
            "url": "https://example.com",
            "title": "Important Title",
            "score": 0.95,
            "content": "Very long content " * 100,
            "raw_content": "Even longer raw content " * 200,
            "metadata": {"key1": "value1", "key2": "value2"}
        }
        json_content = json.dumps(large_object, ensure_ascii=False)
        
        # Create a ToolMessage with this content
        tool_msg = ToolMessage(content=json_content, tool_call_id="test_id")
        
        # Compress the message
        compressed_msg = self.context_manager._summarize_message(tool_msg, max_tokens=50)
        
        # Verify the compressed content is valid JSON
        try:
            compressed_data = json.loads(compressed_msg.content)
            self.assertIsInstance(compressed_data, dict)
            # Important fields should be preserved
            self.assertIn("url", compressed_data)
            self.assertEqual(compressed_data["url"], large_object["url"])
        except json.JSONDecodeError as e:
            self.fail(f"Compressed content is not valid JSON: {e}")

    def test_truncate_json_content(self):
        """Test that truncation also preserves JSON structure"""
        # Create a large JSON array
        large_array = [
            {"url": f"https://example.com/{i}", "title": f"Title {i}"}
            for i in range(15)
        ]
        json_content = json.dumps(large_array, ensure_ascii=False)
        
        # Create a ToolMessage with this content
        tool_msg = ToolMessage(content=json_content, tool_call_id="test_id")
        
        # Truncate the message
        truncated_msg = self.context_manager._truncate_message_content(tool_msg, max_tokens=100)
        
        # Verify the truncated content is valid JSON
        try:
            truncated_data = json.loads(truncated_msg.content)
            self.assertIsInstance(truncated_data, list)
            # Should have fewer elements than original
            self.assertLess(len(truncated_data), len(large_array))
        except json.JSONDecodeError as e:
            self.fail(f"Truncated content is not valid JSON: {e}")

    def test_non_json_content_unchanged(self):
        """Test that non-JSON content is processed normally"""
        # Create a ToolMessage with non-JSON content
        non_json_content = "This is just plain text with some information."
        tool_msg = ToolMessage(content=non_json_content, tool_call_id="test_id")
        
        # Compress the message
        compressed_msg = self.context_manager._summarize_message(tool_msg, max_tokens=50)
        
        # Should be marked as summarized
        self.assertIn("[SUMMARIZED]", compressed_msg.content)

    def test_empty_json_array(self):
        """Test that empty JSON arrays are handled correctly"""
        json_content = "[]"
        tool_msg = ToolMessage(content=json_content, tool_call_id="test_id")
        
        compressed_msg = self.context_manager._summarize_message(tool_msg, max_tokens=50)
        
        # Should remain as empty array
        self.assertEqual(compressed_msg.content, "[]")

    def test_empty_json_object(self):
        """Test that empty JSON objects are handled correctly"""
        json_content = "{}"
        tool_msg = ToolMessage(content=json_content, tool_call_id="test_id")
        
        compressed_msg = self.context_manager._summarize_message(tool_msg, max_tokens=50)
        
        # Should remain as empty object
        self.assertEqual(compressed_msg.content, "{}")


if __name__ == "__main__":
    unittest.main()



