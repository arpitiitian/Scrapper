import json
import html
import re
import base64
import requests
from pathlib import Path
from urllib.parse import urlparse, urljoin
from datetime import datetime, timezone
import unicodedata
import time


ALLOWED_HOST = "quizpractice.space"
DEFAULT_CDN = "https://saram.blr1.cdn.digitaloceanspaces.com"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/154.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}


# ==========================================================
# BASIC HELPERS
# ==========================================================

def safe_name(value, fallback="Untitled"):
    value = str(value or "").strip()
    value = unicodedata.normalize("NFKC", value)

    value = re.sub(
        r'[<>:"/\\|?*\x00-\x1F]',
        "_",
        value
    )

    value = re.sub(r"\s+", " ", value)
    value = value.strip(" .")

    return value[:120] or fallback


def validate_url(url):
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise ValueError("Sirf http/https URL allowed hai.")

    host = (parsed.hostname or "").lower()

    if host != ALLOWED_HOST and not host.endswith("." + ALLOWED_HOST):
        raise ValueError(
            f"Abhi sirf {ALLOWED_HOST} ki pages scrape karne ke liye configured hai."
        )


# ==========================================================
# INERTIA DATA EXTRACTION
# ==========================================================

def extract_data_page(page):

    patterns = [
        r'<div[^>]*\bid=["\']app["\'][^>]*\bdata-page=["\']([^"\']+)["\']',
        r'<div[^>]*\bdata-page=["\']([^"\']+)["\'][^>]*\bid=["\']app["\']',
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            page,
            flags=re.IGNORECASE
        )

        if match:

            encoded = match.group(1)

            decoded = html.unescape(encoded)

            return json.loads(decoded)

    raise ValueError(
        "Page ke HTML me Inertia data-page nahi mila."
    )


# ==========================================================
# IMAGE URL
# ==========================================================

def make_image_url(image_path, cdn_base):

    if not image_path:
        return None

    image_path = str(image_path).strip()

    if image_path.startswith("http://"):
        return image_path

    if image_path.startswith("https://"):
        return image_path

    return urljoin(
        cdn_base.rstrip("/") + "/",
        image_path.lstrip("/")
    )


def extension_from_response(response, url):

    content_type = (
        response.headers.get("content-type") or ""
    ).lower()

    mapping = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "image/svg+xml": ".svg",
    }

    for mime, ext in mapping.items():

        if mime in content_type:
            return ext

    ext = Path(
        urlparse(url).path
    ).suffix.lower()

    if ext in (
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".gif",
        ".svg",
    ):

        return ".jpg" if ext == ".jpeg" else ext

    return ".png"


# ==========================================================
# NORMAL IMAGE DOWNLOAD
# ==========================================================

def download_image(
    session,
    image_path,
    output_without_extension,
    cdn_base,
    referer=None
):

    url = make_image_url(
        image_path,
        cdn_base
    )

    if not url:
        return None, False

    headers = {
        "User-Agent": HEADERS["User-Agent"],
        "Accept": (
            "image/avif,image/webp,image/apng,"
            "image/svg+xml,image/*,*/*;q=0.8"
        ),
        "Referer": (
            referer
            or "https://quizpractice.space/"
        ),
        "Origin": "https://quizpractice.space",
    }

    try:

        response = session.get(
            url,
            headers=headers,
            timeout=30
        )

        response.raise_for_status()

        ext = extension_from_response(
            response,
            url
        )

        output_path = Path(
            str(output_without_extension) + ext
        )

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        output_path.write_bytes(
            response.content
        )

        print(
            "IMAGE DOWNLOADED:",
            url
        )

        return output_path, True

    except requests.RequestException as e:

        print(
            "IMAGE DOWNLOAD FAILED:",
            url
        )

        print(
            "Reason:",
            e
        )

        return None, False


# ==========================================================
# INLINE BASE64 IMAGE
# ==========================================================

