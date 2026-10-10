"""Capture the live GitHub Pages site, verify it, and create the submission PDF."""
from __future__ import annotations
import base64
import io
import json
import os
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo
import cv2
import fitz
import requests
from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright
from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

OUT = Path("outputs")
EVIDENCE = Path("work/evidence")
OUT.mkdir(parents=True, exist_ok=True)
EVIDENCE.mkdir(parents=True, exist_ok=True)
PDF_PATH = OUT / "6week_assignment.pdf"
SITE = os.environ["SITE_URL"].strip().rstrip("/") + "/"
STUDENT_NAME = os.environ["STUDENT_NAME"].strip()
STUDENT_ID = os.environ["STUDENT_ID"].strip()
if not STUDENT_NAME or not STUDENT_ID:
    raise RuntimeError("STUDENT_NAME and STUDENT_ID must be supplied.")
if any(c in STUDENT_NAME + STUDENT_ID for c in "\r\n"):
    raise RuntimeError("Student identity must fit on one line.")
HOME = SITE
QRNSHORT = SITE + "qrnshort/"
URL2QR = SITE + "url2qr/"
ORIGINAL = HOME
CAPTURED = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y.%m.%d %H:%M KST")
validation = {"site_url": SITE, "captured_at": CAPTURED, "tests": {}}

def check(key, condition, message):
    validation["tests"][key] = bool(condition)
    if not condition:
        raise AssertionError(message)

def same_url(a, b):
    x, y = urlsplit(a), urlsplit(b)
    return (x.scheme.lower(), x.netloc.lower(), x.path.rstrip("/"), x.query, x.fragment) == (
        y.scheme.lower(), y.netloc.lower(), y.path.rstrip("/"), y.query, y.fragment)

def settle(page):
    page.wait_for_load_state("domcontentloaded")
    page.evaluate("() => document.fonts.ready")
    page.wait_for_timeout(250)

def goto_live(page, url, required_selector):
    for attempt in range(10):
        try:
            response = page.goto(url, wait_until="domcontentloaded", timeout=30000)
            if response is None or response.status != 200:
                raise RuntimeError("Live URL did not return HTTP 200.")
            page.locator(required_selector).first.wait_for(state="attached", timeout=10000)
            settle(page)
            return
        except Exception:
            if attempt == 9:
                raise
            page.wait_for_timeout(3000)

def click_navigation(page, locator, expected_url):
    href = locator.evaluate("(el) => el.href")
    check("navigation_href_" + urlsplit(expected_url).path.rstrip("/").split("/")[-1],
          same_url(href.split("?")[0], expected_url), "Navigation link points to an unexpected page.")
    if locator.get_attribute("target") == "_blank":
        with page.context.expect_page(timeout=15000) as event:
            locator.click()
        target = event.value
    else:
        locator.click()
        target = page
    target.wait_for_url(lambda u: same_url(str(u).split("?")[0], expected_url),
                        wait_until="domcontentloaded", timeout=30000)
    settle(target)
    return target

def wait_qr(page):
    page.locator("#qr-code canvas").wait_for(state="attached", timeout=15000)
    page.wait_for_function("""() => {
        const c = document.querySelector('#qr-code canvas');
        const i = document.querySelector('#qr-code img');
        return c && c.width > 0 && (!i || i.complete);
    }""", timeout=15000)
    settle(page)

def convert(page, original, with_short):
    page.locator("#url-input").fill(original)
    page.locator("#convert-button").click()
    if with_short:
        page.wait_for_function("""() => {
            const a = document.querySelector('#short-link');
            return a && /^https:\\/\\/spoo\\.me\\/[A-Za-z0-9_-]+$/.test(a.href)
                && a.textContent.trim().length > 0;
        }""", timeout=30000)
    wait_qr(page)

