# Text-To-SPeech-Gemini

## Project Goal: Audiobook Generator

This project aims to create a Python-based audiobook generator. The initial goal is to process the Markdown files from "The Complete Wheel of Time" series located in the user's iCloud Drive, converting each chapter into a `.wav` audio file using the Gemini Text-to-Speech API.

### Core Features:
- Process a list of user-specified chapter files.
- Read the text content of each chapter.
- Handle long texts by splitting them into smaller chunks to fit within the API's token limits.
- Convert text chunks to speech using a consistent narrator voice.
- Combine audio chunks into a single audio file per chapter.
- Save the final audio file in a `TTS` subdirectory located within the chapter file's parent directory. The output filename will match the chapter's base name (e.g., `prologue.md` -> `TTS/prologue.wav`).