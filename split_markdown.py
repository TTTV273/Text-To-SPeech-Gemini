import argparse
import sys
from pathlib import Path
from text_chunker import split_into_chunks, count_tokens

def split_file(file_path: str, max_tokens: int = 500):
    """
    Split a markdown file into smaller chunk files.
    """
    input_path = Path(file_path)
    
    if not input_path.exists():
        print(f"❌ Error: File not found: {file_path}")
        return

    # 1. Read Content
    print(f"📖 Reading: {input_path.name}")
    with open(input_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 2. Split Content using existing logic
    # Note: text_chunker handles paragraph/sentence/word hierarchy automatically
    chunks = split_into_chunks(content, max_tokens=max_tokens)
    print(f"✂️  Split into {len(chunks)} chunks (Limit: {max_tokens} tokens/chunk)")

    # 3. Create Output Directory (Chunks folder inside the source directory)
    output_dir = input_path.parent / "Chunks"
    output_dir.mkdir(exist_ok=True)
    print(f"fp  Output folder: {output_dir}")

    # 4. Save individual files
    base_name = input_path.stem
    total_saved = 0
    
    for i, chunk_text in enumerate(chunks, 1):
        # Format: filename_part_001.md
        chunk_filename = f"{base_name}_part_{i:03d}.md"
        chunk_path = output_dir / chunk_filename
        
        token_count = count_tokens(chunk_text)
        
        with open(chunk_path, "w", encoding="utf-8") as f:
            f.write(chunk_text)
            
        print(f"   ✅ Saved: {chunk_filename} ({token_count} tokens)")
        total_saved += 1

    print(f"\n🎉 Done! Created {total_saved} files in '{output_dir}'")

def main():
    parser = argparse.ArgumentParser(description="Split Markdown file into smaller parts by token count.")
    parser.add_argument("file", help="Path to the markdown file")
    parser.add_argument("--tokens", type=int, default=500, help="Max tokens per chunk (default: 500)")
    
    args = parser.parse_args()
    
    split_file(args.file, args.tokens)

if __name__ == "__main__":
    main()