def decode_qr(path):
    image = cv2.imread(str(path))
    if image is None:
        raise AssertionError("QR image was not saved as a readable PNG.")
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    detector = cv2.QRCodeDetector()
    for factor in (1, 2, 3):
        enlarged = cv2.resize(gray, None, fx=factor, fy=factor, interpolation=cv2.INTER_NEAREST)
        bordered = cv2.copyMakeBorder(enlarged, 32, 32, 32, 32, cv2.BORDER_CONSTANT, value=255)
        text, _, _ = detector.detectAndDecode(bordered)
        if text:
            return text
    raise AssertionError("The actual QR image could not be decoded.")

def capture_result(page, stem):
    settle(page)
    page.evaluate("window.scrollTo(0, 0)")
    screenshot = EVIDENCE / (stem + ".png")
    page.screenshot(path=str(screenshot), full_page=True, animations="disabled")
    qr_image = EVIDENCE / (stem + "_qr.png")
    page.locator(".qr-frame").screenshot(path=str(qr_image), animations="disabled")
    decoded = decode_qr(qr_image)
    check(stem + "_qr_decodes_to_original", decoded == ORIGINAL,
          "QR code does not encode the original URL.")
    with page.expect_download(timeout=15000) as download_event:
        page.locator("#download-qr").click()
    downloaded_path = EVIDENCE / (stem + "_download.png")
    download_event.value.save_as(str(downloaded_path))
    check(stem + "_download_decodes_to_original", decode_qr(downloaded_path) == ORIGINAL,
          "Downloaded QR PNG does not encode the original URL.")
    validation[stem + "_qr_value"] = decoded
    return screenshot

def test_invalid_url(browser):
    context = browser.new_context(viewport={"width": 1440, "height": 1100}, locale="ko-KR")
    page = context.new_page()
    goto_live(page, QRNSHORT, "#url-input")
    short_requests = []
    page.on("request", lambda req: short_requests.append(req.url) if "spoo.me/api/v1/shorten" in req.url else None)
    page.locator("#url-input").fill("javascript:alert(1)")
    page.locator("#convert-button").click()
    page.wait_for_timeout(400)
    href = page.locator("#short-link").get_attribute("href") or ""
    check("invalid_protocol_rejected",
          page.locator("#notice").get_attribute("data-kind") == "error"
          and not short_requests and not re.fullmatch(r"https://spoo\.me/[A-Za-z0-9_-]+", href),
          "Invalid URL protocol was not rejected before shortening.")
    context.close()

def test_mobile(browser, storage_state):
    context = browser.new_context(viewport={"width": 390, "height": 844},
        device_scale_factor=1, locale="ko-KR", storage_state=storage_state)
    page = context.new_page()
    for stem, url, selector in (
        ("home", HOME, 'a[href="./qrnshort/"]'),
        ("qrnshort", QRNSHORT, "#url-input"),
        ("url2qr", URL2QR, "#url-input")):
        goto_live(page, url, selector)
        if stem != "home":
            convert(page, ORIGINAL, stem == "qrnshort")
        dimensions = page.evaluate("""() => ({
            viewport: window.innerWidth, root: document.documentElement.scrollWidth,
            body: document.body.scrollWidth
        })""")
        check("mobile_" + stem + "_no_horizontal_overflow",
              max(dimensions["root"], dimensions["body"]) <= dimensions["viewport"] + 1,
              "The mobile page overflows horizontally: " + stem)
        page.evaluate("window.scrollTo(0, 0)")
        page.screenshot(path=str(EVIDENCE / ("mobile_" + stem + ".png")),
                        full_page=True, animations="disabled")
    validation["mobile_viewport"] = {"width": 390, "height": 844}
    context.close()

