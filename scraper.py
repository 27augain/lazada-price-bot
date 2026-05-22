"""
scraper.py — Dùng Playwright + Stealth để quét giá trên Lazada/Shopee.
Stealth mode giúp tránh bị phát hiện là bot trên GitHub Actions.
"""

import re
import time
import urllib.parse
from playwright.sync_api import sync_playwright


# ─── Tiện ích ─────────────────────────────────────────────────────────────────

def fix_link(link, base="https://www.lazada.vn"):
    """Chuẩn hóa link về dạng https://."""
    if not link:
        return None
    link = link.strip()
    if link.startswith("http"):
        return link
    if link.startswith("//"):
        return "https:" + link
    if link.startswith("/"):
        return base.rstrip("/") + link
    return None


def parse_price(text):
    """Trích giá trị số từ chuỗi giá."""
    if not text:
        return None
    cleaned = re.sub(r"[^\d]", "", str(text))
    return int(cleaned) if cleaned and int(cleaned) > 1000 else None


def is_price_valid(price_num, min_price, max_price):
    if price_num is None:
        return False
    return min_price <= price_num <= max_price


def format_vnd(amount):
    return "{:,.0f} ₫".format(amount).replace(",", ".")


def is_match(title, keyword):
    """
    Kiểm tra tên sản phẩm có thực sự khớp với từ khóa không.
    Yêu cầu: Tất cả các từ trong keyword đều phải có mặt trong title.
    """
    if not title or not keyword:
        return False
    title_lower = title.lower()
    for word in keyword.lower().split():
        if word not in title_lower:
            return False
    return True


def _launch_browser(playwright):
    """Khởi tạo trình duyệt với cấu hình chống phát hiện bot."""
    browser = playwright.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
        ],
    )
    context = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1366, "height": 768},
        locale="vi-VN",
        timezone_id="Asia/Ho_Chi_Minh",
    )
    return browser, context


def _apply_stealth(page):
    """Inject JS để ẩn dấu hiệu headless/bot."""
    page.add_init_script("""
        // Xóa navigator.webdriver
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        // Fake plugins
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5]
        });
        // Fake languages
        Object.defineProperty(navigator, 'languages', {
            get: () => ['vi-VN', 'vi', 'en-US', 'en']
        });
        // Fake chrome runtime
        window.chrome = { runtime: {} };
    """)


# ─── Lazada ───────────────────────────────────────────────────────────────────

def search_lazada(keyword, min_price, max_price):
    """Tìm kiếm Lazada, sort giá tăng dần."""
    encoded = urllib.parse.quote_plus(keyword)
    url = (
        f"https://www.lazada.vn/catalog/"
        f"?q={encoded}"
        f"&price={min_price}-{max_price}"
        f"&sort=priceasc"
    )

    results = []
    try:
        with sync_playwright() as p:
            browser, context = _launch_browser(p)
            page = context.new_page()
            _apply_stealth(page)

            # Chặn ảnh để tải nhanh
            page.route("**/*.{png,jpg,jpeg,gif,webp,svg}", lambda r: r.abort())

            print(f"  [Lazada] Mở: {url}")
            page.goto(url, timeout=60000, wait_until="networkidle")
            page.wait_for_timeout(3000)

            # Debug: lưu nội dung trang để xem có bị chặn không
            title = page.title()
            print(f"  [Lazada] Tiêu đề trang: {title}")

            # Thử nhiều selector
            card_sels = [
                '[data-qa-locator="product-item"]',
                'div[data-tracking="product-card"]',
                '.Bm3ON',
                'div.qmXQo',
                'div[class*="product"]',
            ]
            found_sel = None
            for sel in card_sels:
                try:
                    page.wait_for_selector(sel, timeout=5000)
                    found_sel = sel
                    break
                except Exception:
                    continue

            if not found_sel:
                # Fallback: tìm tất cả link có chứa /products/
                print("  [Lazada] Không tìm thấy card selector, thử tìm link sản phẩm...")
                links = page.locator('a[href*="/products/"]').all()
                print(f"  [Lazada] Tìm thấy {len(links)} link sản phẩm")

                seen = set()
                for a in links:
                    if len(results) >= 5:
                        break
                    try:
                        href = fix_link(a.get_attribute("href"))
                        if not href or href in seen:
                            continue
                        seen.add(href)

                        title_text = (a.get_attribute("title") or a.inner_text()).strip()
                        if len(title_text) < 5 or not is_match(title_text, keyword):
                            continue

                        # Tìm giá gần link (trong parent)
                        parent = a.locator("xpath=ancestor::div[contains(@class,'card') or contains(@class,'item') or contains(@class,'product')]").first
                        price_text = ""
                        price_num = None
                        if parent.count() > 0:
                            spans = parent.locator("span:has-text('₫'), span[class*='price']").all()
                            for sp in spans:
                                txt = sp.inner_text().strip()
                                num = parse_price(txt)
                                if num and is_price_valid(num, min_price, max_price):
                                    price_num = num
                                    price_text = format_vnd(num)
                                    break

                        if price_num:
                            print(f"  [Lazada] ✓ {title_text[:45]} — {price_text}")
                            results.append({
                                "title": title_text,
                                "link": href,
                                "price_text": price_text,
                                "price_num": price_num,
                            })
                    except Exception:
                        continue

                browser.close()
                results.sort(key=lambda x: x["price_num"])
                return results

            print(f"  [Lazada] Dùng selector: {found_sel}")
            cards = page.locator(found_sel).all()
            print(f"  [Lazada] Số card: {len(cards)}")

            for card in cards:
                if len(results) >= 5:
                    break
                try:
                    # Link + title
                    link = None
                    title_text = None
                    for a in card.locator("a").all():
                        href = fix_link(a.get_attribute("href"))
                        t = (a.get_attribute("title") or "").strip()
                        if not t:
                            t = a.inner_text().strip()
                        if href and len(t) > 5 and is_match(t, keyword):
                            link = href
                            title_text = t
                            break

                    if not link:
                        continue

                    # Giá — lấy tất cả giá trong card, chọn giá nhỏ nhất hợp lệ
                    price_text = ""
                    price_num = None
                    spans = card.locator("span:has-text('₫'), span[class*='price'], div[class*='price']").all()
                    candidates = []
                    for sp in spans:
                        txt = sp.inner_text().strip()
                        num = parse_price(txt)
                        if num and is_price_valid(num, min_price, max_price):
                            candidates.append((num, format_vnd(num)))
                    if candidates:
                        candidates.sort(key=lambda x: x[0])
                        price_num, price_text = candidates[0]

                    if not price_num:
                        continue

                    print(f"  [Lazada] ✓ {title_text[:45]} — {price_text}")
                    results.append({
                        "title": title_text,
                        "link": link,
                        "price_text": price_text,
                        "price_num": price_num,
                    })
                except Exception as e:
                    continue

            browser.close()

    except Exception as e:
        print(f"[Lazada] Lỗi: {e}")

    results.sort(key=lambda x: x["price_num"])
    return results


