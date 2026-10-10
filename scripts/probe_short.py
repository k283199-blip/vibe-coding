import json
import os
from playwright.sync_api import sync_playwright

HOME = "https://k283199-blip.github.io/vibe-coding/"
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width":1440,"height":1100})
    result = {"responses":[], "failed_requests":[], "browser_errors":[], "console_errors":[]}
    def response_info(response):
        if "spoo.me/api/v1/shorten" not in response.url:
            return
        item = {"status":response.status, "url":response.url,
                "content_type":response.headers.get("content-type"),
                "cors":response.headers.get("access-control-allow-origin")}
        try:
            item["body"] = response.text()[:1500]
        except Exception as exc:
            item["body_error"] = str(exc)
        result["responses"].append(item)
    page.on("response", response_info)
    page.on("requestfailed", lambda req: result["failed_requests"].append(
        {"url":req.url,"failure":req.failure}) if "spoo.me" in req.url else None)
    page.on("pageerror", lambda error: result["browser_errors"].append(str(error)))
    page.on("console", lambda message: result["console_errors"].append(message.text[:1000]) if message.type == "error" else None)
    response = page.goto(os.environ.get("PROBE_APP_URL", HOME+"qrnshort/"), wait_until="networkidle", timeout=30000)
    result["page_http_status"] = response.status if response else None
    page.locator("#url-input").fill(HOME)
    page.locator("#convert-button").click()
    try:
        page.wait_for_function("['error','success'].includes(document.querySelector('#notice').dataset.kind)", timeout=30000)
    except Exception as exc:
        result["wait_error"] = str(exc)
    result["notice"] = page.locator("#notice").inner_text()
    result["notice_kind"] = page.locator("#notice").get_attribute("data-kind")
    result["short_href"] = page.locator("#short-link").get_attribute("href")
    result["short_text"] = page.locator("#short-link").inner_text()
    result["has_qr"] = page.locator("#qr-code canvas").count() == 1
    if result["short_href"]:
        destination = browser.new_page()
        redirected = destination.goto(result["short_href"], wait_until="domcontentloaded", timeout=30000)
        result["redirect_status"] = redirected.status if redirected else None
        result["redirect_destination"] = destination.url
        destination.close()
    print("SHORT_SERVICE_PROBE_BEGIN"+json.dumps(result,ensure_ascii=False)+"SHORT_SERVICE_PROBE_END")
    assert result["notice_kind"] == "success", "Real shortening failed: " + result["notice"]
    assert result.get("redirect_status") == 200 and result.get("redirect_destination", "").rstrip("/") == HOME.rstrip("/"), "Short link did not redirect to original"
    browser.close()
