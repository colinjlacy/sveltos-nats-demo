#! /bin/sh
ID=$(date +%s)

CLOUDEVENT_JSON=$(cat <<EOF
{
  "specversion": "1.0",
  "type": "repo.error",
  "source": "repo.codesalot.com",
  "id": "$ID",
  "subject": "microsoft-that-repo",
  "datacontenttype": "application/json",
  "data": {
    "org": "microsoft",
    "name": "that-repo"
  }
}
EOF
)
# Send the CloudEvent to the NATS server
nats pub "repo.error" "$CLOUDEVENT_JSON"
