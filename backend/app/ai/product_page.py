import re
from asyncio import gather, get_running_loop
from collections.abc import Sequence
from dataclasses import dataclass
from html.parser import HTMLParser
from ipaddress import ip_address

import httpx
from PIL import Image
from pydantic import HttpUrl, ValidationError
from starlette.concurrency import run_in_threadpool

from .catalog import official_url_key, product_code_key
from .lens import LensCandidate, prepare_lens_image
from .web_search import WebSearchUnavailable

MAX_PAGE_BYTES = 2_000_000
MAX_IMAGE_BYTES = 3_000_000
PUMA_PRODUCT_HOSTS = {
    "puma.com", "www.puma.com", "kr.puma.com", "uk.puma.com", "us.puma.com", "eu.puma.com",
    "sg.puma.com", "in.puma.com", "th.puma.com", "jp.puma.com",
}
PRODUCT_IMAGE_HOSTS = {
    "images.puma.com", "static.nike.com", "assets.adidas.com", "image.uniqlo.com",
    "asset.m-gs.kr", "img.29cm.co.kr", "image.msscdn.net", "itemimage.cjonstyle.net", "item.elandrs.com",
}
# Shops whose product pages have a known address. Only these hosts are read by the server.
RETAIL_PRODUCT_PATHS = {
    "www.29cm.co.kr": "/products/", "www.musinsa.com": "/products/",
    "m.gsshop.com": "/prd/prd.gs", "item.cjonstyle.com": ("/nfront/item/", "/item/"),
    "display.cjonstyle.com": "/p/item/", "www.elandmall.co.kr": "/i/item", "spao.elandmall.co.kr": "/i/item",
    "kream.co.kr": "/products/", "www.ssg.com": "/item/itemView.ssg", "www.lotteon.com": "/p/product/",
    "www.11st.co.kr": "/products/", "item.gmarket.co.kr": "/Item", "www.coupang.com": "/vp/products/",
}
# Korean shops must publish the fiber content and care of a garment in a product notice table.
PRODUCT_NOTICE = re.compile(r"제품\s*소재|섬유의\s*조성|혼용률")
CARE_NOTICE = re.compile(r"세탁\s*방법\s*및\s*취급")
SEARCH_THUMBNAIL_HOST = re.compile(r"encrypted-tbn\d+\.gstatic\.com|serpapi\.com")
STYLE_NUMBER = re.compile(
    r"(?:\b(?:style(?:\s+(?:no\.?|number))?|product (?:id|code)|article number)|스타일 번호|품번|상품 코드)"
    r"\s*:?\s*([a-z]{1,5}\d{3,8}(?:-[a-z0-9]{2,6})?|\d{6}[-_ ]?\d{2}|\d{6})\b",
    re.IGNORECASE,
)
CARE_HEADING = re.compile(
    r"care instructions|washing instructions|세탁방법|세탁 방법|세탁기 사용 가능|machine wash|洗濯機洗い", re.IGNORECASE,
)


class ProductHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.text: list[str] = []
        self.image = ""
        self.title = ""
        self.hidden_tag: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self.hidden_tag is None:
            self.hidden_tag = tag
        if tag == "meta":
            attributes = dict(attrs)
            if attributes.get("property") == "og:image" and not self.image:
                self.image = attributes.get("content") or ""
            if attributes.get("property") == "og:title" and not self.title:
                self.title = (attributes.get("content") or "").strip()

    def handle_endtag(self, tag: str) -> None:
        if tag == self.hidden_tag:
            self.hidden_tag = None

    def handle_data(self, data: str) -> None:
        if self.hidden_tag is None and (value := data.strip()):
            self.text.append(value)


@dataclass(frozen=True)
class ProductPage:
    url: HttpUrl
    text: str
    style_code: str | None
    photo: bytes | None


