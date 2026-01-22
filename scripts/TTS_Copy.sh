#!/bin/bash

echo "Đang copy các file MP3..."

destination="/mnt/hdd1tb/Book/Wheel_Of_Time/B5/TTS/"

# Tạo thư mục đích nếu chưa có
mkdir -p "$destination"

for i in {30..41}; do
    # File MP3 được tạo trong thư mục TTS của mỗi chapter
    mp3_file="/mnt/hdd1tb/Book/Wheel_Of_Time/B5/Translated/B5-CH$i/TTS/B5-CH$i.mp3"

    if [ ! -f "$mp3_file" ]; then
        echo "⚠️  Bỏ qua: $mp3_file không tồn tại"
        continue
    fi

    mv "$mp3_file" "$destination"
    echo "✅ Đã copy: B5-CH$i.mp3"
done

echo "Hoàn tất!"

