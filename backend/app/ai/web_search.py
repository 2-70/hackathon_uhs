import base64

import httpx
from pydantic import BaseModel, Field, HttpUrl


class WebImage(BaseModel):
    url: HttpUrl


class WebPage(WebImage):
    full_images: list[WebImage] = Field(default_factory=list, alias="fullMatchingImages")


class WebDetection(BaseModel):
    full_images: list[WebImage] = Field(default_factory=list, alias="fullMatchingImages")
    pages: list[WebPage] = Field(default_factory=list, alias="pagesWithMatchingImages")

    def full_image_urls(self) -> list[HttpUrl]:
        return [item.url for item in self.full_images] + [
            image.url for page in self.pages for image in page.full_images
        ]


class WebSearchUnavailable(Exception):
    pass


class VisionWebSearch:
    def __init__(self, api_key: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.api_key = api_key
        self.transport = transport

    async def search(self, image: bytes) -> WebDetection:
        # Vision accepts up to 10 MB of JSON, including base64 overhead.
        if len(image) > 7_000_000:
            raise WebSearchUnavailable

        payload = {"requests": [{
            "image": {"content": base64.b64encode(image).decode("ascii")},
            "features": [{"type": "WEB_DETECTION", "maxResults": 10}],
        }]}
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(12, connect=3), transport=self.transport) as client:
                response = await client.post(
                    "https://vision.googleapis.com/v1/images:annotate",
                    headers={"x-goog-api-key": self.api_key},
                    json=payload,
                )
                response.raise_for_status()
            annotation = response.json()["responses"][0]
            if annotation.get("error"):
                raise WebSearchUnavailable
            return WebDetection.model_validate(annotation.get("webDetection", {}))
        except (httpx.HTTPError, AttributeError, IndexError, KeyError, TypeError, ValueError):
            raise WebSearchUnavailable from None
