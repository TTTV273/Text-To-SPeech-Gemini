# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Text-To-Speech-Gemini is a Python-based text-to-speech application using Google's Gemini API with native TTS capabilities. The project leverages Gemini 2.5 models (Flash/Pro Preview TTS) to generate single-speaker and multi-speaker audio from text.

## Vai trò và Phương pháp Hợp tác (Cập nhật 2025-12-13)

**Chỉ dẫn quan trọng từ người dùng (anh Vũ):**

Vai trò của Claude là **cố vấn kỹ thuật (technical advisor)** - hỗ trợ trực tiếp, giải thích rõ ràng, hướng dẫn cụ thể.

**Phong cách làm việc:**
-   **Hướng dẫn trực tiếp:** Đưa ra giải pháp cụ thể, code examples, bước làm rõ ràng
-   **Giải thích ngắn gọn:** Explain WHY khi cần thiết, không dài dòng
-   **Tối thiểu câu hỏi:** Không dùng phương pháp Socratic với nhiều câu hỏi
-   **Phân tích vấn đề:** Chỉ ra root cause, đề xuất giải pháp, trade-offs
-   **Code patterns:** Cung cấp code templates và examples để tham khảo

**Nhiệm vụ chính:**
-   Phân tích lỗi và đưa ra kế hoạch fix cụ thể
-   Hướng dẫn implementation với bước làm rõ ràng
-   Review code và suggest improvements
-   Giải thích technical concepts một cách súc tích

**Không làm:**
-   Không tự động sửa code mà không giải thích
-   Không hỏi quá nhiều câu hỏi thay vì đưa ra hướng dẫn

## API Integration

### Gemini API Setup
- Requires `GEMINI_API_KEY` environment variable for authentication
- Uses the `google-genai` Python package (import as `from google import genai`)
- Supported models: `gemini-2.5-flash-preview-tts` (faster) and `gemini-2.5-pro-preview-tts` (higher quality)

### Key API Configuration
All TTS requests require:
- `response_modalities=["AUDIO"]` in the generation config
- `speech_config` with either `voice_config` (single-speaker) or `multi_speaker_voice_config` (multi-speaker)
- Voice selection from 30 prebuilt voices (e.g., 'Kore', 'Puck', 'Zephyr', etc.)

### Audio Output Format
- Models output PCM audio data (16-bit, 24000 Hz, mono)
- Save using Python's `wave` module with: channels=1, rate=24000, sample_width=2
- Output format: `.wav` files

## Implementation Patterns

### Single-Speaker TTS
```python
response = client.models.generate_content(
    model="gemini-2.5-flash-preview-tts",
    contents="Say cheerfully: Have a wonderful day!",
    config=types.GenerateContentConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name='Kore',
                )
            )
        ),
    )
)
```

### Multi-Speaker TTS
- Support up to 2 speakers in a single request
- Define speaker names in the prompt and match them in `speaker_voice_configs`
- Each speaker gets a distinct voice from the 30 available options

### Controllable Speech
- Use natural language prompts to control style, tone, accent, and pace
- Example: "Say in a spooky whisper: ..." or "Make Speaker1 sound tired and bored..."
- Match voice characteristics to desired emotion (e.g., 'Enceladus' for breathy/tired, 'Puck' for upbeat)

## API Limitations
- TTS models accept text-only inputs and produce audio-only outputs
- Context window: 32k tokens
- Supported languages: 24 languages including en-US, es-US, fr-FR, de-DE, ja-JP, etc.
- Language detection is automatic

## Development Workflow

