from __future__ import annotations

import os
import re
import time
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any

import google.auth
import requests
import streamlit as st
from google.auth.transport.requests import AuthorizedSession
from google.cloud import storage
from google.oauth2 import service_account

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


VISION_ENDPOINT = "https://vision.googleapis.com/v1/images:annotate"
CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
DEFAULT_PREFIX = "streamlit-label-uploads"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff", ".tif"}


def get_setting(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name)
    except Exception:
        value = None

    if value is None:
        value = os.getenv(name, default)

    return str(value).strip() if value is not None else default


def get_service_account_info() -> dict[str, Any] | None:
    try:
        raw_info = st.secrets.get("gcp_service_account")
    except Exception:
        raw_info = None

    if not raw_info:
        return None

    info = dict(raw_info)
    if "private_key" in info:
        info["private_key"] = str(info["private_key"]).replace("\\n", "\n")
    return info


def get_credentials():
    service_account_info = get_service_account_info()
    if service_account_info:
        return service_account.Credentials.from_service_account_info(
            service_account_info,
            scopes=[CLOUD_PLATFORM_SCOPE],
        )

    credentials, _ = google.auth.default(scopes=[CLOUD_PLATFORM_SCOPE])
    return credentials


def get_storage_client(credentials) -> storage.Client:
    project_id = get_setting("GOOGLE_CLOUD_PROJECT")
    if not project_id and getattr(credentials, "project_id", None):
        project_id = credentials.project_id

    return storage.Client(project=project_id or None, credentials=credentials)


def clean_object_name(filename: str) -> str:
    path = Path(filename)
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", path.stem).strip(".-")
    suffix = path.suffix.lower()

    if not stem:
        stem = "image"
    if suffix not in IMAGE_EXTENSIONS:
        suffix = ".jpg"

    return f"{stem[:80]}{suffix}"


def upload_image(
    image_bytes: bytes,
    filename: str,
    content_type: str,
    bucket_name: str,
    prefix: str,
    credentials,
) -> str:
    safe_name = clean_object_name(filename)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    object_prefix = prefix.strip("/") or DEFAULT_PREFIX
    object_name = f"{object_prefix}/{timestamp}-{uuid.uuid4().hex[:8]}-{safe_name}"

    client = get_storage_client(credentials)
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(object_name)
    blob.upload_from_file(BytesIO(image_bytes), content_type=content_type)

    return f"gs://{bucket_name}/{object_name}"


def split_gcs_uri(gcs_uri: str) -> tuple[str, str]:
    if not gcs_uri.startswith("gs://"):
        raise ValueError("Cloud Storage image must start with gs://")

    path = gcs_uri[5:]
    bucket_name, separator, object_name = path.partition("/")
    if not bucket_name or not separator or not object_name:
        raise ValueError("Use this format: gs://bucket-name/path/to/image.jpg")

    return bucket_name, object_name


def download_image(gcs_uri: str, credentials) -> bytes:
    bucket_name, object_name = split_gcs_uri(gcs_uri)
    client = get_storage_client(credentials)
    blob = client.bucket(bucket_name).blob(object_name)
    return blob.download_as_bytes()


def list_bucket_images(
    bucket_name: str,
    prefix: str,
    credentials,
    limit: int = 100,
) -> list[str]:
    object_prefix = prefix.strip("/")
    client = get_storage_client(credentials)
    blobs = client.list_blobs(
        bucket_name,
        prefix=f"{object_prefix}/" if object_prefix else None,
        max_results=limit,
    )

    image_uris = []
    for blob in blobs:
        suffix = Path(blob.name).suffix.lower()
        if blob.name.endswith("/") or suffix not in IMAGE_EXTENSIONS:
            continue
        image_uris.append(f"gs://{bucket_name}/{blob.name}")

    return image_uris


def display_name_for_gcs_uri(gcs_uri: str) -> str:
    _, object_name = split_gcs_uri(gcs_uri)
    return object_name


