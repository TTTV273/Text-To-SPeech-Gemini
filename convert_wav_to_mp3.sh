#!/bin/bash

echo "Đang convert WAV sang MP3..."

# Thư mục chứa file WAV
source_dir="/mnt/hdd1tb/Book/Wheel_Of_Time/B5/TTS/"

# Kiểm tra thư mục tồn tại
if [ ! -d "$source_dir" ]; then
    echo "❌ Thư mục không tồn tại: $source_dir"
    exit 1
fi

# Đếm số file WAV
wav_count=$(find "$source_dir" -maxdepth 1 -name "*.wav" | wc -l)
echo "📁 Tìm thấy $wav_count file WAV trong $source_dir"

if [ "$wav_count" -eq 0 ]; then
    echo "⚠️  Không có file WAV nào để convert"
    exit 0
fi

# Convert từng file
converted=0
for wav_file in "$source_dir"*.wav; do
    # Kiểm tra file tồn tại (tránh lỗi nếu không có file nào match)
    [ -f "$wav_file" ] || continue

    # Tạo tên file MP3
    mp3_file="${wav_file%.wav}.mp3"
    filename=$(basename "$wav_file")

    echo "🔄 Converting: $filename"

    # Convert bằng ffmpeg
    ffmpeg -y -i "$wav_file" -codec:a libmp3lame -b:a 128k -q:a 2 "$mp3_file" 2>/dev/null

    if [ $? -eq 0 ] && [ -f "$mp3_file" ]; then
        # Hiển thị kích thước
        wav_size=$(du -h "$wav_file" | cut -f1)
        mp3_size=$(du -h "$mp3_file" | cut -f1)
        echo "✅ Đã convert: $filename ($wav_size → $mp3_size)"

        # Xóa file WAV gốc
        rm "$wav_file"
        ((converted++))
    else
        echo "❌ Lỗi convert: $filename"
    fi
done

echo ""
echo "🎉 Hoàn tất! Đã convert $converted/$wav_count file"
