import asyncio
import json
import os
from nats.aio.client import Client as NATS
import httpx
import uuid
from datetime import datetime, timezone
from cloudevents.http import from_json, to_json, CloudEvent

# Config
NATS_URL = os.getenv("NATS_URL", "nats://127.0.0.1:4222")
NATS_TIMEOUT = int(os.getenv("NATS_TIMEOUT", "5"))
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_API = "https://api.github.com"

NATS_STREAM = "REPOS"
NATS_CONSUMER = "repo_creator"
NATS_USERNAME = os.getenv("NATS_USERNAME")
NATS_PASSWORD = os.getenv("NATS_PASSWORD")

CREATE_SUBJECT = "repo.requested"
RESPONSE_SUBJECT = "repo.created"
ERROR_SUBJECT = "repo.error"

# Graceful shutdown
stop_event = asyncio.Event()

def shutdown():
    stop_event.set()

async def handle_message(msg):
    # Parse message as CloudEvent JSON
    global ce
    ce = from_json(msg.data.decode())
    event_data = ce.data

    org = event_data.get("org")
    name = event_data.get("name")

    if not org or not name:
        print("Invalid CloudEvent data")
        return

    print(f"Creating repo {org}/{name}")
    repo_url = await create_github_repo(org, name)

    return repo_url


# NATS + CloudEvents handler
async def main():
    nc = NATS()
    await nc.connect(servers=[NATS_URL], user=NATS_USERNAME, password=NATS_PASSWORD)

    js = nc.jetstream()

    sub = await js.pull_subscribe(
        subject=CREATE_SUBJECT,
        stream=NATS_STREAM,
    )

    while not stop_event.is_set():
        try:
            msgs = await sub.fetch(timeout=NATS_TIMEOUT)
            if not msgs:
                continue  # Nothing fetched, continue polling

            for msg in msgs:
                print(f"Received message: {msg.data.decode()}")
                repo_url = await handle_message(msg)

                # Prepare CloudEvent response
                response_event = CloudEvent(
                    attributes={
                        "type": "repo.created",
                        "source": "repo.codesalot.com",
                        "id": str(uuid.uuid4()),
                        "time": datetime.now(timezone.utc).isoformat(),
                        "datacontenttype": "application/json",
                        "specversion": "1.0",
                        "subject": ce.get("subject"),
                    },
                    data={
                        "url": repo_url
                    }
                )
                payload = to_json(response_event)
                await js.publish(RESPONSE_SUBJECT, payload)
                print(f"Published repo.created CloudEvent for {repo_url}")

        except asyncio.TimeoutError:
            print("Timeout reached, continuing fetch loop...")
        except httpx.HTTPStatusError as e:
            error_message = f"Failed to create repo: {e.response.text}"
            print(error_message)
            if e.response.status_code == 422:
                error_message = "Repository already exists or invalid request"
            else:
                await publish_error_event(js, ERROR_SUBJECT, error_message)
                return
        except Exception as e:
            print(f"Unexpected error during message fetch: {e}")
            break

async def publish_error_event(js, ce_subject, error_message):
    error_event = CloudEvent(
        attributes={
            "type": "repo.error",
            "source": "repo.codesalot.com",
            "id": str(uuid.uuid4()),
            "time": datetime.now(timezone.utc).isoformat(),
            "datacontenttype": "application/json",
            "specversion": "1.0",
            "subject": ce_subject,
        },
        data={"error": error_message}
    )
    payload = to_json(error_event)
    await js.publish(ERROR_SUBJECT, payload)
    print(f"Published error event: {error_message}")

# GitHub repo creation logic
async def create_github_repo(org, repo_name):
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    url = f"{GITHUB_API}/orgs/{org}/repos"
    payload = {
        "name": repo_name,
        "private": False
    }

    async with httpx.AsyncClient() as client:
        r = await client.post(url, json=payload, headers=headers)
        r.raise_for_status()
        return r.json()["html_url"]


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Shutting down.")
