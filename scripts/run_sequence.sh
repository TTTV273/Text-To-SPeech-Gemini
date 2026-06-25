#!/bin/bash

# Kiểm tra tham số đầu vào
if [ -z "$1" ] || [ -z "$2" ]; then
    echo "Cách dùng: $0 <số_bắt_đầu> <số_kết_thúc>"
    echo "Ví dụ: $0 1 9   (Sẽ chạy B01, B02 ... B09)"
    echo "Ví dụ: $0 9 12  (Sẽ chạy B09, B10, B11, B12)"
    exit 1
fi

START=$1
END=$2

# Cấu hình đường dẫn gốc (Anh có thể sửa ở đây nếu thay đổi vị trí lưu truyện)
BASE_PATH="/mnt/hdd1tb/Book/Wheel_Of_Time"

echo "🚀 Bắt đầu chạy batch từ B$(printf "%02d" $START) đến B$(printf "%02d" $END)..."

for ((i=START; i<=END; i++)); do
    # QUAN TRỌNG: Dòng này biến đổi 1 -> 01, 10 -> 10
    BOOK_ID=$(printf "%02d" $i)
    
    SRC_DIR="$BASE_PATH/B${BOOK_ID}/Translated"
    DEST_DIR="$BASE_PATH/B${BOOK_ID}/TTS"

    echo ""
    echo "======================================================="
    echo "📘 ĐANG XỬ LÝ QUYỂN: B${BOOK_ID}"
    echo "   Nguồn: $SRC_DIR"
    echo "   Đích : $DEST_DIR"
    echo "======================================================="

    if [ -d "$SRC_DIR" ]; then
        # Gọi script TTS_Folder.sh để quét và xử lý file bên trong
        ./scripts/TTS_Folder.sh "$SRC_DIR" "$DEST_DIR"
    else
        echo "⚠️  Bỏ qua: Không tìm thấy thư mục $SRC_DIR"
    fi
done

echo ""
echo "🎉 Hoàn tất toàn bộ chuỗi!"
