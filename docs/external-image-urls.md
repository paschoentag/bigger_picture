# Linking Images from External Brokers (osis.geomar.de)

Instead of uploading and storing images locally on the OpenShift backend, you can link images from an external image broker like `https://osis.geomar.de/images/broker/`.

## How it works

- **No local storage**: Image files are never downloaded or stored on the backend server
- **Direct serving**: The image URL is stored in the database and served directly from the broker to the browser
- **Transparent to frontend**: The game client doesn't know or care whether images are local or external

## Using the API

### Create an image from an external URL

**Endpoint**: `POST /api/v1/dataset/images/create-from-url`

**Request**:
```json
{
  "uuid": "8f8b65dc-fbf2-4dfb-bff2-f34072bb97e2",
  "filename": "frame_0001.jpg",
  "filepath": "https://osis.geomar.de/images/broker/abc123def456",
  "dive_uuid": "1a6ccf07-c766-4934-a6a5-0ca6dbdb5a0b",
  "size_x": 1920,
  "size_y": 1080,
  "metadata": null,
  "difficulty": null,
  "priority": null
}
```

**Parameters**:
- `uuid`: Unique identifier for the image (required)
- `filename`: Display name (required)
- `filepath`: Full external URL starting with `http://` or `https://` (required)
- `dive_uuid`: Dive this image belongs to (required)
- `size_x`, `size_y`: Image dimensions in pixels (optional)
  - If omitted, the backend will fetch the image from the URL to read dimensions (slower)
  - **Recommended**: provide them explicitly for better performance
- `metadata`, `difficulty`, `priority`: Optional image metadata

**Response**: Standard `ImageResponse` with the created image details

## Example: Python script to import from osis.geomar.de

```python
import requests
from uuid import uuid4

BASE_URL = "http://localhost:8000"  # or your OpenShift backend URL
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "change-me-please"

# Login as admin
response = requests.post(
    f"{BASE_URL}/api/v1/auth/login",
    json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
    cookies={}
)
session_cookie = response.cookies.get("session_uuid")

# Get CSRF token
response = requests.get(
    f"{BASE_URL}/api/v1/auth/me",
    cookies={"session_uuid": session_cookie}
)
csrf_token = response.cookies.get("csrf_token")

# Create image from external broker URL
response = requests.post(
    f"{BASE_URL}/api/v1/dataset/images/create-from-url",
    json={
        "uuid": str(uuid4()),
        "filename": "frame_0001.jpg",
        "filepath": "https://osis.geomar.de/images/broker/your-image-id",
        "dive_uuid": "your-dive-uuid-here",
        "size_x": 1920,  # Provide to avoid remote fetch
        "size_y": 1080,
    },
    cookies={"session_uuid": session_cookie},
    headers={"X-CSRF-Token": csrf_token}
)

print(response.json())
```

## Mixing local and external images

The backend supports both local and external images in the same dive:
- Local uploads use relative paths like `dive-uuid/image.jpg`
- External broker images use full URLs like `https://osis.geomar.de/images/broker/...`
- The frontend automatically detects which is which via `assetUrl()`

## Performance notes

- **With dimensions provided**: Fast — only one DB write
- **Without dimensions**: Slower — backend downloads image from broker to read dimensions, then discards it
- **Frontend rendering**: Direct image loading from broker (no backend proxy/relay)
- **Broker availability**: Images are live as long as the broker is accessible. If the broker goes down, those images won't load in the game

## Troubleshooting

- **"filepath must be a full http(s) URL"** → The URL must start with `http://` or `https://`
- **"Could not fetch image dimensions from URL"** → Either provide `size_x` and `size_y` explicitly, or ensure the broker URL is publicly accessible
- **Image won't load in game** → Check that the broker URL is accessible from the browser (check browser console for CORS errors)

