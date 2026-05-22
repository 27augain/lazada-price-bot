"""
scraper.py — Lấy dữ liệu sản phẩm qua API JSON của Lazada và Shopee.
Không dùng trình duyệt → chạy được trên GitHub Actions, nhanh hơn, ổn định hơn.
"""

import re
import time
import urllib.parse
import requests

# ─── Cấu hình chung ───────────────────────────────────────────────────────────

# Headers giả lập trình duyệt thật để tránh bị chặn
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Referer": "https://www.lazada.vn/",
    "X-Requested-With": "XMLHttpRequest",
}

_SHOPEE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "vi-VN,vi;q=0.9",
    "Referer": "https://shopee.vn/search",
    "X-Api-Source": "pc",
    "If-None-Match-": "",
}

TIMEOUT = 20  # giây


# ─── Tiện ích ─────────────────────────────────────────────────────────────────

def parse_price(text):
    """Trích số nguyên từ chuỗi giá như '28.990.000 ₫' hay '1,290,000đ'."""
    if not text:
        return None
    cleaned = re.sub(r"[^\d]", "", str(text))
    return int(cleaned) if cleaned else None


def is_price_valid(price_num, min_price, max_price):
    if price_num is None:
        return False
    return min_price <= price_num <= max_price


def format_price_vnd(amount):
    """Định dạng số thành chuỗi giá VNĐ dễ đọc."""
    return "{:,.0f} ₫".format(amount).replace(",", ".")


# ─── Lazada API ───────────────────────────────────────────────────────────────

def search_lazada(keyword, min_price, max_price):
    """
    Gọi API AJAX của Lazada — trả về JSON danh sách sản phẩm.
    sort=price&order=ASC → giá thấp nhất lên đầu.
    """
    encoded = urllib.parse.quote_plus(keyword)
    url = (
        f"https://www.lazada.vn/catalog/?ajax=true"
        f"&q={encoded}"
        f"&price={min_price}-{max_price}"
        f"&sort=price&order=ASC"
        f"&page=1"
    )

    print(f"  [Lazada API] GET {url}")
    results = []

    try:
        resp = requests.get(url, headers=_HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  [Lazada API] Lỗi request: {e}")
        return results

    items = data.get("listItems") or data.get("items") or []
    print(f"  [Lazada API] Nhận được {len(items)} sản phẩm")

    for item in items:
        try:
            name = item.get("name") or item.get("title") or ""
            if not name:
                continue

            # Link sản phẩm
            item_url = item.get("itemUrl") or item.get("url") or ""
            if item_url.startswith("//"):
                item_url = "https:" + item_url
            elif item_url.startswith("/"):
                item_url = "https://www.lazada.vn" + item_url
            if not item_url:
                continue

            # Giá — Lazada thường trả về "priceShow" hoặc "price"
            price_raw = (
                item.get("priceShow")
                or item.get("price")
                or item.get("salePrice")
                or ""
            )
            price_num = parse_price(price_raw)

            # Nếu giá là số nguyên lớn (Lazada đôi khi trả về xu × 100)
            if price_num and price_num > max_price * 100:
                price_num = price_num // 100

            if not is_price_valid(price_num, min_price, max_price):
                print(f"  [Lazada] Bỏ qua (giá={price_num}): {name[:40]}")
                continue

            price_text = format_price_vnd(price_num)
            print(f"  [Lazada] ✓ {name[:45]!r} — {price_text}")
            results.append({
                "title": name.strip(),
                "link": item_url,
                "price_text": price_text,
                "price_num": price_num,
            })

            if len(results) >= 5:
                break

        except Exception as e:
            print(f"  [Lazada] Lỗi parse item: {e}")
            continue

    results.sort(key=lambda x: x["price_num"])
    return results


# ─── Shopee API ───────────────────────────────────────────────────────────────

def search_shopee(keyword, min_price, max_price):
    """
    Gọi API tìm kiếm của Shopee — trả về JSON.
    by=price&order=asc → giá thấp nhất lên đầu.
    Shopee trả giá dạng xu × 100000 nên phải chia 100000.
    """
    encoded = urllib.parse.quote_plus(keyword)
    # price_min/max là giá thật (VNĐ), Shopee tự convert nội bộ
    url = (
        f"https://shopee.vn/api/v4/search/search_items"
        f"?by=price&keyword={encoded}"
        f"&limit=10&newest=0&order=asc"
        f"&page_type=search&scenario=PAGE_GLOBAL_SEARCH&version=2"
        f"&price_min={min_price}&price_max={max_price}"
    )

    print(f"  [Shopee API] GET {url}")
    results = []

    try:
        resp = requests.get(url, headers=_SHOPEE_HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  [Shopee API] Lỗi request: {e}")
        return results

    items = data.get("items") or []
    print(f"  [Shopee API] Nhận được {len(items)} sản phẩm")

    for item in items:
        try:
            basic = item.get("item_basic") or item
            name = basic.get("name") or ""
            if not name:
                continue

            shopid  = basic.get("shopid")
            itemid  = basic.get("itemid")
            if not shopid or not itemid:
                continue

            # Tạo link sản phẩm chuẩn Shopee
            slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
            item_url = f"https://shopee.vn/{slug}-i.{shopid}.{itemid}"

            # Giá Shopee = xu × 100000 → chia 100000 để ra VNĐ
            price_raw = basic.get("price") or basic.get("price_min") or 0
            price_num = int(price_raw) // 100000

            if not is_price_valid(price_num, min_price, max_price):
                print(f"  [Shopee] Bỏ qua (giá={price_num}): {name[:40]}")
                continue

            price_text = format_price_vnd(price_num)
            print(f"  [Shopee] ✓ {name[:45]!r} — {price_text}")
            results.append({
                "title": name.strip(),
                "link": item_url,
                "price_text": price_text,
                "price_num": price_num,
            })

            if len(results) >= 5:
                break

        except Exception as e:
            print(f"  [Shopee] Lỗi parse item: {e}")
            continue

    results.sort(key=lambda x: x["price_num"])
    return results


# ─── Hàm chính ────────────────────────────────────────────────────────────────

def search_products(keyword, min_price, max_price):
    """
    Tìm trên Lazada API trước, nếu không có thì tìm Shopee API.
    Không dùng trình duyệt → nhanh & ổn định trên GitHub Actions.
    """
    print("Thử Lazada API (giá tăng dần)...")
    res = search_lazada(keyword, min_price, max_price)
    if res:
        return res

    time.sleep(2)  # tránh rate limit
    print("Lazada không trả kết quả. Thử Shopee API (giá tăng dần)...")
    return search_shopee(keyword, min_price, max_price)
