#!/bin/bash

# Cấu hình chung
VOICE="Kore"
WORKERS=7

# Kích hoạt môi trường ảo
source .venv/bin/activate

echo "-------------------------------------------------------"
echo "🎙️  Voice: $VOICE | Workers: $WORKERS"
echo "-------------------------------------------------------"

# Hàm xử lý một file cụ thể
process_file() {
    local file="$1"
    
    # Kiểm tra file tồn tại (đề phòng trường hợp lỗi)
    if [ ! -f "$file" ]; then
        echo "⚠️  Bỏ qua: '$file' không phải là file hợp lệ."
        return
    fi

    echo "📖 Đang xử lý: $file"
    .venv/bin/python -m src.audiobook_generator "$file" \
        --voice "$VOICE" \
        --concurrent \
        --workers "$WORKERS" \
        --resume
    
    if [ $? -eq 0 ]; then
        echo "✅ Hoàn thành: $file"
    else
        echo "❌ Lỗi khi xử lý: $file"
    fi
    echo "-------------------------------------------------------"
}

# Hàm xử lý thư mục
process_dir() {
    local dir="$1"
    echo "📂 Mode: Thư mục (Batch processing)"
    echo "Looking for .md files in $dir..."
    echo "-------------------------------------------------------"
    
    # Tìm file .md trong thư mục (xử lý cả file có khoảng trắng)
    find "$dir" -maxdepth 1 -name "*.md" | sort | while read -r file; do
        process_file "$file"
    done
}

# --- LOGIC CHÍNH ---

# Kiểm tra nếu không có tham số nào
if [ $# -eq 0 ]; then
    # Mặc định chạy thư mục cấu hình sẵn nếu không truyền tham số
    DEFAULT_DIR="2.DATA/BOOK-2_Learn-Python"
    process_dir "$DEFAULT_DIR"
    exit 0
fi

# Duyệt qua từng tham số người dùng truyền vào
for TARGET in "$@"; do
    if [ -f "$TARGET" ]; then
        # Nếu là file
        echo "🎯 Mode: File đơn lẻ"
        process_file "$TARGET"
    elif [ -d "$TARGET" ]; then
        # Nếu là thư mục
        process_dir "$TARGET"
    else
        # Thử "cứu" bằng cách globbing (nếu người dùng lỡ để wildcard trong ngoặc kép)
        # Lưu ý: Cách này chỉ hỗ trợ đơn giản, tốt nhất người dùng nên truyền đúng cách
        echo "⚠️  Cảnh báo: '$TARGET' không tìm thấy trực tiếp. Đang thử tìm kiếm mở rộng..."
        
        # Tìm các file khớp với pattern (dùng Python glob để xử lý chính xác khoảng trắng và wildcard)
        MATCHED_FILES=$(python -c "import glob, sys; print('\n'.join(glob.glob(sys.argv[1])))" "$TARGET")
        
        if [ -n "$MATCHED_FILES" ]; then
             # Lưu IFS cũ để xử lý tên file có khoảng trắng khi lặp
             SAVEIFS=$IFS
             IFS=$'\n'
             for f in $MATCHED_FILES; do
                 process_file "$f"
             done
             IFS=$SAVEIFS
        else
             echo "❌ Lỗi: Không tìm thấy file nào khớp với mẫu: $TARGET"
        fi
    fi
done

echo "🎉 Quy trình kết thúc!"