# ─── Shopee ───────────────────────────────────────────────────────────────────

def search_shopee(keyword, min_price, max_price):
    """Tìm kiếm Shopee, sort giá tăng dần."""
    encoded = urllib.parse.quote_plus(keyword)
    url = (
        f"https://shopee.vn/search"
        f"?keyword={encoded}"
        f"&minPrice={min_price}"
        f"&maxPrice={max_price}"
        f"&sortBy=price"
    )

    results = []
    try:
        with sync_playwright() as p:
            browser, context = _launch_browser(p)
            page = context.new_page()
            _apply_stealth(page)

            page.route("**/*.{png,jpg,jpeg,gif,webp,svg}", lambda r: r.abort())

            print(f"  [Shopee] Mở: {url}")
            page.goto(url, timeout=60000, wait_until="networkidle")
            page.wait_for_timeout(5000)

            title = page.title()
            print(f"  [Shopee] Tiêu đề trang: {title}")

            # Shopee hiện tại render card bằng thẻ <a> chứa link sản phẩm
            # Tìm tất cả link sản phẩm trực tiếp
            product_links = page.locator('a[href*="-i."]').all()
            print(f"  [Shopee] Tìm thấy {len(product_links)} link sản phẩm")

            seen = set()
            for a in product_links:
                if len(results) >= 5:
                    break
                try:
                    href = a.get_attribute("href")
                    href = fix_link(href, base="https://shopee.vn")
                    if not href or href in seen:
                        continue
                    seen.add(href)

                    # Title từ text bên trong link
                    title_text = a.inner_text().strip()
                    # Shopee thường có nhiều text lồng nhau, lấy dòng dài nhất
                    lines = [l.strip() for l in title_text.split("\n") if len(l.strip()) > 5]
                    if not lines:
                        continue
                    title_text = max(lines, key=len)

                    if not is_match(title_text, keyword):
                        continue

                    # Giá: tìm trong nội dung text — format "₫xxx.xxx"
                    full_text = a.inner_text()
                    price_matches = re.findall(r"₫[\d\.]+", full_text)
                    if not price_matches:
                        price_matches = re.findall(r"[\d\.]+₫", full_text)
                    if not price_matches:
                        price_matches = re.findall(r"[\d]{3,}\.[\d]{3}", full_text)

                    price_num = None
                    price_text = ""
                    candidates = []
                    for pm in price_matches:
                        num = parse_price(pm)
                        if num and is_price_valid(num, min_price, max_price):
                            candidates.append((num, format_vnd(num)))
                    if candidates:
                        candidates.sort(key=lambda x: x[0])
                        price_num, price_text = candidates[0]

                    if not price_num:
                        continue

                    print(f"  [Shopee] ✓ {title_text[:45]} — {price_text}")
                    results.append({
                        "title": title_text,
                        "link": href,
                        "price_text": price_text,
                        "price_num": price_num,
                    })
                except Exception:
                    continue

            browser.close()

    except Exception as e:
        print(f"[Shopee] Lỗi: {e}")

    results.sort(key=lambda x: x["price_num"])
    return results


# ─── Hàm chính ────────────────────────────────────────────────────────────────

def search_products(keyword, min_price, max_price):
    """Tìm Lazada trước, nếu không có thì tìm Shopee."""
    print("Thử quét Lazada (giá tăng dần)...")
    res = search_lazada(keyword, min_price, max_price)
    if res:
        return res

    time.sleep(2)
    print("Lazada không có. Thử quét Shopee (giá tăng dần)...")
    return search_shopee(keyword, min_price, max_price)