async def read_public_asset(client: httpx.AsyncClient, url: HttpUrl, prefix: str, limit: int) -> bytes | None:
    async with client.stream("GET", str(url)) as response:
        if response.status_code != 200 or not response.headers.get("content-type", "").startswith(prefix):
            return None
        data = bytearray()
        async for chunk in response.aiter_bytes():
            if len(data) + len(chunk) > limit:
                return None
            data.extend(chunk)
        return bytes(data)


def is_direct_product_page(url: HttpUrl) -> bool:
    path = url.path or ""
    host = (url.host or "").removeprefix("www.")
    if url.host in PUMA_PRODUCT_HOSTS:
        return "/pd/" in path
    if host == "nike.com":
        return "/t/" in path
    if host in {"adidas.com", "adidas.co.kr"}:
        return bool(re.search(r"/[a-z]{1,3}\d{4,6}\.html$", path, re.IGNORECASE))
    if host == "uniqlo.com":
        return "/products/" in path
    return url.host == "m.gsshop.com" and path == "/prd/prd.gs"


def is_listing_page(url: HttpUrl) -> bool:
    """A category or search page on a storefront whose product page addresses are known."""
    host = (url.host or "").removeprefix("www.")
    known_storefront = url.host in PUMA_PRODUCT_HOSTS or host in {"nike.com", "adidas.com", "adidas.co.kr", "uniqlo.com"}
    return known_storefront and not is_direct_product_page(url)


async def read_candidate_photo(client: httpx.AsyncClient, candidate: LensCandidate) -> bytes | None:
    for url in (candidate.image_url, candidate.thumbnail_url):
        if url is None or official_url_key(url) is None:
            continue
        # Download only from known product CDNs and the search provider's own thumbnails.
        if url.host not in PRODUCT_IMAGE_HOSTS and not SEARCH_THUMBNAIL_HOST.fullmatch(url.host or ""):
            continue
        try:
            image = await read_public_asset(client, url, "image/", MAX_IMAGE_BYTES)
            if image:
                return await run_in_threadpool(prepare_lens_image, image)
        except (httpx.HTTPError, OSError, ValueError, Image.DecompressionBombError, WebSearchUnavailable):
            continue
    return None


async def read_candidate_photos(candidates: Sequence[LensCandidate]) -> dict[tuple, bytes]:
    """Photos that the image search found on each candidate page, keyed by the page."""
    shown = [candidate for candidate in candidates[:12] if official_url_key(candidate.source_url)]
    if not shown:
        return {}
    async with httpx.AsyncClient(timeout=httpx.Timeout(4, connect=3)) as client:
        photos = await gather(*(read_candidate_photo(client, candidate) for candidate in shown))
    return {
        official_url_key(candidate.source_url): photo
        for candidate, photo in zip(shown, photos, strict=True) if photo
    }


def is_retail_product_page(url: HttpUrl) -> bool:
    path = RETAIL_PRODUCT_PATHS.get(url.host or "")
    return bool(path and (url.path or "").startswith(path))


async def read_page_photo(client: httpx.AsyncClient, address: str) -> bytes | None:
    if not address:
        return None
    image_url = HttpUrl(address)
    if image_url.host not in PRODUCT_IMAGE_HOSTS or official_url_key(image_url) is None:
        return None
    image = await read_public_asset(client, image_url, "image/", MAX_IMAGE_BYTES)
    return await run_in_threadpool(prepare_lens_image, image) if image else None


async def is_public_host(host: str | None) -> bool:
    """A named host that resolves only to public addresses. The server never fetches private or local addresses."""
    if not host or "." not in host or host.endswith((".local", ".localhost", ".internal")):
        return False
    try:
        ip_address(host.strip("[]"))
        return False
    except ValueError:
        pass
    try:
        found = await get_running_loop().getaddrinfo(host, 443)
    except OSError:
        return False
    return bool(found) and all(ip_address(item[4][0]).is_global for item in found)


