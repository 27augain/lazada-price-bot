import os
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

def get_tracking_data():
    """
    Đọc dữ liệu từ Google Sheets (đã được Publish to web dưới định dạng CSV).
    Cấu trúc bảng cần có các cột:
    - keyword: Từ khóa tìm kiếm (Ví dụ: iPhone 15 Pro Max)
    - min_price: Giá tối thiểu (để lọc phụ kiện, ốp lưng, hàng fake)
    - max_price: Giá mục tiêu (báo cáo nếu có shop bán dưới giá này)
    """
    csv_url = os.environ.get('GOOGLE_SHEET_CSV_URL')
    
    if not csv_url:
        print("LỖI: Chưa có GOOGLE_SHEET_CSV_URL trong file .env!")
        return []
        
    try:
        df = pd.read_csv(csv_url)
        df = df.dropna(subset=['keyword', 'min_price', 'max_price'])
        
        items = []
        for index, row in df.iterrows():
            items.append({
                'keyword': str(row['keyword']).strip(),
                'min_price': int(row['min_price']),
                'max_price': int(row['max_price'])
            })
        return items
    except Exception as e:
        print(f"Lỗi khi đọc file Google Sheets: {e}")
        return []