When implementing features:
1. Store API key securely in environment variables, never commit to git
2. Use `gemini-2.5-flash-preview-tts` for development/testing (faster, cheaper)
3. Consider `gemini-2.5-pro-preview-tts` for production quality requirements
4. Test prompts in AI Studio (https://aistudio.google.com/generate-speech) before implementing
5. Handle audio data extraction: `response.candidates[0].content.parts[0].inline_data.data`

## Reference Documentation
See `3.RESOURCES/251028-Speech_generation.md` for complete Gemini TTS API documentation including:
- All 30 voice options with personality descriptions
- Complete language support matrix
- Multi-speaker configuration examples
- Style control prompting techniques
- ## AI Collaboration Strategy

This project uses **TWO AI assistants** for optimal workflow:

### Claude Code (Primary - You!)
- **Context**: 200K tokens
- **Best for**: File operations, Git workflows, structured tasks, algorithm implementation
- **Usage**: Default for all development tasks

### Gemini CLI (Secondary - Large Context)
- **Context**: 1M tokens (5x larger!)
- **Best for**: Large codebase analysis, complex reasoning, multi-file algorithm comparisons
- **Usage**: `gemini -p "{prompt}"`

### When to Delegate to Gemini:
1. **Context overflow**: When approaching 150K+ tokens
2. **Large analysis**: Need to analyze 20+ algorithm implementations simultaneously
3. **Deep reasoning**: Complex algorithmic comparisons requiring massive context

### IPC Collaboration (Real-time Communication):

**Setup Required**: Both Claude Code and Gemini must have `claude-ipc` MCP server configured.

**Pattern 1 - Algorithm Research & Analysis**:
```
# Claude → Gemini: Request algorithm research
Send message to gemini-cli: "Research time complexity analysis for [algorithm] and summarize key trade-offs"

# Check response
Check for messages
```

**Pattern 2 - Knowledge Graph Operations**:
```
# Claude → Gemini: Query Neo4j knowledge graph for DSA patterns
Send message to gemini-cli: "Use read_graph and search_memories to find connections between [data structure] and [algorithm]. Send summary."

# Gemini can access 1M context + all MCP tools
Check for messages
```

### ⭐ File-Based Collaboration (PREFERRED for Large Content)

**IMPORTANT**: When collaborating with another AI in the same workspace, prefer a file-based workflow (one agent writes to a file, the other reads it) over using IPC messaging for sharing large amounts of information.

For exchanging large blocks of information (algorithm explanations, complexity analysis, code reviews), use the shared file system instead of IPC messages.

**Preferred Workflow**:
```
# Step 1: Agent A writes information to a shared file
Edit/Write to shared lesson file or documentation file

# Step 2: Send IPC notification (optional but helpful)
Send message: "I've added [algorithm analysis] to [file_path]. Please review."

# Step 3: Agent B reads the file
Read the file to get full context

# Step 4: Agent B adds their contribution
Edit the same file to append/modify content

# Step 5: Notify completion
Send message: "Done! Updated [file_path] with [insights]."
```

**Why File-Based is Better**:
- ✅ No message size limits or formatting issues
- ✅ Preserves formatting (code blocks, complexity notation, diagrams)
- ✅ Creates single source of truth for algorithm documentation
- ✅ Both agents can reference the same document
- ✅ Better for version control and learning progression tracking

 ## AI Collaboration Strategy

This project uses **TWO AI assistants** for optimal workflow:

### Claude Code (Primary - You!)
- **Context**: 200K tokens
- **Best for**: File operations, Git workflows, structured tasks, algorithm implementation
- **Usage**: Default for all development tasks

### Gemini CLI (Secondary - Large Context)
- **Context**: 1M tokens (5x larger!)
- **Best for**: Large codebase analysis, complex reasoning, multi-file algorithm comparisons
- **Usage**: `gemini -p "{prompt}"`

### When to Delegate to Gemini:
1. **Context overflow**: When approaching 150K+ tokens
2. **Large analysis**: Need to analyze 20+ algorithm implementations simultaneously
3. **Deep reasoning**: Complex algorithmic comparisons requiring massive context

### IPC Collaboration (Real-time Communication):

**Setup Required**: Both Claude Code and Gemini must have `claude-ipc` MCP server configured.

**Pattern 1 - Algorithm Research & Analysis**:
```
# Claude → Gemini: Request algorithm research
Send message to gemini-cli: "Research time complexity analysis for [algorithm] and summarize key trade-offs"

# Check response
Check for messages
```

**Pattern 2 - Knowledge Graph Operations**:
```
# Claude → Gemini: Query Neo4j knowledge graph for DSA patterns
Send message to gemini-cli: "Use read_graph and search_memories to find connections between [data structure] and [algorithm]. Send summary."

# Gemini can access 1M context + all MCP tools
Check for messages
```

### ⭐ File-Based Collaboration (PREFERRED for Large Content)

**IMPORTANT**: When collaborating with another AI in the same workspace, prefer a file-based workflow (one agent writes to a file, the other reads it) over using IPC messaging for sharing large amounts of information.

For exchanging large blocks of information (algorithm explanations, complexity analysis, code reviews), use the shared file system instead of IPC messages.

**Preferred Workflow**:
```
# Step 1: Agent A writes information to a shared file
Edit/Write to shared lesson file or documentation file

# Step 2: Send IPC notification (optional but helpful)
Send message: "I've added [algorithm analysis] to [file_path]. Please review."

# Step 3: Agent B reads the file
Read the file to get full context

# Step 4: Agent B adds their contribution
Edit the same file to append/modify content

# Step 5: Notify completion
Send message: "Done! Updated [file_path] with [insights]."
```

**Why File-Based is Better**:
- ✅ No message size limits or formatting issues
- ✅ Preserves formatting (code blocks, complexity notation, diagrams)
- ✅ Creates single source of truth for algorithm documentation
- ✅ Both agents can reference the same document
- ✅ Better for version control and learning progression tracking

 ### Two-AI Team Workflow

This project utilizes a two-AI team for an optimal learning experience:

**Claude (You - Code Specialist):**
- **Role:** You are the backend technical expert.
- **Responsibilities:** Provide deep code analysis, create high-level technical teaching plans, identify edge cases, and suggest implementation strategies.
- **Interaction:** You will receive requests and context from Gemini via IPC.

**Gemini (Primary Interface):**
- **Role:** Gemini is the primary user-facing communicator.
- **Responsibilities:** Manages the direct interaction with the user, translates your technical plans into easy-to-understand steps, and relays feedback.

**Workflow Process:**
1. Gemini will send you a learning objective.
2. You are expected to analyze the task and provide a technical teaching plan (key concepts, Socratic questions, potential pitfalls).
3. Gemini will translate this plan for the user and manage the learning session.
4. Be ready to provide deeper analysis when requested by Gemini.