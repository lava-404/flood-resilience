"""SQS consumer for the forecast worker (ECS Fargate service). UNTESTED against AWS.
Message is deleted ONLY after success; failures are left to SQS retry -> DLQ (redrive policy in Terraform)."""
import json, logging, os, signal
from datetime import datetime, timezone
from floodcommon import metrics
from floodcommon.config import database_dsn
from floodcommon.pgrepo import PgRepo
from .worker import handle_job

log, stop = logging.getLogger("floodres.worker"), False
signal.signal(signal.SIGTERM, lambda *_: globals().__setitem__("stop", True))


def main():
    import boto3
    logging.basicConfig(level=logging.INFO)
    sqs, url, repo = boto3.client("sqs"), os.environ["FORECAST_QUEUE_URL"], PgRepo(database_dsn())
    replay = os.getenv("REPLAY_MODE") == "1"
    while not stop:
        for m in sqs.receive_message(QueueUrl=url, MaxNumberOfMessages=5, WaitTimeSeconds=20).get("Messages", []):
            try:
                job = json.loads(m["Body"])
                now = datetime.fromisoformat(job["as_of"]) if replay else datetime.now(timezone.utc)
                log.info("job %s -> %s", job["job_key"], handle_job(job, repo, now))
                sqs.delete_message(QueueUrl=url, ReceiptHandle=m["ReceiptHandle"])
            except Exception:
                log.exception("job failed; leaving on queue for retry/DLQ")
                metrics.put("ForecastJobFailure", 1)


if __name__ == "__main__":
    main()
