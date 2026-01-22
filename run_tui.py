import os
import sys

# Thêm thư mục src vào đường dẫn tìm kiếm module
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))

from tui.app import TTSApp

if __name__ == "__main__":
    app = TTSApp()
    app.run()