def embedded_text(html: str) -> str:
    """Text that a shop renders from data in its scripts, such as a product notice kept as JSON."""
    scripts = " ".join(re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL | re.IGNORECASE))
    scripts = re.sub(r"\\u([0-9a-fA-F]{4})", lambda code: chr(int(code[1], 16)), scripts)
    scripts = scripts.replace('\\"', '"').replace("\\n", " ").replace("\\/", "/")
    return " ".join(re.sub(r"<[^>]+>", " ", scripts).split())


async def read_retail_page(client: httpx.AsyncClient, url: HttpUrl) -> ProductPage | None:
    """The product name and the product notice table of a shop page. None when the page shows no notice."""
    try:
        html = await read_public_asset(client, url, "text/html", MAX_PAGE_BYTES)
        if not html:
            return None
        source = html.decode("utf-8", errors="replace")
        product = ProductHTML()
        product.feed(source)
        visible = " ".join(product.text)
        notice = PRODUCT_NOTICE.search(visible)
        if notice is None:
            # Some shops draw the notice in the browser from data embedded in the page.
            visible = embedded_text(source)
            notice = PRODUCT_NOTICE.search(visible)
        if notice is None:
            return None
        title = product.title
        if not title and (heading := re.search(r"<title[^>]*>(.*?)</title>", source, re.DOTALL | re.IGNORECASE)):
            title = " ".join(heading[1].split())
        # Menus and reviews surround the notice. Keep the product name and the notice itself.
        text = f"{title}\n{visible[max(0, notice.start() - 200):notice.start() + 1600]}"
        care = CARE_NOTICE.search(visible, notice.start())
        if care and care.start() > notice.start() + 1500:
            text += "\n" + visible[care.start():care.start() + 600]
        return ProductPage(url, text, None, await read_page_photo(client, product.image))
    except (httpx.HTTPError, OSError, ValidationError, ValueError, WebSearchUnavailable):
        return None


async def read_product_page(client: httpx.AsyncClient, url: HttpUrl) -> ProductPage | None:
    if official_url_key(url) is None:
        return None
    if not is_direct_product_page(url):
        # Any shop page can carry a product notice. Listing pages of known storefronts cannot.
        if is_listing_page(url) or not (is_retail_product_page(url) or await is_public_host(url.host)):
            return None
        return await read_retail_page(client, url)
    try:
        expected_style = None
        # Puma's style-code URLs redirect to the named product on the same storefront.
        if style_path := re.search(r"/pd/(\d{6})\.html$", url.path or ""):
            base = style_path[1]
            if color := httpx.URL(str(url)).params.get(f"dwvar_{base}_color"):
                expected_style = f"{base}{color}"
            response = await client.head(str(url))
            if response.is_redirect and response.headers.get("location"):
                destination = HttpUrl(str(response.url.join(response.headers["location"])))
                if (
                    destination.host != url.host or official_url_key(destination) is None
                    or not is_direct_product_page(destination)
                ):
                    return None
                url = destination
        html = await read_public_asset(client, url, "text/html", MAX_PAGE_BYTES)
        if not html:
            return None
        product = ProductHTML()
        product.feed(html.decode("utf-8", errors="replace"))
        visible_text = " ".join(product.text)
        # Read the selected colorway printed by Puma, rather than variant IDs in scripts.
        style = STYLE_NUMBER.search(visible_text)
        style_code = product_code_key(style[1]) if style else None
        if (url.host in PUMA_PRODUCT_HOSTS and not style_code) or (expected_style and style_code != expected_style):
            return None
        photo = await read_page_photo(client, product.image)
        if style:
            text = visible_text[max(0, style.start() - 2800):style.end() + 6000]
        else:
            text = visible_text[:6000]
        # Product disclosures can appear below long size tables and galleries.
        care = CARE_HEADING.search(visible_text, style.start() if style else 0)
        if care and care[0] not in text:
            text += "\n" + visible_text[max(0, care.start() - 500):care.end() + 3000]
        return ProductPage(url, text, style_code, photo)
    except (httpx.HTTPError, OSError, ValidationError, ValueError, WebSearchUnavailable):
        return None
