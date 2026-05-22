import os
import time
from config import get_tracking_data
from scraper import search_products
from telegram_alert import send_telegram_message

def is_ci():
    """Kiểm tra có đang chạy trên GitHub Actions / môi trường CI không."""
    return os.environ.get("CI") == "true" or os.environ.get("GITHUB_ACTIONS") == "true"

def setup_env():
    """
    - Trên GitHub Actions: biến môi trường đã được inject từ Secrets → bỏ qua.
    - Chạy local: nếu chưa có .env thì hỏi người dùng nhập vào.
    """
    from dotenv import load_dotenv

    if is_ci():
        # Môi trường CI — secrets đã được GitHub Actions inject sẵn
        print("Đang chạy trên GitHub Actions, dùng Secrets đã cấu hình.")
        return

    # Chạy local
    if not os.path.exists(".env"):
        print("=== CÀI ĐẶT LẦN ĐẦU (chỉ cần nhập 1 lần) ===")
        sheet_url = input("1. Nhập link Google Sheets CSV: ").strip()
        bot_token = input("2. Nhập TELEGRAM_BOT_TOKEN: ").strip()
        chat_id   = input("3. Nhập TELEGRAM_CHAT_ID: ").strip()

        with open(".env", "w", encoding="utf-8") as f:
            f.write(f"GOOGLE_SHEET_CSV_URL={sheet_url}\n")
            f.write(f"TELEGRAM_BOT_TOKEN={bot_token}\n")
            f.write(f"TELEGRAM_CHAT_ID={chat_id}\n")
        print("Đã lưu cấu hình vào .env!\n")

    load_dotenv()

def format_price(price):
    return "{:,.0f} ₫".format(price).replace(',', '.')

def main():
    setup_env()
    print("Bắt đầu quét giá...")
    items = get_tracking_data()
    
    if not items:
        print("Không có dữ liệu hoặc lỗi cấu hình (chưa set Google Sheet URL).")
        return
        
    for item in items:
        keyword = item['keyword']
        min_price = item['min_price']
        max_price = item['max_price']
        
        print(f"Đang tìm kiếm: {keyword} (Từ {format_price(min_price)} đến {format_price(max_price)})")
        
        results = search_products(keyword, min_price, max_price)
        
        if not results:
            print(f"Không tìm thấy sản phẩm nào phù hợp cho: {keyword}")
            continue
            
        print(f"Tìm thấy {len(results)} sản phẩm phù hợp. Gửi thông báo Telegram...")
        
        # Tạo tin nhắn
        message = (
            f"🚨 <b>KẾT QUẢ SĂN SALE</b> 🚨\n\n"
            f"🔍 <b>Từ khóa:</b> {keyword}\n"
            f"🎯 <b>Giá mục tiêu:</b> Dưới {format_price(max_price)}\n"
            f"🛡 <b>Giá sàn (để lọc fake):</b> {format_price(min_price)}\n\n"
            f"<b>Các shop đang bán với mức giá này:</b>\n"
        )
        
        rank_emojis = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
        for i, res in enumerate(results):
            title = res['title']
            if len(title) > 60:
                title = title[:57] + "..."
            rank = rank_emojis[i] if i < len(rank_emojis) else f"{i+1}."
            message += f"{rank} <a href='{res['link']}'>{title}</a>\n"
            message += f"   💵 Giá: <b>{res['price_text']}</b>\n\n"
            
        message += f"<i>⬆️ Đã sắp xếp từ rẻ đến đắt. Click để xem chi tiết!</i>"
        
        send_telegram_message(message)
            
        # Tạm dừng một chút giữa các lần request để tránh bị block
        time.sleep(5)
        
    print("Hoàn tất quét giá.")
    if not is_ci():
        input("\nNhấn Enter để thoát...")

if __name__ == "__main__":
    main()