def save_inline_images(
    option_html,
    output_dir,
    question_number,
    option_number
):

    if not option_html:
        return [], ""

    option_html = html.unescape(
        str(option_html)
    )

    pattern = (
        r'<img[^>]+src\s*=\s*["\']'
        r'(data:image/[^"\']+)'
        r'["\'][^>]*>'
    )

    matches = re.findall(
        pattern,
        option_html,
        flags=re.IGNORECASE
    )

    local_images = []

    for image_index, data_uri in enumerate(
        matches,
        start=1
    ):

        try:

            header, encoded_data = data_uri.split(
                ",",
                1
            )

            mime_match = re.search(
                r"data:image/([^;]+)",
                header,
                flags=re.IGNORECASE
            )

            if mime_match:

                extension = (
                    "." +
                    mime_match.group(1).lower()
                )

            else:

                extension = ".png"

            if extension == ".jpeg":
                extension = ".jpg"

            filename = (
                f"q{question_number}"
                f"_option{option_number}"
            )

            if len(matches) > 1:

                filename += (
                    f"_{image_index}"
                )

            output_path = (
                output_dir /
                f"{filename}{extension}"
            )

            image_bytes = base64.b64decode(
                encoded_data
            )

            output_path.write_bytes(
                image_bytes
            )

            local_images.append(
                str(
                    Path("images") /
                    "options" /
                    output_path.name
                ).replace("\\", "/")
            )

        except Exception as e:

            print(
                f"INLINE IMAGE FAILED "
                f"Q{question_number} "
                f"Option {option_number}: {e}"
            )

    # img tags remove
    clean_text = re.sub(
        r"<img[^>]*>",
        "",
        option_html,
        flags=re.IGNORECASE
    )

    # remaining HTML remove
    clean_text = re.sub(
        r"<[^>]+>",
        "",
        clean_text
    )

    clean_text = html.unescape(
        clean_text
    ).strip()

    return local_images, clean_text


# ==========================================================
# SELENIUM FALLBACK
#
# CDN agar Python ko 403 de raha hai,
# Chrome browser se image response capture karenge.
# ==========================================================

def browser_download_images(
    page_url,
    image_urls,
    output_map
):

    if not image_urls:
        return {}

    try:

        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options

    except ImportError:

        print()
        print(
            "Selenium installed nahi hai."
        )
        print(
            "Run: pip install selenium"
        )
        print()

        return {}

    print()
    print(
        "Opening Chrome fallback for "
        f"{len(image_urls)} images..."
    )

    options = Options()

    options.add_argument(
        "--headless=new"
    )

    options.add_argument(
        "--disable-gpu"
    )

    options.add_argument(
        "--no-sandbox"
    )

    options.add_argument(
        "--disable-dev-shm-usage"
    )

    options.add_argument(
        "--window-size=1920,1080"
    )

    options.set_capability(
        "goog:loggingPrefs",
        {
            "performance": "ALL"
        }
    )

    driver = None

    results = {}

    try:

        driver = webdriver.Chrome(
            options=options
        )

        driver.execute_cdp_cmd(
            "Network.enable",
            {}
        )

        driver.get(page_url)

        time.sleep(3)

        # Page ko scroll karenge taaki lazy images load ho sakein.
        for _ in range(8):

            driver.execute_script(
                """
                window.scrollTo(
                    0,
                    document.body.scrollHeight
                );
                """
            )

            time.sleep(0.5)

        # Network logs
        logs = driver.get_log(
            "performance"
        )

        image_requests = {}

        for entry in logs:

            try:

                message = json.loads(
                    entry["message"]
                )["message"]

                if (
                    message.get("method")
                    != "Network.responseReceived"
                ):
                    continue

                params = message.get(
                    "params",
                    {}
                )

                response = params.get(
                    "response",
                    {}
                )

                resource_type = params.get(
                    "type"
                )

                response_url = response.get(
                    "url"
                )

                if (
                    resource_type == "Image"
                    and response_url
                ):

                    image_requests[
                        response_url
                    ] = params.get(
                        "requestId"
                    )

            except Exception:
                continue

        for image_url in image_urls:

            request_id = image_requests.get(
                image_url
            )

            if not request_id:

                # URL matching fallback
                for loaded_url, rid in image_requests.items():

                    if (
                        loaded_url.rstrip("/")
                        ==
                        image_url.rstrip("/")
                    ):

                        request_id = rid
                        break

            if not request_id:

                print(
                    "BROWSER IMAGE NOT FOUND:",
                    image_url
                )

                continue

            try:

                body_data = driver.execute_cdp_cmd(
                    "Network.getResponseBody",
                    {
                        "requestId": request_id
                    }
                )

                body = body_data.get(
                    "body"
                )

                if not body:
                    continue

                if body_data.get(
                    "base64Encoded"
                ):

                    raw = base64.b64decode(
                        body
                    )

                else:

                    raw = body.encode(
                        "utf-8"
                    )

                output_without_extension = (
                    output_map[image_url]
                )

                # Usually PNG.
                extension = ".png"

                content_type = ""

                # Try URL extension first
                url_ext = Path(
                    urlparse(image_url).path
                ).suffix.lower()

                if url_ext in (
                    ".jpg",
                    ".jpeg",
                    ".png",
                    ".webp",
                    ".gif",
                ):

                    extension = (
                        ".jpg"
                        if url_ext == ".jpeg"
                        else url_ext
                    )

                output_path = Path(
                    str(
                        output_without_extension
                    ) + extension
                )

                output_path.parent.mkdir(
                    parents=True,
                    exist_ok=True
                )

                output_path.write_bytes(
                    raw
                )

                results[
                    image_url
                ] = output_path

                print(
                    "BROWSER IMAGE SAVED:",
                    output_path
                )

            except Exception as e:

                print(
                    "BROWSER IMAGE FAILED:",
                    image_url
                )

                print(
                    "Reason:",
                    e
                )

    except Exception as e:

        print(
            "Chrome fallback failed:",
            e
        )

        print(
            "Try: pip install selenium"
        )

    finally:

        if driver:

            try:
                driver.quit()
            except Exception:
                pass

    return results


