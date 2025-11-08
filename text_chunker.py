"""
Text Chunking Module for Gemini TTS

This module provides intelligent text chunking with 3-level hierarchy:
- Level 1: Paragraphs (preserve document structure)
- Level 2: Sentences (preserve semantic meaning)
- Level 3: Words (guarantee token limit)

Features:
- Hybrid splitting approach for optimal audio quality
- Token-aware chunking (uses tiktoken)
- Handles edge cases (large paragraphs, long sentences)
- Logging support for debugging
- Comprehensive unit tests

Author: TTTV273
Created: 2025-11-08 (Phase 9: Text Chunker Refactor)
"""

import re
import logging
from typing import List

# Import tiktoken for token counting
try:
    import tiktoken
except ImportError:
    raise ImportError(
        "tiktoken is required for token counting. Install with: pip install tiktoken"
    )

# Setup logging
logger = logging.getLogger(__name__)


# ============================================================
# Token Counting
# ============================================================


def count_tokens(text: str) -> int:
    """
    Count tokens using tiktoken (cl100k_base encoding)

    Args:
        text: Input text

    Returns:
        int: Number of tokens
    """
    try:
        encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text))
    except Exception as e:
        logger.warning(f"Token counting failed: {e}, using word count estimation")
        # Fallback: estimate 1 word ≈ 1.3 tokens
        return int(len(text.split()) * 1.3)


# ============================================================
# Level 3: Word-level Splitting (Fallback)
# ============================================================


def split_by_words(text: str, max_tokens: int) -> List[str]:
    """
    Split text by words to guarantee chunks ≤ max_tokens.

    This is the fallback when sentences are too long.
    Splits on whitespace and joins words until max_tokens is reached.

    Args:
        text: Input text (typically a very long sentence)
        max_tokens: Maximum tokens per chunk

    Returns:
        List of word-level chunks, each ≤ max_tokens
    """
    words = text.split()
    chunks = []
    current_chunk = []
    current_tokens = 0

    for word in words:
        # Calculate tokens with space
        word_with_space = word + " "
        word_tokens = count_tokens(word_with_space)

        if current_tokens + word_tokens > max_tokens:
            # Finalize current chunk
            if current_chunk:
                chunks.append(" ".join(current_chunk))
                logger.debug(
                    f"Word-level chunk: {current_tokens} tokens, {len(current_chunk)} words"
                )

            # Start new chunk
            current_chunk = [word]
            current_tokens = word_tokens
        else:
            current_chunk.append(word)
            current_tokens += word_tokens

    # Add final chunk
    if current_chunk:
        chunks.append(" ".join(current_chunk))
        logger.debug(
            f"Word-level chunk (final): {current_tokens} tokens, {len(current_chunk)} words"
        )

    logger.info(f"Split by words: {len(chunks)} chunks from {len(words)} words")
    return chunks


# ============================================================
# Level 2: Sentence-level Splitting
# ============================================================


def split_large_paragraph(para: str, max_tokens: int) -> List[str]:
    """
    Split a large paragraph into sentence-level chunks.

    Uses regex to detect sentence boundaries (. ! ? …) while
    preserving natural speech flow. Falls back to word-level
    splitting if individual sentences exceed max_tokens.

    Regex pattern: (?<=[.!?…])\\s+
    - Positive lookbehind: must have punctuation before
    - \\s+: one or more whitespace characters

    Args:
        para: Input paragraph (> max_tokens)
        max_tokens: Maximum tokens per chunk

    Returns:
        List of sentence-level chunks, each ≤ max_tokens
    """
    # Split by sentence boundaries
    # Supports: . ! ? … (Vietnamese and English)
    sentences = re.split(r"(?<=[.!?…])\s+", para)

    chunks = []
    current_chunk = []
    current_tokens = 0

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        sentence_tokens = count_tokens(sentence)

        # Edge case: Single sentence > max_tokens
        if sentence_tokens > max_tokens:
            logger.warning(
                f"Sentence exceeds max_tokens ({sentence_tokens} > {max_tokens}), "
                f"falling back to word-level split"
            )

            # Finalize current chunk first
            if current_chunk:
                chunks.append(" ".join(current_chunk))
                logger.debug(
                    f"Sentence-level chunk: {current_tokens} tokens, "
                    f"{len(current_chunk)} sentences"
                )
                current_chunk = []
                current_tokens = 0

            # Split this sentence by words
            word_chunks = split_by_words(sentence, max_tokens)
            chunks.extend(word_chunks)
            continue

        # Normal case: sentence fits
        if current_tokens + sentence_tokens > max_tokens:
            # Finalize current chunk
            if current_chunk:
                chunks.append(" ".join(current_chunk))
                logger.debug(
                    f"Sentence-level chunk: {current_tokens} tokens, "
                    f"{len(current_chunk)} sentences"
                )

            # Start new chunk
            current_chunk = [sentence]
            current_tokens = sentence_tokens
        else:
            current_chunk.append(sentence)
            current_tokens += sentence_tokens

    # Add final chunk
    if current_chunk:
        chunks.append(" ".join(current_chunk))
        logger.debug(
            f"Sentence-level chunk (final): {current_tokens} tokens, "
            f"{len(current_chunk)} sentences"
        )

    logger.info(
        f"Split large paragraph: {len(chunks)} chunks from {len(sentences)} sentences"
    )
    return chunks


