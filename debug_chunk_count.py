import sys
import logging
import re
from text_chunker import split_into_chunks, count_tokens

# Configure logging to capture output
logging.basicConfig(level=logging.INFO)

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
    text = re.sub(r"!\[([^\]]*)\]\([^\]]+\)", "", text)
    return text

user_text = """CHƯƠNG

24

Trinh sát và Khám phá

Ánh nắng xuyên qua những cánh cửa chớp chạm trổ, trườn dần trên giường, đánh thức Mat. Trong một thoáng, gã chỉ nằm đó cau mày. Gã đã không nghĩ ra được kế hoạch nào để trốn khỏi Tar Valon trước khi chìm vào giấc ngủ, nhưng gã cũng chưa từ bỏ. Quá nhiều ký ức vẫn còn bị sương mù bao phủ, nhưng gã sẽ không từ bỏ.

Hai người hầu gái tất bật bước vào với nước nóng và một khay thức ăn nặng trĩu, cười nói và bảo gã trông đã khỏe hơn nhiều rồi, và gã sẽ sớm đứng dậy được nếu làm theo lời các Aes Sedai. Gã trả lời họ cộc lốc, cố không tỏ ra cay đắng. Cứ để họ nghĩ mình định thuận theo. Bụng gã réo lên vì mùi thơm từ khay thức ăn.

Khi họ rời đi, gã hất tấm chăn sang một bên và nhảy ra khỏi giường, chỉ dừng lại để nhét nửa lát giăm bông vào miệng trước khi đổ nước ra để rửa mặt và cạo râu. Nhìn vào gương phía trên chậu rửa, gã dừng lại khi đang xoa xà phòng lên mặt. Gã trông khá hơn thật.

Má gã vẫn còn hóp, nhưng không hóp sâu như trước"""

# Clean text
cleaned_text = clean_markdown(user_text)

# Calculate tokens
total_tokens = count_tokens(cleaned_text)
print(f"Total tokens (cleaned): {total_tokens}")

# Split into chunks (default max_tokens=1000)
chunks_1000 = split_into_chunks(cleaned_text, max_tokens=1000)
print(f"Chunks (max_tokens=1000): {len(chunks_1000)}")

for i, chunk in enumerate(chunks_1000):
    print(f"Chunk {i+1} length: {len(chunk)} chars, {count_tokens(chunk)} tokens")