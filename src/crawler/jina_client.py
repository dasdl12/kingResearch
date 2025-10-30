# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import logging
import os

import requests

logger = logging.getLogger(__name__)


class JinaClient:
    def __init__(self):
        """Initialize Jina client with API key from environment variable."""
        self.api_key = os.getenv("JINA_API_KEY")
        if not self.api_key:
            logger.info(
                "JINA_API_KEY not set. Using free tier with rate limits. "
                "Set JINA_API_KEY environment variable for higher limits. "
                "Get your key at: https://jina.ai/reader"
            )
        else:
            logger.info("Jina API client initialized with API key")
    
    def crawl(self, url: str, return_format: str = "html") -> str:
        """Crawl a URL and return content in specified format.
        
        Args:
            url: The URL to crawl
            return_format: Output format (html, markdown, text, screenshot, pageshot)
            
        Returns:
            str: The crawled content
        """
        headers = {
            "Content-Type": "application/json",
            "X-Return-Format": return_format,
        }
        
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        
        data = {"url": url}
        try:
            response = requests.post("https://r.jina.ai/", headers=headers, json=data, timeout=30)
            response.raise_for_status()
            return response.text
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to crawl URL {url}: {e}")
            raise