# ============================================================
# Level 1: Main Chunking Function
# ============================================================


def split_into_chunks(text: str, max_tokens: int = 2000) -> List[str]:
    """
    Split text into token-safe chunks with 3-level hierarchy.

    Hierarchy:
    1. Level 1 (Preferred): Split by paragraphs (\\n\\n)
       - Preserves document structure
       - Best for audio flow

    2. Level 2 (Fallback): Split by sentences
       - Used when paragraph > max_tokens
       - Preserves semantic meaning

    3. Level 3 (Last resort): Split by words
       - Used when sentence > max_tokens
       - Guarantees all chunks ≤ max_tokens

    Args:
        text: Input text (markdown, plain text, etc.)
        max_tokens: Maximum tokens per chunk (default: 2000)
                   Gemini TTS supports up to 32K, but 2K is optimal

    Returns:
        List of text chunks, each ≤ max_tokens

    Example:
        >>> text = "Para 1.\\n\\nPara 2 with many sentences..."
        >>> chunks = split_into_chunks(text, max_tokens=2000)
        >>> len(chunks)
        5
    """
    chunks = []
    current_chunk = []
    current_token_count = 0

    # Level 1: Split by paragraphs (double newline)
    paragraphs = text.split("\n\n")

    logger.info(f"Processing {len(paragraphs)} paragraphs")

    for para_idx, para in enumerate(paragraphs):
        para = para.strip()
        if not para:
            continue

        para_tokens = count_tokens(para)
        logger.debug(f"Paragraph {para_idx + 1}: {para_tokens} tokens")

        # Case 1: Paragraph fits in current chunk
        if current_token_count + para_tokens <= max_tokens:
            current_chunk.append(para)
            current_token_count += para_tokens
            logger.debug(
                f"  → Added to current chunk (now {current_token_count} tokens)"
            )

        # Case 2: Paragraph doesn't fit, but is small enough
        elif para_tokens <= max_tokens:
            # Finalize current chunk
            if current_chunk:
                chunk_text = "\n\n".join(current_chunk)
                chunks.append(chunk_text)
                logger.debug(
                    f"  → Finalized chunk: {current_token_count} tokens, "
                    f"{len(current_chunk)} paragraphs"
                )

            # Start new chunk with this paragraph
            current_chunk = [para]
            current_token_count = para_tokens
            logger.debug(f"  → Started new chunk: {para_tokens} tokens")

        # Case 3: Paragraph is too large → split by sentences (Level 2)
        else:
            logger.warning(
                f"  → Paragraph {para_idx + 1} exceeds max_tokens "
                f"({para_tokens} > {max_tokens}), splitting by sentences"
            )

            # Finalize current chunk first
            if current_chunk:
                chunk_text = "\n\n".join(current_chunk)
                chunks.append(chunk_text)
                logger.debug(
                    f"  → Finalized chunk before split: {current_token_count} tokens"
                )
                current_chunk = []
                current_token_count = 0

            # Split large paragraph (Level 2/3)
            para_chunks = split_large_paragraph(para, max_tokens)
            chunks.extend(para_chunks)

    # Add final chunk
    if current_chunk:
        chunk_text = "\n\n".join(current_chunk)
        chunks.append(chunk_text)
        logger.debug(
            f"Final chunk: {current_token_count} tokens, {len(current_chunk)} paragraphs"
        )

    logger.info(
        f"Chunking complete: {len(chunks)} chunks created from {len(paragraphs)} paragraphs"
    )

    # Validation: Check all chunks are within limit
    for i, chunk in enumerate(chunks):
        chunk_tokens = count_tokens(chunk)
        if chunk_tokens > max_tokens:
            logger.error(
                f"⚠️  Chunk {i + 1} exceeds max_tokens: {chunk_tokens} > {max_tokens}"
            )
        else:
            logger.debug(f"Chunk {i + 1}: {chunk_tokens} tokens ✓")

    return chunks


