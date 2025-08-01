#! /bin/sh
ID=$(date +%s)

CLOUDEVENT_JSON=$(cat <<EOF
{
  "specversion": "1.0",
  "type": "repo.requested",
  "source": "repo.codesalot.com",
  "id": "$ID",
  "subject": "open-garlic-this-repo",
  "datacontenttype": "application/json",
  "data": {
    "org": "open-garlic",
    "name": "this-repo"
  }
}
EOF
)
# Send the CloudEvent to the NATS server
nats pub "repo.requested" "$CLOUDEVENT_JSON"
