"""CloudWatch custom metrics (UNTESTED: needs boto3 + cloudwatch:PutMetricData). No-op when disabled."""
import logging
log = logging.getLogger("floodres.metrics")


def put(name, value, unit="None", dims=None, enabled=True):
    if not enabled: return
    try:
        import boto3
        boto3.client("cloudwatch").put_metric_data(Namespace="FloodResilience", MetricData=[
            {"MetricName": name, "Value": float(value), "Unit": unit,
             "Dimensions": [{"Name": k, "Value": v} for k, v in (dims or {}).items()]}])
    except Exception as e:                                    # metrics must never take the service down
        log.warning("metric %s not published: %s", name, e)
