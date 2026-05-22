import re
import urllib.parse
# pyrefly: ignore [missing-import]
from playwright.sync_api import sync_playwright


# ─── Tiện ích ─────────────────────────────────────────────────────────────────

def fix_link(link, base="https://www.lazada.vn"):
    """Chuẩn hóa link về dạng https:// đầy đủ."""
    if not link:
        return None
    link = link.strip()
    if link.startswith("http"):
        return link
    if link.startswith("//"):
        return "https:" + link
    if link.startswith("/"):
        return base.rstrip("/") + link
    return None  # link không hợp lệ

def parse_price(text):
    """
    Trích giá trị số từ chuỗi như '28.990.000 ₫' hoặc '1,290,000đ'.
    Trả về int hoặc None nếu không tìm được.
    """
    if not text:
        return None
    # Xóa ký tự không phải số / dấu phân cách
    cleaned = re.sub(r"[^\d]", "", text)
    return int(cleaned) if cleaned else None

def is_price_valid(price_num, min_price, max_price):
    """Kiểm tra giá có nằm trong khoảng hợp lệ không."""
    if price_num is None:
        return False
    return min_price <= price_num <= max_price


# ─── Lazada ───────────────────────────────────────────────────────────────────

def search_lazada(keyword, min_price, max_price):
    """
    Tìm kiếm Lazada, sort giá tăng dần, chỉ lấy sản phẩm có giá hợp lệ.
    """
    encoded_keyword = urllib.parse.quote_plus(keyword)
    # sort=price&order=ASC → sắp xếp giá thấp nhất lên đầu
    url = (
        f"https://www.lazada.vn/catalog/"
        f"?q={encoded_keyword}"
        f"&price={min_price}-{max_price}"
        f"&sort=price&order=ASC"
    )

    results = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 900},
            )
            page = context.new_page()
            # Chặn ảnh/font để tải nhanh hơn
            page.route(
                "**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf}",
                lambda route: route.abort()
            )

            print(f"  [Lazada] Mở URL (sort=giá tăng dần): {url}")
            page.goto(url, timeout=60000, wait_until="domcontentloaded")

            # Thử nhiều selector card sản phẩm
            card_selectors = [
                '[data-qa-locator="product-item"]',
                'div[data-tracking="product-card"]',
                '.Bm3ON',
                'div[class*="gridItem"]',
            ]
            found_sel = None
            for sel in card_selectors:
                try:
                    page.wait_for_selector(sel, timeout=8000)
                    found_sel = sel
                    print(f"  [Lazada] Card selector: {sel}")
                    break
                except Exception:
                    continue

            if not found_sel:
                print(f"  [Lazada] Không tìm thấy sản phẩm: {keyword}")
                browser.close()
                return results

            cards = page.locator(found_sel).all()
            print(f"  [Lazada] Số card tìm thấy: {len(cards)}")

            for card in cards:
                if len(results) >= 5:
                    break
                try:
                    # ── Lấy link & title ──────────────────────────────────
                    link = None
                    title = None

                    # Ưu tiên <a title="..."> — đây là link sản phẩm chính
                    a_els = card.locator("a[title]").all()
                    for a in a_els:
                        href = fix_link(a.get_attribute("href"))
                        t = (a.get_attribute("title") or a.inner_text()).strip()
                        # Bỏ qua link rác (quảng cáo, banner, shop sponsor)
                        if href and "lazada.vn" in href and len(t) > 5:
                            link = href
                            title = t
                            break

                    # Fallback: <a> đầu tiên có href hợp lệ
                    if not link:
                        for a in card.locator("a").all():
                            href = fix_link(a.get_attribute("href"))
                            if href and "lazada.vn" in href and "/products/" not in href:
                                link = href
                                title = title or a.inner_text().strip()
                                break

                    if not link:
                        continue  # Bỏ qua card không có link hợp lệ

                    # ── Lấy giá ───────────────────────────────────────────
                    # Lazada thường có span.pdp-price hoặc span với ₫
                    price_text = ""
                    price_num = None
                    price_sels = [
                        "span.pdp-price",
                        "span[class*='price']",
                        "div[class*='price'] span",
                        "span:has-text('₫')",
                        ".aBrP0",
                    ]
                    for ps in price_sels:
                        try:
                            # Lấy tất cả spans giá trong card rồi chọn giá thấp nhất
                            # (tránh bị lừa bởi giá phụ kiện/variant bên trong)
                            els = card.locator(ps).all()
                            candidates = []
                            for el in els:
                                txt = el.inner_text().strip()
                                num = parse_price(txt)
                                if num and num > 1000:  # bỏ qua số rác
                                    candidates.append((num, txt))
                            if candidates:
                                # Lấy giá nhỏ nhất thực sự
                                candidates.sort(key=lambda x: x[0])
                                price_num, price_text = candidates[0]
                                break
                        except Exception:
                            continue

                    # Kiểm tra giá có nằm trong khoảng người dùng đặt không
                    if not is_price_valid(price_num, min_price, max_price):
                        print(f"  [Lazada] Bỏ qua (giá ngoài khoảng {price_num}): {title[:40] if title else '?'}")
                        continue

                    print(f"  [Lazada] ✓ {title[:45]!r} — {price_text} — {link[:60]}")
                    results.append({
                        "title": title,
                        "link": link,
                        "price_text": price_text,
                        "price_num": price_num,
                    })

                except Exception as e:
                    print(f"  [Lazada] Lỗi parse card: {e}")
                    continue

            browser.close()

    except Exception as e:
        print(f"[Lazada] Lỗi nghiêm trọng '{keyword}': {e}")

    # Sắp xếp lại theo giá tăng dần (đề phòng sort URL chưa hoạt động)
    results.sort(key=lambda x: x["price_num"])
    return results


