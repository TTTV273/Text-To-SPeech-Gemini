import sys
import re
from pathlib import Path
from text_chunker import split_into_chunks, count_tokens

# Copied from audiobook_generator.py to ensure identical processing
def clean_markdown(text: str) -> str:
    # clean Headers
    text = re.sub(r"^#+\s+", "", text, flags=re.MULTILINE)

    # clean Bold
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)

    # clean Italic
    text = re.sub(r"\*([^*]+)\*", r"\1", text)

    # clean Link
    text = re.sub(r"!\[([^\]]+)\]\([^\]]+\)", r"\1", text)

    # clean Code Block
    text = re.sub(r"```[^`]*```", "", text, flags=re.DOTALL)

    # clean in line code
    text = re.sub(r"`([^`]+)`", r"\1", text)

    # clean image
    text = re.sub(r"!\{([^\]]*)\}\]\([^\]]+\)", "", text)

    return text

def extract_chunk(file_path, chunk_index):
    # Configuration must match audiobook_generator.py
    MAX_TOKENS_PER_CHUNK = 1000
    
    input_path = Path(file_path)
    if not input_path.exists():
        print(f"❌ Error: File not found: {file_path}")
        return

    print(f"📖 Reading: {input_path.name}")
    with open(input_path, "r", encoding="utf-8") as f:
        text = f.read()
        
    print(f"🧼 Cleaning Markdown...")
    cleaned_text = clean_markdown(text)
    
    print(f"📦 Splitting into chunks (Max {MAX_TOKENS_PER_CHUNK} tokens)...")
    chunks = split_into_chunks(cleaned_text, max_tokens=MAX_TOKENS_PER_CHUNK)
    
    total_chunks = len(chunks)
    print(f"📊 Total chunks found: {total_chunks}")
    
    if chunk_index < 0 or chunk_index >= total_chunks:
        print(f"❌ Error: Chunk index {chunk_index} is invalid. Valid range: 0 to {total_chunks - 1}")
        return

    chunk_content = chunks[chunk_index]
    output_filename = f"chunk_{chunk_index}.md"
    
    # Optional: Save with source filename prefix
    # output_filename = f"{input_path.stem}_chunk_{chunk_index}.md"
    
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(chunk_content)
        
    print(f"\n✅ Successfully saved chunk {chunk_index} to: {output_filename}")
    print(f"   Content length: {len(chunk_content)} chars")
    print(f"   Token count: {count_tokens(chunk_content)}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python extract_chunk.py <file_path> <chunk_index>")
        print("Example: python extract_chunk.py data/book.md 10")
    else:
        extract_chunk(sys.argv[1], int(sys.argv[2]))
