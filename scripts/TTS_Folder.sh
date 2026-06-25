#!/bin/bash

echo "Đang xử lý các file TTS..."

destination="/mnt/hdd1tb/Book/Wheel_Of_Time/B6/TTS/"

# Tạo thư mục đích nếu chưa có
mkdir -p "$destination"

for i in {11..15}; do
    file_name="/mnt/hdd1tb/Book/Wheel_Of_Time/B6/Translated/B6-CH$i/B6-CH$i.md"

    # Kiểm tra file tồn tại trước khi chạy
    if [ ! -f "$file_name" ]; then
        echo "⚠️  Bỏ qua: $file_name không tồn tại"
        continue
    fi

    echo "📖 Đang xử lý: $file_name"

    if ! ./scripts/run_batch.sh "$file_name"; then
        echo "❌ Lỗi TTS: $file_name"
        continue
    fi

    mp3_file="/mnt/hdd1tb/Book/Wheel_Of_Time/B6/Translated/B6-CH$i/TTS/B6-CH$i.mp3"

    if [ -f "$mp3_file" ]; then
        mv "$mp3_file" "$destination"
        echo "✅ Đã di chuyển: B6-CH$i.mp3"
    else
        echo "❌ Không tìm thấy: $mp3_file"
    fi
done

echo "Hoàn tất!"