def browser_evidence():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 1100},
                                      device_scale_factor=1, locale="ko-KR")
        page = context.new_page()
        goto_live(page, HOME, 'a[href="./qrnshort/"]')
        home_url2qr = page.locator('a[href="./url2qr/"]').first
        check("homepage_url2qr_link", same_url(home_url2qr.evaluate("(el) => el.href"), URL2QR),
              "Homepage does not link to the deployed URL2QR page.")
        home_image = EVIDENCE / "homepage.png"
        page.screenshot(path=str(home_image), full_page=True, animations="disabled")
        page = click_navigation(page, page.locator('a[href="./qrnshort/"]').first, QRNSHORT)
        check("homepage_qrnshort_navigation", same_url(page.url, QRNSHORT),
              "Homepage QRnShort navigation failed.")
        convert(page, ORIGINAL, True)
        short_url = page.locator("#short-link").evaluate("(el) => el.href")
        check("short_url_is_real_spoo", bool(re.fullmatch(r"https://spoo\.me/[A-Za-z0-9_-]+", short_url)),
              "Converter did not return a real spoo.me short URL.")
        check("short_url_is_shorter", len(short_url) < len(ORIGINAL),
              "Generated short URL is not shorter than the original URL.")
        qrnshort_image = capture_result(page, "qrnshort")
        validation["short_url"] = short_url
        validation["original_url"] = ORIGINAL
        storage_state = context.storage_state()
        clean_context = browser.new_context(viewport={"width": 1440, "height": 1100}, locale="ko-KR")
        destination = clean_context.new_page()
        final_response = destination.goto(short_url, wait_until="domcontentloaded", timeout=30000)
        settle(destination)
        check("short_url_fresh_browser_http_200",
              final_response is not None and final_response.status == 200,
              "Short URL destination did not return HTTP 200.")
        check("short_url_fresh_browser_resolves_to_original", same_url(destination.url, ORIGINAL),
              "Short URL did not resolve to the original URL in a new browser.")
        validation["short_url_final_destination"] = destination.url
        destination.screenshot(path=str(EVIDENCE / "short_destination.png"),
                               full_page=True, animations="disabled")
        clean_context.close()
        response = requests.get(short_url, allow_redirects=True, timeout=30,
            headers={"User-Agent": "GitHubPagesAssignmentVerifier/1.0"})
        check("short_url_http_redirect", response.status_code == 200 and same_url(response.url, ORIGINAL),
              "HTTP redirect verification failed.")
        validation["short_redirect_chain"] = [
            {"status": item.status_code, "url": item.url} for item in response.history
        ] + [{"status": response.status_code, "url": response.url}]
        page = click_navigation(page, page.locator("a#url2qr-link"), URL2QR)
        check("qrnshort_url2qr_link_navigation", same_url(page.url.split("?")[0], URL2QR),
              "QRnShort's URL2QR navigation failed.")
        validation["url2qr_navigation_url"] = page.url
        convert(page, ORIGINAL, False)
        url2qr_image = capture_result(page, "url2qr")
        context.close()
        test_invalid_url(browser)
        test_mobile(browser, storage_state)
        validation["browser"] = "Playwright Chromium " + browser.version
        validation["desktop_viewport"] = {"width": 1440, "height": 1100}
        browser.close()
    return home_image, qrnshort_image, url2qr_image

FONT_PATH = Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf")
FONT_BOLD_PATH = Path("/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf")
if not FONT_PATH.exists():
    raise RuntimeError("Install fonts-nanum before generating the report.")
pdfmetrics.registerFont(TTFont("Nanum", str(FONT_PATH)))
pdfmetrics.registerFont(TTFont("NanumBold", str(FONT_BOLD_PATH if FONT_BOLD_PATH.exists() else FONT_PATH)))
pdfmetrics.registerFontFamily("Nanum", normal="Nanum", bold="NanumBold",
                             italic="Nanum", boldItalic="NanumBold")
