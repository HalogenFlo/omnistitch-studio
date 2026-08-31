# REST API

The server listens on `http://127.0.0.1:5000` by default. Set `HOST` or `PORT` before launch to override this. An installed wheel stores writable data under `~/.omnistitch-studio`; set `OMNISTITCH_WORKSPACE_DIR` to select another location. The API has no authentication and is intended for local use, not direct exposure to an untrusted network.

## Health

```http
GET /api/health
```

Returns `200` with service status and memory information.

## Scan a Folder

```http
POST /api/scan_folder
Content-Type: application/json

{"folderPath":"sample_data/demo_slide"}
```

Returns discovered image paths and folder metadata. Paths are constrained to permitted workspace locations.

## Start Automatic Stitching

```http
POST /api/stitch/auto
Content-Type: application/json

{
  "images":["sample_data/demo_slide/tile_00.png","sample_data/demo_slide/tile_01.png"],
  "folderName":"example",
  "featureMethod":"sift",
  "motionModel":"affine",
  "backgroundMode":"white",
  "autoCrop":true
}
```

The operation runs in the background. Poll `GET /api/stitch/status` for progress and errors.

## Projects

`GET /api/projects/{id}` loads project state. `PUT /api/projects/{id}` validates and saves project state using revision-aware persistence. A stale revision returns a conflict response rather than overwriting newer state.

`POST /api/projects/{id}/inspect` accepts a rectangle or polygon in world coordinates and returns overlapping source candidates with coverage and clarity scores.

`POST /api/projects/{id}/exports` exports the current project using the requested `exportFormat` and `backgroundMode`.

## Limits and Errors

- JSON requests are limited to 4 MiB.
- Upload requests are limited to 256 MiB and decoded upload content to 128 MiB.
- Invalid input returns `400`, disallowed paths return `403`, oversized requests return `413`, and stale project revisions return `409`.
- Error responses are JSON where handled by an API endpoint; unknown routes use an HTTP error response.