def build_vision_request(gcs_uri: str, max_results: int) -> dict[str, Any]:
    return {
        "requests": [
            {
                "image": {
                    "source": {
                        "imageUri": gcs_uri,
                    },
                },
                "features": [
                    {
                        "type": "LABEL_DETECTION",
                        "maxResults": max_results,
                    },
                ],
            },
        ],
    }


def parse_labels(response_json: dict[str, Any]) -> list[dict[str, Any]]:
    responses = response_json.get("responses", [])
    if not responses:
        raise RuntimeError("Vision API returned no responses.")

    first_response = responses[0]
    if "error" in first_response:
        message = first_response["error"].get("message", "Unknown Vision API error")
        raise RuntimeError(message)

    return first_response.get("labelAnnotations", [])


def label_with_api_key(api_key: str, gcs_uri: str, max_results: int) -> list[dict[str, Any]]:
    response = requests.post(
        VISION_ENDPOINT,
        params={"key": api_key},
        json=build_vision_request(gcs_uri, max_results),
        timeout=30,
    )
    response.raise_for_status()
    return parse_labels(response.json())


def label_with_service_account(credentials, gcs_uri: str, max_results: int) -> list[dict[str, Any]]:
    session = AuthorizedSession(credentials)
    response = session.post(
        VISION_ENDPOINT,
        json=build_vision_request(gcs_uri, max_results),
        timeout=30,
    )
    response.raise_for_status()
    return parse_labels(response.json())


def label_image(
    auth_method: str,
    api_key: str,
    credentials,
    gcs_uri: str,
    max_results: int,
) -> list[dict[str, Any]]:
    if auth_method == "API key":
        return label_with_api_key(api_key, gcs_uri, max_results)
    return label_with_service_account(credentials, gcs_uri, max_results)


def show_labels(labels: list[dict[str, Any]]) -> None:
    if not labels:
        st.warning("No labels were returned for this image.")
        return

    best = labels[0]
    st.success(f"Best label: {best.get('description', 'Unknown')}")

    rows = [
        {
            "label": label.get("description", ""),
            "score": round(float(label.get("score", 0)) * 100, 2),
            "topicality": round(float(label.get("topicality", 0)) * 100, 2),
        }
        for label in labels
    ]
    st.dataframe(rows, hide_index=True, use_container_width=True)


def render_upload_tab(bucket_name: str, upload_prefix: str) -> None:
    uploaded_file = st.file_uploader(
        "Image",
        type=["jpg", "jpeg", "png", "webp", "gif", "bmp", "tiff"],
        key="upload_image_file",
    )

    if uploaded_file is not None:
        image_bytes = uploaded_file.getvalue()
        content_type = uploaded_file.type or "application/octet-stream"
        st.image(image_bytes, caption="Selected image", use_container_width=True)
    else:
        image_bytes = b""
        content_type = "application/octet-stream"

    clicked = st.button(
        "Upload image",
        type="primary",
        disabled=uploaded_file is None,
    )
    if not clicked:
        return

    try:
        with st.status("Uploading image to Cloud Storage...", expanded=True) as status:
            credentials = get_credentials()
            gcs_uri = upload_image(
                image_bytes=image_bytes,
                filename=uploaded_file.name,
                content_type=content_type,
                bucket_name=bucket_name,
                prefix=upload_prefix,
                credentials=credentials,
            )
            status.update(label="Upload complete", state="complete")

        st.session_state["last_uploaded_uri"] = gcs_uri
        st.success("Image uploaded to Cloud Storage.")
        st.code(gcs_uri)
    except Exception as exc:
        st.error(str(exc))