PAGE_W, PAGE_H = A4
MARGIN = 38
CONTENT_W = PAGE_W - MARGIN * 2
INK = colors.HexColor("#172B45")
MUTED = colors.HexColor("#53657C")
BLUE = colors.HexColor("#245DCD")
PALE = colors.HexColor("#F2F6FC")
RULE = colors.HexColor("#DCE4EF")
styles = {
    "body": ParagraphStyle("body", fontName="Nanum", fontSize=10, leading=15,
                           textColor=INK, wordWrap="CJK"),
    "small": ParagraphStyle("small", fontName="Nanum", fontSize=8.5, leading=12,
                            textColor=MUTED, wordWrap="CJK"),
    "url": ParagraphStyle("url", fontName="Nanum", fontSize=9.2, leading=14,
                          textColor=BLUE, wordWrap="CJK", splitLongWords=True),
}
def paragraph(pdf, text, x, top, width, style="body"):
    p = Paragraph(text, styles[style])
    _, height = p.wrap(width, PAGE_H)
    p.drawOn(pdf, x, top - height)
    return top - height

def page_header(pdf, page_no):
    pdf.setFillColor(BLUE)
    pdf.rect(0, PAGE_H - 8, PAGE_W, 8, fill=1, stroke=0)
    pdf.setFillColor(INK)
    pdf.setFont("NanumBold", 18)
    pdf.drawString(MARGIN, PAGE_H - 43, "바이브코딩 6주차 · GitHub Pages")
    pdf.setFont("Nanum", 9.5)
    pdf.setFillColor(MUTED)
    pdf.drawString(MARGIN, PAGE_H - 72,
                   "제출자: " + STUDENT_NAME + "    |    학번: " + STUDENT_ID)
    pdf.setStrokeColor(RULE)
    pdf.line(MARGIN, PAGE_H - 91, PAGE_W - MARGIN, PAGE_H - 91)
    pdf.setFont("Nanum", 8)
    pdf.drawString(MARGIN, 23, "제출 기한: 2026.10.22    ·    실제 배포 화면 및 URL 확인")
    pdf.drawRightString(PAGE_W - MARGIN, 23, str(page_no) + " / 3")
    return PAGE_H - 116

def section_heading(pdf, text, top):
    pdf.setFont("NanumBold", 13)
    pdf.setFillColor(INK)
    pdf.drawString(MARGIN, top, text)
    return top - 24

def linked_url(pdf, label, url, top):
    top = paragraph(pdf, escape(label), MARGIN, top, CONTENT_W, "small") - 3
    safe = escape(url, {'"': "&quot;"})
    top = paragraph(pdf, '<link href="' + safe + '" color="#245DCD">' + safe + '</link>',
                    MARGIN, top, CONTENT_W, "url")
    return top - 14

def screenshot_box(pdf, image_path, top, max_height):
    with Image.open(image_path) as im:
        width, height = im.size
    ratio = min(CONTENT_W / width, max_height / height)
    draw_w, draw_h = width * ratio, height * ratio
    x = MARGIN + (CONTENT_W - draw_w) / 2
    pdf.setFillColor(colors.white)
    pdf.setStrokeColor(RULE)
    pdf.roundRect(x - 1, top - draw_h - 1, draw_w + 2, draw_h + 2, 3, stroke=1, fill=1)
    pdf.drawImage(str(image_path), x, top - draw_h, width=draw_w, height=draw_h,
                  preserveAspectRatio=True, mask="auto")
    top -= draw_h + 10
    return paragraph(pdf, "실제 배포 사이트를 Chromium 웹 브라우저에서 열어 촬영한 화면입니다.",
                     MARGIN, top, CONTENT_W, "small") - 14

def facts_box(pdf, rows, top):
    text_top = top - 12
    measured = []
    for label, value in rows:
        line = "<b>" + escape(label) + "</b>  " + escape(str(value))
        p = Paragraph(line, styles["small"])
        _, height = p.wrap(CONTENT_W - 24, PAGE_H)
        measured.append((p, height))
    total = sum(height + 6 for _, height in measured) + 18
    pdf.setFillColor(PALE)
    pdf.setStrokeColor(RULE)
    pdf.roundRect(MARGIN, top - total, CONTENT_W, total, 6, fill=1, stroke=1)
    for p, height in measured:
        p.drawOn(pdf, MARGIN + 12, text_top - height)
        text_top -= height + 6
    return top - total - 14

