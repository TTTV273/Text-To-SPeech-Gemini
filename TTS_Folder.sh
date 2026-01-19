#!/bin/bash

echo "Đang xử lý các file TTS..."

for i in {34..41}; do
    file_name="/mnt/hdd1tb/Book/Wheel_Of_Time/B5/Translated/B5-CH$i/B5-CH$i.md"

    # Kiểm tra file tồn tại trước khi chạy
    if [ ! -f "$file_name" ]; then
        echo "⚠️  Bỏ qua: $file_name không tồn tại"
        continue
    fi

    echo "📖 Đang xử lý: $file_name"
    ./run_batch.sh "$file_name"
done

echo "Hoàn tất!"

