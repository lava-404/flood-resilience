"""Storage / queue ports. Local + in-memory versions are testable; S3/SQS versions use boto3 (untested here)."""
import json, os
from datetime import datetime


def snapshot_key(source: str, fetched_at: datetime, ext="json") -> str:
    return f"raw/{source}/{fetched_at:%Y/%m/%d}/{fetched_at:%Y%m%dT%H%M%SZ}.{ext}"


class LocalSnapshotStore:
    def __init__(self, root): self.root = root

    def put(self, source, raw):
        key = snapshot_key(source, raw.fetched_at)
        path = os.path.join(self.root, key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f: f.write(raw.body)
        return key


class S3SnapshotStore:  # UNTESTED: requires boto3 + AWS (task role credentials)
    def __init__(self, bucket, client=None):
        import boto3
        self.bucket, self.s3 = bucket, client or boto3.client("s3")

    def put(self, source, raw):
        key = snapshot_key(source, raw.fetched_at)
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=raw.body, ContentType=raw.content_type,
                           ServerSideEncryption="AES256")
        return key


class InMemoryQueue:
    def __init__(self): self.messages = []
    def publish(self, msg): self.messages.append(msg)
    def drain(self):
        out, self.messages = self.messages, []
        return out


class SqsQueue:  # UNTESTED
    def __init__(self, url, client=None):
        import boto3
        self.url, self.sqs = url, client or boto3.client("sqs")

    def publish(self, msg):
        self.sqs.send_message(QueueUrl=self.url, MessageBody=json.dumps(msg))