def make_pdf(images):
    pdf = canvas.Canvas(str(PDF_PATH), pagesize=A4)
    pdf.setTitle("바이브코딩 6주차 GitHub Pages 과제")
    pdf.setAuthor(STUDENT_NAME)
    pdf.setSubject("시작 홈페이지 및 QRnShort 배포 URL과 실제 웹 브라우저 화면")
    home_image, qrnshort_image, url2qr_image = images
    top = page_header(pdf, 1)
    top = section_heading(pdf, "① 나만의 시작 홈페이지", top)
    top = paragraph(pdf, "5주차 1교시 GitHub Pages 배포 / 프로젝트02",
                    MARGIN, top, CONTENT_W, "small") - 12
    top = linked_url(pdf, "배포 URL — 아래 주소를 클릭하면 홈페이지로 연결됩니다.", HOME, top)
    top = screenshot_box(pdf, home_image, top, 402)
    top = paragraph(pdf, "GitHub Pages에 배포한 시작 홈페이지입니다. 홈페이지에서 QRnShort와 "
                     "URL2QR로 이동할 수 있도록 연결했습니다.", MARGIN, top, CONTENT_W) - 10
    top = facts_box(pdf, [("확인 결과", "배포 URL 접속 및 QRnShort·URL2QR 링크 연결 확인"),
                          ("화면 촬영", CAPTURED)], top)
    if top < 47:
        raise AssertionError("Page 1 content exceeds the A4 layout.")
    pdf.showPage()
    top = page_header(pdf, 2)
    top = section_heading(pdf, "② QRnShort — QR 코드 + 단축 URL", top)
    top = paragraph(pdf, "6주차 2교시 QRnShort 만들기", MARGIN, top, CONTENT_W, "small") - 12
    top = linked_url(pdf, "배포 URL — 아래 주소를 클릭하면 QRnShort로 연결됩니다.", QRNSHORT, top)
    top = screenshot_box(pdf, qrnshort_image, top, 340)
    top = facts_box(pdf, [
        ("입력 URL", ORIGINAL),
        ("생성된 단축 URL", validation["short_url"]),
        ("QR 코드 확인", "원본 URL을 QR 코드로 변환하였으며, 내려받은 PNG도 같은 주소로 연결됩니다."),
        ("단축 URL 확인", "새 웹 브라우저에서 원본 홈페이지로 이동하는 것을 확인했습니다."),
    ], top)
    top = linked_url(pdf, "생성된 단축 URL — 클릭하여 원본 홈페이지 연결을 확인할 수 있습니다.",
                     validation["short_url"], top)
    if top < 47:
        raise AssertionError("Page 2 content exceeds the A4 layout.")
    pdf.showPage()
    top = page_header(pdf, 3)
    top = section_heading(pdf, "③ URL2QR 연결 및 동작 확인", top)
    top = paragraph(pdf, "5주차 2교시 URL2QR 웹사이트와 QRnShort의 연결",
                    MARGIN, top, CONTENT_W, "small") - 12
    top = linked_url(pdf, "URL2QR 연결 주소", URL2QR, top)
    top = screenshot_box(pdf, url2qr_image, top, 334)
    top = facts_box(pdf, [
        ("연결 확인", "QRnShort 안의 URL2QR 링크를 눌러 실제 URL2QR 페이지로 이동했습니다."),
        ("URL2QR 확인", "같은 원본 URL을 QR로 변환하고 QR 이미지 및 다운로드 PNG의 주소를 확인했습니다."),
        ("입력 확인", "올바르지 않은 URL을 입력하면 변환을 진행하지 않는 것을 확인했습니다."),
        ("휴대폰 화면", "가로 390px 화면에서 홈페이지·QRnShort·URL2QR의 가로 넘침이 없습니다."),
    ], top)
    top = paragraph(pdf, "확인 환경: " + escape(validation["browser"]) +
                    " / 데스크톱 1440 × 1100 / 휴대폰 390 × 844",
                    MARGIN, top, CONTENT_W, "small")
    if top < 47:
        raise AssertionError("Page 3 content exceeds the A4 layout.")
    pdf.showPage()
    pdf.save()

