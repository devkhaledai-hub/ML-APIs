# Cloud Vision Streamlit Labeler

A simple Streamlit app for working with Google Cloud Storage and Google Cloud
Vision.

The app has three main features:

- Upload an image to a Google Cloud Storage bucket.
- Fetch and preview images already saved in the bucket.
- Label a selected bucket image using Cloud Vision Label Detection.

The Vision API request uses a Cloud Storage image URI like this:

```json
{
  "requests": [
    {
      "image": {
        "source": {
          "imageUri": "gs://bucket_name/path_to_image_object"
        }
      },
      "features": [
        {
          "type": "LABEL_DETECTION",
          "maxResults": 5
        }
      ]
    }
  ]
}
```

## Project Files

```text
.
+-- app.py
+-- requirements.txt
+-- README.md
+-- .env.example
+-- .gitignore
+-- .streamlit/
    +-- secrets.toml.example
```

## Requirements

- Python 3.10 or newer
- A Google Cloud project
- Cloud Storage API enabled
- Cloud Vision API enabled
- A Cloud Storage bucket
- A Google Cloud service account JSON key

## Google Cloud Setup

1. Open Google Cloud Console.
2. Create or choose a project.
3. Enable these APIs:
   - Cloud Storage
   - Cloud Vision API
4. Create a Cloud Storage bucket.
5. Create a service account.
6. Give the service account access to your bucket.

For a lab project, this role is simple:

```text
Storage Object Admin
```

For real production apps, use more restricted permissions.

7. Create a JSON key for the service account:
   - Go to IAM & Admin
   - Open Service Accounts
   - Select your service account
   - Open Keys
   - Add key
   - Create new key
   - Choose JSON

Save the downloaded JSON file somewhere safe.

## Install

Open PowerShell in this project folder:

```powershell
cd "D:\Courses\Google cloud ITI\Session one\ML APIs"
```

Create a virtual environment:

```powershell
python -m venv .venv
```

Install the packages:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Configuration

You can configure the app using `.env` or Streamlit secrets.

### Option 1: `.env`

Copy `.env.example` to `.env`:

```powershell
Copy-Item .env.example .env
```

Then edit `.env`:

```env
GCS_BUCKET_NAME=your-bucket-name
GCS_UPLOAD_PREFIX=streamlit-label-uploads
GOOGLE_CLOUD_PROJECT=your-google-cloud-project-id
GOOGLE_VISION_API_KEY=your-restricted-vision-api-key
GOOGLE_APPLICATION_CREDENTIALS=C:\path\to\service-account.json
```

Important values:

- `GCS_BUCKET_NAME`: your bucket name only, without `gs://`
- `GCS_UPLOAD_PREFIX`: folder/prefix inside the bucket
- `GOOGLE_CLOUD_PROJECT`: your Google Cloud project ID
- `GOOGLE_APPLICATION_CREDENTIALS`: full path to the service account JSON file
- `GOOGLE_VISION_API_KEY`: optional, only needed if you choose API key auth for Vision

### Option 2: Streamlit Secrets

Copy the example secrets file:

```powershell
Copy-Item .streamlit\secrets.toml.example .streamlit\secrets.toml
```

Then edit `.streamlit/secrets.toml`.

You can either keep using `GOOGLE_APPLICATION_CREDENTIALS`, or paste the service
account JSON fields into the `[gcp_service_account]` section in
`.streamlit/secrets.toml`.

Do not commit `.env` or `.streamlit/secrets.toml`.

## Run The App

Start Streamlit:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open the app in your browser:

```text
http://127.0.0.1:8501
```

## How To Use

### 1. Upload Image

1. Open the Upload Image tab.
2. Choose an image from your computer.
3. Click Upload image.
4. The app uploads the file to:

```text
gs://your-bucket-name/streamlit-label-uploads/...
```

The uploaded Cloud Storage URI is shown after upload.

### 2. Fetch Images

1. Open the Fetch Images tab.
2. Click Fetch images.
3. The app lists images from your configured bucket prefix.
4. Select an image.
5. Click Show selected image to preview it from Cloud Storage.

Supported image extensions:

```text
.jpg, .jpeg, .png, .webp, .gif, .bmp, .tiff, .tif
```

### 3. Label Image

1. Open the Label Image tab.
2. Click Refresh bucket images if needed.
3. Choose an image from the dropdown.
4. Click Label selected image.
5. The app fetches the image from Cloud Storage and calls Cloud Vision.

The app displays:

- The selected image
- The best label
- A table of labels, scores, and topicality values

## Auth Modes

The sidebar has a Vision auth setting.

### Service account

Recommended.

This uses your service account credentials to call Vision. It works well with
private bucket images when the service account has permission.

### API key

This uses `GOOGLE_VISION_API_KEY` only for the Vision request.

Important:

- API key auth does not upload images to Cloud Storage.
- Upload and fetch still need service account credentials.
- API key auth can fail if Vision cannot access the Cloud Storage object.

## Troubleshooting

### Missing GCS_BUCKET_NAME

Set this in `.env` or `.streamlit/secrets.toml`:

```env
GCS_BUCKET_NAME=your-bucket-name
```

Do not include `gs://`.

### Could not automatically determine credentials

Check that `GOOGLE_APPLICATION_CREDENTIALS` points to your service account JSON:

```env
GOOGLE_APPLICATION_CREDENTIALS=C:\path\to\service-account.json
```

Also check that the file path exists.

### Permission denied when uploading or fetching

Make sure the service account has access to the bucket. For this lab, give it:

```text
Storage Object Admin
```

### Vision API returns an error

Check these things:

- Cloud Vision API is enabled.
- The image exists in Cloud Storage.
- The service account has permission.
- If using API key mode, the API key is valid and restricted to Vision API.

### No images appear in Fetch Images

Check that:

- The images are inside `GCS_UPLOAD_PREFIX`.
- The files have supported image extensions.
- You are using the correct bucket name.

## Security Notes

- Do not put real API keys directly in `app.py`.
- Do not commit `.env`.
- Do not commit `.streamlit/secrets.toml`.
- Keep your service account JSON file private.
- If an API key is shared publicly, rotate it or restrict it in Google Cloud.

## Dependencies

Main packages:

- `streamlit`
- `google-cloud-storage`
- `google-auth`
- `requests`
- `python-dotenv`

They are listed in `requirements.txt`.