# ─── Shopee ───────────────────────────────────────────────────────────────────

def search_shopee(keyword, min_price, max_price):
    """
    Tìm kiếm Shopee, sort giá tăng dần, chỉ lấy sản phẩm có giá hợp lệ.
    """
    encoded_keyword = urllib.parse.quote_plus(keyword)
    # sortBy=price → Shopee sort giá tăng dần
    url = (
        f"https://shopee.vn/search"
        f"?keyword={encoded_keyword}"
        f"&minPrice={min_price}"
        f"&maxPrice={max_price}"
        f"&sortBy=price"
    )

    results = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 900},
            )
            page = context.new_page()
            page.route(
                "**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf}",
                lambda route: route.abort()
            )

            print(f"  [Shopee] Mở URL (sortBy=price): {url}")
            page.goto(url, timeout=60000, wait_until="domcontentloaded")
            # Shopee render bằng JS, cần chờ thêm
            page.wait_for_timeout(5000)

            card_selectors = [
                'li[data-sqe="item"]',
                'div.shopee-search-item-result__item',
                'div[class*="col-xs-2-4"]',
            ]
            found_sel = None
            for sel in card_selectors:
                try:
                    page.wait_for_selector(sel, timeout=8000)
                    found_sel = sel
                    print(f"  [Shopee] Card selector: {sel}")
                    break
                except Exception:
                    continue

            if not found_sel:
                print(f"  [Shopee] Không tìm thấy sản phẩm: {keyword}")
                browser.close()
                return results

            cards = page.locator(found_sel).all()
            print(f"  [Shopee] Số card tìm thấy: {len(cards)}")

            for card in cards:
                if len(results) >= 5:
                    break
                try:
                    # ── Link ──────────────────────────────────────────────
                    link = None
                    a_el = card.locator("a").first
                    if a_el.count() > 0:
                        href = a_el.get_attribute("href")
                        link = fix_link(href, base="https://shopee.vn")

                    if not link or "shopee.vn" not in link:
                        continue

                    # ── Title ─────────────────────────────────────────────
                    title = ""
                    for ts in ['div[data-sqe="name"]', 'div[class*="name"]', 'div[class*="title"]']:
                        try:
                            el = card.locator(ts).first
                            if el.count() > 0:
                                title = el.inner_text().strip()
                                if title:
                                    break
                        except Exception:
                            continue

                    # ── Giá ───────────────────────────────────────────────
                    price_text = ""
                    price_num = None
                    price_sels = [
                        "span[class*='price']",
                        "div[class*='price'] span",
                        "span:has-text('₫')",
                        "span:has-text('đ')",
                    ]
                    for ps in price_sels:
                        try:
                            els = card.locator(ps).all()
                            candidates = []
                            for el in els:
                                txt = el.inner_text().strip()
                                num = parse_price(txt)
                                if num and num > 1000:
                                    candidates.append((num, txt))
                            if candidates:
                                candidates.sort(key=lambda x: x[0])
                                price_num, price_text = candidates[0]
                                break
                        except Exception:
                            continue

                    if not is_price_valid(price_num, min_price, max_price):
                        print(f"  [Shopee] Bỏ qua (giá ngoài khoảng {price_num}): {title[:40]}")
                        continue

                    print(f"  [Shopee] ✓ {title[:45]!r} — {price_text} — {link[:60]}")
                    results.append({
                        "title": title or "Sản phẩm Shopee",
                        "link": link,
                        "price_text": price_text.replace("\n", " ") or "Xem trên Shopee",
                        "price_num": price_num,
                    })

                except Exception as e:
                    print(f"  [Shopee] Lỗi parse card: {e}")
                    continue

            browser.close()

    except Exception as e:
        print(f"[Shopee] Lỗi nghiêm trọng '{keyword}': {e}")

    results.sort(key=lambda x: x["price_num"])
    return results


# ─── Hàm chính ────────────────────────────────────────────────────────────────

def search_products(keyword, min_price, max_price):
    """
    Thử tìm trên Lazada trước (sort giá tăng dần).
    Nếu không có kết quả hợp lệ thì tìm Shopee.
    """
    print("Thử quét Lazada (giá tăng dần)...")
    res = search_lazada(keyword, min_price, max_price)
    if res:
        return res

    print("Lazada không có / bị chặn. Thử quét Shopee (giá tăng dần)...")
    return search_shopee(keyword, min_price, max_price)