def verify_pdf():
    reader = PdfReader(str(PDF_PATH))
    check("pdf_three_pages", len(reader.pages) == 3, "PDF must have exactly three pages.")
    for index, page in enumerate(reader.pages, 1):
        check("pdf_page_" + str(index) + "_a4",
              abs(float(page.mediabox.width) - PAGE_W) < 0.2
              and abs(float(page.mediabox.height) - PAGE_H) < 0.2, "PDF page is not A4.")
    uris = []
    for page in reader.pages:
        for annotation_ref in page.get("/Annots", []):
            action = annotation_ref.get_object().get("/A")
            if action and action.get("/S") == "/URI":
                uris.append(str(action.get("/URI")))
    check("pdf_clickable_home_url", HOME in uris, "Homepage URL is not clickable in the PDF.")
    check("pdf_clickable_qrnshort_url", QRNSHORT in uris, "QRnShort URL is not clickable in the PDF.")
    check("pdf_clickable_url2qr_url", URL2QR in uris, "URL2QR URL is not clickable in the PDF.")
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    check("pdf_student_name_present", STUDENT_NAME in text, "Student name is missing in the PDF.")
    check("pdf_student_id_present", STUDENT_ID in text, "Student ID is missing in the PDF.")
    validation["pdf_clickable_urls"] = uris
    validation["pdf_page_count"] = len(reader.pages)

def render_pdf_and_preview():
    document = fitz.open(str(PDF_PATH))
    thumbnails = []
    for index, page in enumerate(document):
        pixmap = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
        render_path = EVIDENCE / ("pdf_page_" + str(index + 1) + ".png")
        pixmap.save(str(render_path))
        image = Image.open(render_path).convert("RGB")
        scale_x, scale_y = image.width / PAGE_W, image.height / PAGE_H
        draw = ImageDraw.Draw(image)
        draw.rectangle((32 * scale_x, 59 * scale_y,
                        (PAGE_W - 32) * scale_x, 81 * scale_y), fill="white")
        image.thumbnail((360, 510), Image.Resampling.LANCZOS)
        thumbnails.append(image)
    sheet_w = sum(item.width for item in thumbnails) + 16 * (len(thumbnails) + 1)
    sheet_h = max(item.height for item in thumbnails) + 32
    sheet = Image.new("RGB", (sheet_w, sheet_h), "#e5eaf1")
    x = 16
    for thumbnail in thumbnails:
        sheet.paste(thumbnail, (x, 16))
        x += thumbnail.width + 16
    jpeg = None
    for quality in (82, 72, 62, 52, 42, 32):
        stream = io.BytesIO()
        sheet.save(stream, format="JPEG", quality=quality, optimize=True)
        jpeg = stream.getvalue()
        if len(jpeg) < 45000:
            break
    (EVIDENCE / "qa_preview_redacted.jpg").write_bytes(jpeg)
    print("QA_PREVIEW_BEGIN" + base64.b64encode(jpeg).decode("ascii") + "QA_PREVIEW_END")
    document.close()

def main():
    images = browser_evidence()
    make_pdf(images)
    verify_pdf()
    render_pdf_and_preview()
    (EVIDENCE / "validation.json").write_text(
        json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Verified live deployment, QR payloads, real short redirect, mobile layout, and 3-page A4 PDF.")
    print("PDF output: " + str(PDF_PATH))

if __name__ == "__main__":
    main()