def render_fetch_tab(bucket_name: str, upload_prefix: str) -> None:
    if st.button("Fetch images", type="primary"):
        try:
            with st.status("Fetching images from Cloud Storage...", expanded=True) as status:
                credentials = get_credentials()
                st.session_state["bucket_images"] = list_bucket_images(
                    bucket_name=bucket_name,
                    prefix=upload_prefix,
                    credentials=credentials,
                )
                status.update(label="Fetch complete", state="complete")
        except Exception as exc:
            st.error(str(exc))
            return

    image_uris = st.session_state.get("bucket_images", [])
    if not image_uris:
        st.info("Click Fetch images to load images from your bucket.")
        return

    st.success(f"Found {len(image_uris)} image(s).")
    selected_uri = st.selectbox(
        "Fetched images",
        options=image_uris,
        format_func=display_name_for_gcs_uri,
        key="fetch_image_select",
    )

    if st.button("Show selected image"):
        try:
            credentials = get_credentials()
            image_bytes = download_image(selected_uri, credentials)
            st.image(image_bytes, caption=display_name_for_gcs_uri(selected_uri), use_container_width=True)
        except Exception as exc:
            st.error(str(exc))


def render_label_tab(
    bucket_name: str,
    upload_prefix: str,
    auth_method: str,
    api_key: str,
    max_results: int,
) -> None:
    refresh_clicked = st.button("Refresh bucket images")
    if refresh_clicked:
        try:
            with st.status("Fetching images from Cloud Storage...", expanded=True) as status:
                credentials = get_credentials()
                st.session_state["bucket_images"] = list_bucket_images(
                    bucket_name=bucket_name,
                    prefix=upload_prefix,
                    credentials=credentials,
                )
                status.update(label="Fetch complete", state="complete")
        except Exception as exc:
            st.error(str(exc))
            return

    image_uris = list(st.session_state.get("bucket_images", []))
    last_uploaded_uri = st.session_state.get("last_uploaded_uri")
    if last_uploaded_uri and last_uploaded_uri not in image_uris:
        image_uris.insert(0, last_uploaded_uri)

    if not image_uris:
        st.info("Upload an image or refresh bucket images first.")
        return

    selected_uri = st.selectbox(
        "Image to label",
        options=image_uris,
        format_func=display_name_for_gcs_uri,
        key="label_image_select",
    )

    if not st.button("Label selected image", type="primary"):
        return

    if auth_method == "API key" and not api_key:
        st.error("Missing GOOGLE_VISION_API_KEY.")
        return

    try:
        with st.status("Labeling image...", expanded=True) as status:
            credentials = get_credentials()
            status.update(label="Fetching image from Cloud Storage...", state="running")
            image_bytes = download_image(selected_uri, credentials)

            status.update(label="Calling Cloud Vision...", state="running")
            labels = label_image(auth_method, api_key, credentials, selected_uri, max_results)
            status.update(label="Done", state="complete")

        st.image(image_bytes, caption=display_name_for_gcs_uri(selected_uri), use_container_width=True)
        show_labels(labels)
    except Exception as exc:
        st.error(str(exc))


def main() -> None:
    st.set_page_config(page_title="Cloud Vision Labeler")

    st.title("Cloud Vision Labeler")

    with st.sidebar:
        st.header("Google Cloud")
        bucket_name = get_setting("GCS_BUCKET_NAME")
        upload_prefix = get_setting("GCS_UPLOAD_PREFIX", DEFAULT_PREFIX)
        api_key = get_setting("GOOGLE_VISION_API_KEY")
        max_results = st.slider("Max labels", min_value=1, max_value=10, value=5)
        auth_method = st.radio(
            "Vision auth",
            options=("Service account", "API key"),
            help="Use service account for private buckets. API key works best when Vision can read the GCS object.",
        )

        if bucket_name:
            st.caption(f"Bucket: gs://{bucket_name}")
        else:
            st.warning("Set GCS_BUCKET_NAME in Streamlit secrets or .env.")

    if not bucket_name:
        st.error("Missing GCS_BUCKET_NAME.")
        return

    upload_tab, fetch_tab, label_tab = st.tabs(
        ["Upload Image", "Fetch Images", "Label Image"]
    )

    with upload_tab:
        render_upload_tab(bucket_name, upload_prefix)

    with fetch_tab:
        render_fetch_tab(bucket_name, upload_prefix)

    with label_tab:
        render_label_tab(bucket_name, upload_prefix, auth_method, api_key, max_results)


if __name__ == "__main__":
    main()