# ==========================================================
# MAIN SCRAPER
# ==========================================================

def scrape_paper(
    url,
    subject,
    data_dir
):

    validate_url(url)

    session = requests.Session()

    session.headers.update(
        HEADERS
    )

    print()
    print(
        "Fetching:",
        url
    )

    response = session.get(
        url,
        timeout=30
    )

    response.raise_for_status()

    data = extract_data_page(
        response.text
    )

    props = data.get(
        "props",
        {}
    )

    paper = props.get(
        "question_paper"
    )

    if not paper:

        raise ValueError(
            "question_paper data nahi mila."
        )

    paper_name = (
        paper.get(
            "question_paper_name"
        )
        or paper.get("name")
        or "Untitled Paper"
    )

    subject_name = safe_name(
        subject,
        "Other"
    )

    paper_folder_name = safe_name(
        paper_name,
        "Untitled Paper"
    )

    paper_dir = (
        Path(data_dir)
        / subject_name
        / paper_folder_name
    )

    question_images_dir = (
        paper_dir
        / "images"
        / "questions"
    )

    option_images_dir = (
        paper_dir
        / "images"
        / "options"
    )

    question_images_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    option_images_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    cdn_base = (
        props.get("file_url")
        or DEFAULT_CDN
    )

    questions = []

    images_downloaded = 0
    images_failed = 0

    # ======================================================
    # Browser fallback queue
    # ======================================================

    browser_urls = []
    browser_output_map = {}

    # ======================================================
    # QUESTIONS
    # ======================================================

    for index, q in enumerate(
        paper.get("questions", []),
        start=1
    ):

        question_number = (
            q.get("question_number")
            or index
        )

        # --------------------------------------------------
        # Question text
        # --------------------------------------------------

        question_texts = q.get(
            "question_texts"
        )

        if isinstance(
            question_texts,
            list
        ):

            question_text = "\n".join(
                str(x)
                for x in question_texts
                if x is not None
            )

        else:

            question_text = (
                q.get(
                    "question_text_1"
                )
                or ""
            )

        # --------------------------------------------------
        # Question images
        # --------------------------------------------------

        question_images = (
            q.get(
                "question_image_url"
            )
            or []
        )

        local_question_images = []

        for image_index, image_path in enumerate(
            question_images,
            start=1
        ):

            filename = (
                f"q{question_number}"
                f"_{image_index}"
            )

            output = (
                question_images_dir /
                filename
            )

            local_path, success = (
                download_image(
                    session,
                    image_path,
                    output,
                    cdn_base,
                    referer=url
                )
            )

            if success and local_path:

                images_downloaded += 1

                local_question_images.append(
                    str(
                        Path("images")
                        / "questions"
                        / local_path.name
                    ).replace(
                        "\\",
                        "/"
                    )
                )

            else:

                images_failed += 1

        # ==================================================
        # OPTIONS
        # ==================================================

        options = []

        for option_index, opt in enumerate(
            q.get("options", []),
            start=1
        ):

            raw_option_text = (
                opt.get(
                    "option_text"
                )
                or ""
            )

            # ------------------------------------------------
            # Inline Base64 images
            # ------------------------------------------------

            inline_images, clean_option_text = (
                save_inline_images(
                    raw_option_text,
                    option_images_dir,
                    question_number,
                    option_index
                )
            )

            images_downloaded += len(
                inline_images
            )

            # ------------------------------------------------
            # Normal option image URL
            # ------------------------------------------------

            image_path = (
                opt.get(
                    "option_image_url"
                )
            )

            local_image = None

            if image_path:

                image_url = make_image_url(
                    image_path,
                    cdn_base
                )

                filename = (
                    f"q{question_number}"
                    f"_option{option_index}"
                )

                output = (
                    option_images_dir
                    / filename
                )

                local_path, success = (
                    download_image(
                        session,
                        image_path,
                        output,
                        cdn_base,
                        referer=url
                    )
                )

                if success and local_path:

                    images_downloaded += 1

                    local_image = str(
                        Path("images")
                        / "options"
                        / local_path.name
                    ).replace(
                        "\\",
                        "/"
                    )

                else:

                    images_failed += 1

                    # ========================================
                    # 403 fallback
                    # ========================================

                    if image_url:

                        browser_urls.append(
                            image_url
                        )

                        browser_output_map[
                            image_url
                        ] = output

            # ------------------------------------------------
            # Inline image ko priority
            # ------------------------------------------------

            if inline_images:

                local_image = (
                    inline_images[0]
                )

            options.append(
                {
                    "text": clean_option_text,
                    "image": image_path,
                    "local_image": local_image,
                    "inline_images": inline_images,
                    "correct": bool(
                        opt.get(
                            "is_correct",
                            0
                        )
                    )
                }
            )

        # ==================================================
        # QUESTION OBJECT
        # ==================================================

        questions.append(
            {
                "question_id": q.get(
                    "id"
                ),

                "question_number":
                    question_number,

                "uuid": q.get(
                    "uuid"
                ),

                "type": q.get(
                    "question_type"
                ),

                "question":
                    question_text,

                "question_images":
                    question_images,

                "local_question_images":
                    local_question_images,

                "options":
                    options,

                "total_mark":
                    q.get(
                        "total_mark"
                    ),

                "answer_type":
                    q.get(
                        "answer_type"
                    ),

                "response_type":
                    q.get(
                        "response_type"
                    ),
            }
        )

    # ======================================================
    # BROWSER FALLBACK
    # ======================================================

    unique_browser_urls = list(
        dict.fromkeys(
            browser_urls
        )
    )

    if unique_browser_urls:

        print()
        print(
            "Python se kuch images download nahi hui."
        )

        print(
            "Browser fallback start ho raha hai..."
        )

        browser_results = (
            browser_download_images(
                url,
                unique_browser_urls,
                browser_output_map
            )
        )

        # --------------------------------------------------
        # JSON options update
        # --------------------------------------------------

        for q in questions:

            for option in q["options"]:

                original_image = (
                    option.get("image")
                )

                if not original_image:
                    continue

                image_url = make_image_url(
                    original_image,
                    cdn_base
                )

                if image_url in browser_results:

                    local_path = (
                        browser_results[
                            image_url
                        ]
                    )

                    option["local_image"] = str(
                        Path("images")
                        / "options"
                        / local_path.name
                    ).replace(
                        "\\",
                        "/"
                    )

                    images_downloaded += 1

                    images_failed -= 1

    # ======================================================
    # FINAL JSON
    # ======================================================

    exam = paper.get(
        "exam"
    )

    if isinstance(
        exam,
        dict
    ):

        exam = exam.get(
            "exam_name"
        )

    course = paper.get(
        "course"
    )

    if isinstance(
        course,
        dict
    ):

        course = course.get(
            "course_name"
        )

    output = {

        "paper": {

            "id":
                paper.get("id"),

            "name":
                paper_name,

            "description":
                paper.get(
                    "question_paper_description"
                ),

            "uuid":
                paper.get("uuid"),

            "year":
                paper.get("year"),

            "source":
                paper.get("source"),

            "exam":
                exam,

            "course":
                course,

            "subject":
                subject_name,

            "source_url":
                url,

            "scraped_at":
                datetime.now(
                    timezone.utc
                ).isoformat(),
        },

        "questions":
            questions,
    }

    json_path = (
        paper_dir
        / "questions.json"
    )

    with open(
        json_path,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            output,
            f,
            ensure_ascii=False,
            indent=2
        )

    print()
    print("=" * 55)
    print("SCRAPING COMPLETE")
    print(
        "Paper:",
        paper_name
    )
    print(
        "Questions:",
        len(questions)
    )
    print(
        "Images:",
        images_downloaded
    )
    print(
        "Failed:",
        max(images_failed, 0)
    )
    print(
        "Folder:",
        paper_dir
    )
    print("=" * 55)

    return {

        "subject":
            subject_name,

        "paper":
            paper_name,

        "questions":
            len(questions),

        "folder":
            str(paper_dir),

        "images_downloaded":
            images_downloaded,

        "images_failed":
            max(images_failed, 0),
    }