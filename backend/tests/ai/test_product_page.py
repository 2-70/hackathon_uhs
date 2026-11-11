import asyncio

import httpx
from pydantic import HttpUrl

from backend.app.ai import product_page
from backend.app.ai.product_page import read_product_page

SHOP_PAGE = """<html><head><meta property="og:title" content="[남녀공용] 루즈핏 옥스포드 셔츠- 이랜드몰">
<script>var menu = "세탁방법 및 취급시 주의사항 드라이클리닝";</script></head><body>
<nav>세탁/다림용품 빨래건조대</nav>
<table><tr><th>제품 소재 (섬유의 조성 또는 혼용률을 백분율로 표시)</th><td>면 100%</td></tr>
<tr><th>세탁방법 및 취급시 주의사항</th><td>손세탁</td></tr></table></body></html>"""


def read(url: str, handler) -> object:
    async def fetch():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await read_product_page(client, HttpUrl(url))

    return asyncio.run(fetch())


def test_shop_page_supplies_the_product_notice():
    def shop(request):
        assert request.url.host == "www.elandmall.co.kr"
        return httpx.Response(200, headers={"content-type": "text/html;charset=UTF-8"}, text=SHOP_PAGE)

    page = read("https://www.elandmall.co.kr/i/item?itemNo=2206858302", shop)

    assert page.text.startswith("[남녀공용] 루즈핏 옥스포드 셔츠")
    assert "면 100%" in page.text and "세탁방법 및 취급시 주의사항 손세탁" in page.text
    # Menus before the notice and scripts are not product information.
    assert "빨래건조대" not in page.text.split("제품 소재")[1] and "드라이클리닝" not in page.text
    assert page.photo is None and page.style_code is None


def test_any_public_shop_is_read_and_private_addresses_are_not(monkeypatch):
    async def public(host):
        return host == "shop.example.com"

    def shop(request):
        assert request.url.host == "shop.example.com"
        embedded = '<script>window.data = {"notice": "제품 소재 \\ud3f4\\ub9ac\\uc5d0\\uc2a4\\ud130 100% 세탁방법 및 취급시 주의사항 단독 세탁"}</script>'
        return httpx.Response(200, headers={"content-type": "text/html"}, text=(
            f"<html><head><title>바람막이 재킷 | 쇼핑몰</title>{embedded}</head><body>상품</body></html>"
        ))

    monkeypatch.setattr(product_page, "is_public_host", public)
    page = read("https://shop.example.com/goods/774", shop)
    # The notice drawn by the browser is read from the data embedded in the page.
    assert page.text.startswith("바람막이 재킷") and "폴리에스터 100%" in page.text and "단독 세탁" in page.text

    monkeypatch.undo()
    for address in ("https://localhost/item", "https://10.0.0.5/item", "https://intranet.local/item"):
        assert asyncio.run(product_page.is_public_host(HttpUrl(address).host)) is False


def test_blocked_or_unknown_pages_are_not_used():
    blocked = read("https://www.musinsa.com/products/5560241", lambda _: httpx.Response(403, text="blocked"))
    without_notice = read("https://www.29cm.co.kr/products/1", lambda _: httpx.Response(
        200, headers={"content-type": "text/html"}, text="<html><body>셔츠</body></html>",
    ))

    def unexpected(request):
        raise AssertionError(f"A private address was fetched: {request.url.host}")

    assert blocked is None and without_notice is None
    assert read("https://10.0.0.5/goods/774", unexpected) is None