# ============================================================
# Unit Tests
# ============================================================


def run_tests():
    """Run comprehensive unit tests for chunking functions"""
    import sys

    print("\n" + "=" * 60)
    print("🧪 RUNNING UNIT TESTS: Text Chunker")
    print("=" * 60 + "\n")

    # Configure logging for tests
    logging.basicConfig(level=logging.INFO)

    test_passed = 0
    test_failed = 0

    # Test 1: Normal paragraphs
    print("Test 1: Normal paragraphs (5 paras, ~600 tokens each)")
    # Create 5 paragraphs, each ~600 tokens → total ~3000 tokens → 2 chunks
    text1 = "\n\n".join(["Word " * 450 for _ in range(5)])  # ~600 tokens each
    chunks1 = split_into_chunks(text1, max_tokens=2000)
    expected1 = 2  # 5 paras * 600 = 3000 tokens → should split into 2 chunks
    if len(chunks1) >= 2:
        print(f"  ✅ PASS: {len(chunks1)} chunks (expected ≥2)")
        test_passed += 1
    else:
        print(f"  ❌ FAIL: {len(chunks1)} chunks (expected ≥2)")
        test_failed += 1

    # Test 2: Single large paragraph
    print("\nTest 2: Single large paragraph (17,158 tokens)")
    text2 = "Word " * 13000  # ~17,000 tokens
    chunks2 = split_into_chunks(text2, max_tokens=2000)
    expected2_min = 8  # 17000/2000 = 8.5
    if len(chunks2) >= expected2_min:
        print(f"  ✅ PASS: {len(chunks2)} chunks (expected ≥{expected2_min})")
        test_passed += 1
    else:
        print(f"  ❌ FAIL: {len(chunks2)} chunks (expected ≥{expected2_min})")
        test_failed += 1

    # Verify all chunks are within limit
    all_valid = all(count_tokens(c) <= 2000 for c in chunks2)
    if all_valid:
        print(f"  ✅ PASS: All chunks ≤ 2000 tokens")
        test_passed += 1
    else:
        print(f"  ❌ FAIL: Some chunks exceed 2000 tokens")
        test_failed += 1

    # Test 3: Mixed sizes
    print("\nTest 3: Mixed paragraph sizes (500, 5000, 500 tokens)")
    text3_parts = [
        "A " * 250,  # 500 tokens
        "B " * 2500,  # 5000 tokens
        "C " * 250,  # 500 tokens
    ]
    text3 = "\n\n".join(text3_parts)
    chunks3 = split_into_chunks(text3, max_tokens=2000)
    # Expected: Para 1 (chunk 1), Para 2 split (chunks 2-3), Para 3 (chunk 4)
    # Or Para 1 + Para 3 merged with Para 2 chunks
    if len(chunks3) >= 3:
        print(f"  ✅ PASS: {len(chunks3)} chunks (expected ≥3)")
        test_passed += 1
    else:
        print(f"  ❌ FAIL: {len(chunks3)} chunks (expected ≥3)")
        test_failed += 1

    # Test 4: Edge case - no paragraphs (single text block)
    print("\nTest 4: No paragraph breaks (single 3000 token text)")
    # Create ~3000 tokens with sentences (8 words * 400 = ~3200 tokens)
    text4 = "This is a long sentence with many words. " * 400  # ~3000 tokens
    chunks4 = split_into_chunks(text4, max_tokens=2000)
    if len(chunks4) >= 2:
        print(f"  ✅ PASS: {len(chunks4)} chunks (expected ≥2)")
        test_passed += 1
    else:
        print(f"  ❌ FAIL: {len(chunks4)} chunks (expected ≥2)")
        test_failed += 1

    # Test 5: Empty and whitespace handling
    print("\nTest 5: Empty paragraphs and whitespace")
    text5 = "\n\n  \n\nActual content.\n\n  \n\n"
    chunks5 = split_into_chunks(text5, max_tokens=2000)
    if len(chunks5) == 1:
        print(f"  ✅ PASS: {len(chunks5)} chunk (expected 1)")
        test_passed += 1
    else:
        print(f"  ❌ FAIL: {len(chunks5)} chunks (expected 1)")
        test_failed += 1

    # Summary
    print("\n" + "=" * 60)
    print(f"TEST SUMMARY: {test_passed} passed, {test_failed} failed")
    print("=" * 60 + "\n")

    return test_failed == 0


# ============================================================
# Main
# ============================================================

if __name__ == "__main__":
    # Run unit tests when executed directly
    success = run_tests()
    exit(0 if success else 1)
