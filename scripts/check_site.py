from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
import json
import re
import cv2
import numpy as np
from playwright.sync_api import sync_playwright

class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory="site"))
Thread(target=server.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{server.server_port}/"
work = Path("work/check")
work.mkdir(parents=True, exist_ok=True)
test_url = "https://example.com/lesson?week=6&tool=qrnshort#result"
passed = []

def decode(data):
    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    value, points, _ = cv2.QRCodeDetector().detectAndDecode(image)
    assert value == test_url, f"QR contents mismatch: {value!r}"
    assert points is not None

with sync_playwright() as p:
    browser = p.chromium.launch()
    context = browser.new_context(viewport={"width": 1440, "height": 1100})
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(base, wait_until="networkidle")
    assert page.locator("a[href='./qrnshort/']").count() == 1
    assert page.locator("a[href='./url2qr/']").count() == 1
    assert page.locator("form.search").get_attribute("action") == "https://www.google.com/search"
    page.locator("#note").fill("브라우저 메모 저장 확인")
    page.locator("#save-note").click()
    page.reload(wait_until="networkidle")
    assert page.locator("#note").input_value() == "브라우저 메모 저장 확인"
    page.locator("#note").fill("")
    page.locator("#save-note").click()
    passed.append("Homepage navigation, search form and memo persistence")
    page.goto(base + "url2qr/", wait_until="networkidle")
    page.locator("#convert-button").click()
    assert page.locator("#notice").get_attribute("data-kind") == "error"
    page.locator("#url-input").fill("javascript:alert(1)")
    page.locator("#convert-button").click()
    assert page.locator("#notice").get_attribute("data-kind") == "error"
    assert page.locator("#qr-code canvas").count() == 0
    page.locator("#url-input").fill(test_url)
    page.locator("#convert-button").click()
    page.wait_for_function("document.querySelector('#notice').dataset.kind === 'success'")
    page.wait_for_timeout(300)
    decode(page.locator(".qr-frame").screenshot())
    with page.expect_download() as info:
        page.locator("#download-qr").click()
    download = info.value
    download.save_as(work / "qr-download.png")
    decode((work / "qr-download.png").read_bytes())
    assert page.locator("#original-link").get_attribute("href") == test_url
    passed.append("URL2QR invalid input, QR decoding and PNG download")
    page.goto(base + "qrnshort/", wait_until="networkidle")
    assert page.locator("#url2qr-link").get_attribute("href") == "../url2qr/"
    page.route("https://spoo.me/api/v1/shorten", lambda route: route.abort())
    page.locator("#url-input").fill(test_url)
    page.locator("#convert-button").click()
    page.wait_for_function("document.querySelector('#notice').dataset.kind === 'error'")
    assert page.locator("#short-result").is_hidden()
    assert not page.locator("#convert-button").is_disabled()
    decode(page.locator(".qr-frame").screenshot())
    passed.append("QRnShort connection and honest short-service failure handling")
    for path in ["", "url2qr/", "qrnshort/"]:
        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(base + path, wait_until="networkidle")
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), path
    passed.append("All three pages fit a mobile viewport")
    assert not errors, errors
    browser.close()

print(json.dumps({"passed": passed, "browser_errors": errors}, ensure_ascii=False))

import runpy
import os
os.environ['PROBE_APP_URL'] = base + 'qrnshort/'
runpy.run_path('scripts/probe_short.py', run_name='__main__')
server.shutdown()
