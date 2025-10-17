# src/tools/search_postprocessor.py
import re
import base64
import logging
from typing import List, Dict, Any, Set
from urllib.parse import urlparse
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


class SearchResultPostProcessor:
    """Enhanced search result post-processor with intelligent deduplication and relevance filtering."""

    base64_pattern = r"data:image/[^;]+;base64,[a-zA-Z0-9+/=]+"

    def __init__(
        self, 
        min_score_threshold: float, 
        max_content_length_per_page: int,
        similarity_threshold: float = 0.85,
        enable_content_extraction: bool = True
    ):
        """
        Initialize the post-processor

        Args:
            min_score_threshold: Minimum relevance score threshold
            max_content_length_per_page: Maximum content length
            similarity_threshold: Content similarity threshold for deduplication (0-1)
            enable_content_extraction: Whether to extract key content instead of keeping full text
        """
        self.min_score_threshold = min_score_threshold
        self.max_content_length_per_page = max_content_length_per_page
        self.similarity_threshold = similarity_threshold
        self.enable_content_extraction = enable_content_extraction

    def process_results(self, results: List[Dict]) -> List[Dict]:
        """
        Process search results with enhanced deduplication and optimization

        Args:
            results: Original search result list

        Returns:
            Processed result list
        """
        if not results:
            return []

        cleaned_results = []
        seen_urls = set()
        seen_contents = []  # Store content signatures for similarity check

        for result in results:
            # 1. Remove URL duplicates
            cleaned_result = self._remove_url_duplicates(result, seen_urls)
            if not cleaned_result:
                continue

            # 2. Filter low quality results
            if (
                "page" == cleaned_result.get("type")
                and self.min_score_threshold
                and self.min_score_threshold > 0
                and cleaned_result.get("score", 0) < self.min_score_threshold
            ):
                logger.debug(f"Filtered low score result: {cleaned_result.get('url', 'unknown')}")
                continue

            # 3. Check content similarity for deduplication
            if not self._is_content_unique(cleaned_result, seen_contents):
                logger.info(f"Filtered similar content: {cleaned_result.get('url', 'unknown')}")
                continue

            # 4. Clean base64 images from content
            cleaned_result = self._remove_base64_images(cleaned_result)
            if not cleaned_result:
                continue

            # 5. Extract key information if enabled
            if self.enable_content_extraction and "page" == cleaned_result.get("type"):
                cleaned_result = self._extract_key_content(cleaned_result)

            # 6. Truncate long content
            if (
                self.max_content_length_per_page
                and self.max_content_length_per_page > 0
            ):
                cleaned_result = self._truncate_long_content(cleaned_result)

            if cleaned_result:
                cleaned_results.append(cleaned_result)
                # Store content signature for future similarity checks
                if cleaned_result.get("content"):
                    seen_contents.append(self._get_content_signature(cleaned_result["content"]))

        # 7. Sort by score descending
        sorted_results = sorted(
            cleaned_results, key=lambda x: x.get("score", 0), reverse=True
        )

        logger.info(
            f"Search result post-processing: {len(results)} -> {len(sorted_results)} "
            f"(removed {len(results) - len(sorted_results)} duplicates/low-quality)"
        )
        return sorted_results

    def _remove_url_duplicates(self, result: Dict, seen_urls: Set[str]) -> Dict:
        """Remove duplicate results based on URL."""
        url = result.get("url", result.get("image_url", ""))
        
        if url:
            # Normalize URL (remove trailing slashes, fragments, etc.)
            normalized_url = self._normalize_url(url)
            
            if normalized_url not in seen_urls:
                seen_urls.add(normalized_url)
                return result.copy()
            else:
                return {}
        else:
            # Keep results with empty URLs
            return result.copy()

    def _normalize_url(self, url: str) -> str:
        """Normalize URL for better duplicate detection."""
        # Remove trailing slashes
        url = url.rstrip('/')
        # Remove URL fragments
        if '#' in url:
            url = url.split('#')[0]
        # Remove common tracking parameters
        tracking_params = ['utm_source', 'utm_medium', 'utm_campaign', 'ref', 'source']
        if '?' in url:
            base, params = url.split('?', 1)
            param_pairs = params.split('&')
            filtered_params = [p for p in param_pairs if not any(p.startswith(f"{tp}=") for tp in tracking_params)]
            if filtered_params:
                url = f"{base}?{'&'.join(filtered_params)}"
            else:
                url = base
        return url.lower()

    def _is_content_unique(self, result: Dict, seen_contents: List[str]) -> bool:
        """
        Check if content is unique using similarity comparison.
        
        Args:
            result: Current result to check
            seen_contents: List of content signatures already seen
            
        Returns:
            True if content is unique enough, False otherwise
        """
        if not seen_contents or "content" not in result:
            return True
        
        current_signature = self._get_content_signature(result["content"])
        
        if not current_signature:
            return True
        
        # Compare with existing content signatures
        for seen_sig in seen_contents:
            similarity = self._calculate_similarity(current_signature, seen_sig)
            if similarity > self.similarity_threshold:
                logger.debug(f"Content similarity: {similarity:.2f} (threshold: {self.similarity_threshold})")
                return False
        
        return True

    def _get_content_signature(self, content: str, max_length: int = 500) -> str:
        """
        Get a signature/fingerprint of content for similarity comparison.
        
        Args:
            content: Full content text
            max_length: Maximum length of signature
            
        Returns:
            Content signature (first N chars of cleaned content)
        """
        if not content:
            return ""
        
        # Clean content: remove extra whitespace, lowercase
        cleaned = re.sub(r'\s+', ' ', content.lower().strip())
        
        # Take first max_length characters as signature
        return cleaned[:max_length]

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """
        Calculate similarity ratio between two text strings.
        
        Args:
            text1: First text
            text2: Second text
            
        Returns:
            Similarity ratio (0-1)
        """
        if not text1 or not text2:
            return 0.0
        
        return SequenceMatcher(None, text1, text2).ratio()

    def _extract_key_content(self, result: Dict) -> Dict:
        """
        Extract key information from search result instead of keeping full content.
        This helps reduce token usage while preserving important information.
        
        Args:
            result: Search result with full content
            
        Returns:
            Result with extracted key content
        """
        if "content" not in result or not result["content"]:
            return result
        
        content = result["content"]
        extracted_result = result.copy()
        
        # Extract key information patterns
        key_parts = []
        
        # 1. Extract title/headers (lines starting with #, or all caps, or ending with :)
        lines = content.split('\n')
        headers = []
        for line in lines[:20]:  # Check first 20 lines
            line_stripped = line.strip()
            if (line_stripped.startswith('#') or 
                (len(line_stripped) > 3 and line_stripped.isupper()) or
                (len(line_stripped) < 100 and line_stripped.endswith(':'))):
                headers.append(line_stripped)
        
        if headers:
            key_parts.append("**Key Sections:**\n" + "\n".join(headers[:5]))
        
        # 2. Extract numerical data and dates
        numbers_and_dates = re.findall(
            r'\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b|\b\d+[,.]?\d*\s*(?:million|billion|thousand|percent|%|meters?|feet|km|mi)\b',
            content,
            re.IGNORECASE
        )
        if numbers_and_dates:
            key_parts.append("**Key Data:** " + ", ".join(set(numbers_and_dates[:10])))
        
        # 3. Extract first few sentences as summary
        sentences = re.split(r'[.!?]+', content)
        summary_sentences = [s.strip() for s in sentences[:3] if len(s.strip()) > 20]
        if summary_sentences:
            key_parts.append("**Summary:** " + " ".join(summary_sentences))
        
        # 4. Keep important markers (prices, names, specific terms)
        # This is a simple heuristic - can be improved with NER
        
        # Combine extracted parts
        if key_parts:
            extracted_content = "\n\n".join(key_parts)
            # Add a note that this is extracted content
            extracted_result["content"] = f"[KEY CONTENT EXTRACTED]\n\n{extracted_content}"
            
            # Keep original raw_content if available (but truncated)
            if "raw_content" in extracted_result:
                original_raw = extracted_result["raw_content"]
                if len(original_raw) > 2000:
                    extracted_result["raw_content"] = original_raw[:2000] + "...[truncated]"
            
            logger.debug(f"Extracted key content from {result.get('url', 'unknown')}: "
                        f"{len(content)} -> {len(extracted_content)} chars")
        
        return extracted_result

    def _remove_base64_images(self, result: Dict) -> Dict:
        """Remove base64 encoded images from content"""

        if "page" == result.get("type"):
            cleaned_result = self.processPage(result)
        elif "image" == result.get("type"):
            cleaned_result = self.processImage(result)
        else:
            # For other types, keep as is
            cleaned_result = result.copy()

        return cleaned_result

    def processPage(self, result: Dict) -> Dict:
        """Process page type result"""
        # Clean base64 images from content
        cleaned_result = result.copy()

        if "content" in result:
            original_content = result["content"]
            cleaned_content = re.sub(self.base64_pattern, " ", original_content)
            cleaned_result["content"] = cleaned_content

            # Log if significant content was removed
            if len(cleaned_content) < len(original_content) * 0.8:
                logger.debug(
                    f"Removed base64 images from search content: {result.get('url', 'unknown')}"
                )

        # Clean base64 images from raw content
        if "raw_content" in cleaned_result:
            original_raw_content = cleaned_result["raw_content"]
            cleaned_raw_content = re.sub(self.base64_pattern, " ", original_raw_content)
            cleaned_result["raw_content"] = cleaned_raw_content

            # Log if significant content was removed
            if len(cleaned_raw_content) < len(original_raw_content) * 0.8:
                logger.debug(
                    f"Removed base64 images from search raw content: {result.get('url', 'unknown')}"
                )

        return cleaned_result

    def processImage(self, result: Dict) -> Dict:
        """Process image type result - clean up base64 data and long fields"""
        cleaned_result = result.copy()

        # Remove base64 encoded data from image_url if present
        if "image_url" in cleaned_result and isinstance(
            cleaned_result["image_url"], str
        ):
            # Check if image_url contains base64 data
            if "data:image" in cleaned_result["image_url"]:
                original_image_url = cleaned_result["image_url"]
                cleaned_image_url = re.sub(self.base64_pattern, " ", original_image_url)
                if len(cleaned_image_url) == 0 or not cleaned_image_url.startswith(
                    "http"
                ):
                    logger.debug(
                        f"Removed base64 data from image_url and the cleaned_image_url is empty or not start with http"
                    )
                    return {}
                cleaned_result["image_url"] = cleaned_image_url
                logger.debug(
                    f"Removed base64 data from image_url: {result.get('image_url', 'unknown')}"
                )

        # Truncate very long image descriptions
        if "image_description" in cleaned_result and isinstance(
            cleaned_result["image_description"], str
        ):
            if (
                self.max_content_length_per_page
                and len(cleaned_result["image_description"])
                > self.max_content_length_per_page
            ):
                cleaned_result["image_description"] = (
                    cleaned_result["image_description"][
                        : self.max_content_length_per_page
                    ]
                    + "..."
                )
                logger.info(
                    f"Truncated long image description from search result"
                )

        return cleaned_result

    def _truncate_long_content(self, result: Dict) -> Dict:
        """Truncate long content"""

        truncated_result = result.copy()

        # Truncate content length
        if "content" in truncated_result:
            content = truncated_result["content"]
            if len(content) > self.max_content_length_per_page:
                truncated_result["content"] = (
                    content[: self.max_content_length_per_page] + "..."
                )
                logger.debug(
                    f"Truncated long content from search result: {result.get('url', 'unknown')}"
                )

        # Truncate raw content length (can be slightly longer)
        if "raw_content" in truncated_result:
            raw_content = truncated_result["raw_content"]
            if len(raw_content) > self.max_content_length_per_page * 2:
                truncated_result["raw_content"] = (
                    raw_content[: self.max_content_length_per_page * 2] + "..."
                )
                logger.debug(
                    f"Truncated long raw content from search result"
                )

        return truncated_result
