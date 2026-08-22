
"""
Lambda code for snapshotting the volume's S3 bucket with AWS Backup,
whenever the container spins down (aka someone just finished playing).
"""

## TODO: Add this to the metric dashboard somewhere! (At least the execution errors...)
## TODO: This failing should also trigger SNS emails n such. (Base stack only?)

import os
import json
import time
from typing import Any
from functools import cache
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone

import boto3

from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.data_classes import EventBridgeEvent, event_source
from aws_lambda_powertools.utilities.typing import LambdaContext

logger = Logger()

## How long to wait before the first check, to let S3 File metrics settle:
#   60s to let the container write any last saves to EFS.
#   60s after last write, to queue files for export.
#   60s for those metrics to get to cloudwatch and be queryable.
EXPORT_SETTLE_SEC = 180
# How often to re-check after that:
EXPORT_POLL_INTERVAL_SEC = 30


# frozen=True: This should never be modified (change cdk inputs instead)
@dataclass(frozen=True)
class EnvVars:
    """ Env vars that the lambda needs. """
    # pylint: disable=invalid-name
    BACKUP_VAULT_NAME: str
    # What to snapshot, and the role AWS Backup assumes to read it:
    BUCKET_ARN: str
    BACKUP_ROLE_ARN: str
    # Who to ask if the bucket is done syncing yet:
    FILE_SYSTEM_ID: str
    # How long to keep the snapshot around for:
    DELETE_AFTER_DAYS: int
    # pylint: enable=invalid-name

@cache
def get_env_vars() -> EnvVars:
    """ Lazy-load and Validate the environment variables """
    env_vars: dict[str, Any] = {
        # If it's supposed to be a string already, DON'T json.loads it:
        k: os.environ[k] if var_type is str else json.loads(os.environ[k])
        for k, var_type in EnvVars.__annotations__.items()
        if k in os.environ
    }
    # EnvVars will naturally error with ALL the missing env-vars on creation:
    return EnvVars(**env_vars)

## Boto3 Clients:
# ALWAYS use @cache for clients. Even if they're always called, it helps
# them not exist until moto is setup inside of the test suite.
@cache
def get_backup_client():
    """ Used for starting the backup job """
    return boto3.client('backup')

@cache
def get_s3_client():
    """ Used for clearing out old object versions before the backup """
    return boto3.client('s3')

@cache
def get_cloudwatch_client():
    """ Used for checking if S3 Files is done exporting yet """
    return boto3.client('cloudwatch')


def get_pending_exports(file_system_id: str) -> float | None:
    """
    The newest value of the S3 Files 'PendingExports' metric,
    or None if CloudWatch doesn't have data from the last period.
    """
    cloudwatch_client = get_cloudwatch_client()
    now = datetime.now(timezone.utc)
    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/cloudwatch/client/get_metric_data.html
    response = cloudwatch_client.get_metric_data(
        MetricDataQueries=[{
            "Id": "pending_exports",
            "MetricStat": {
                # https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-files-monitoring-cloudwatch.html
                "Metric": {
                    "Namespace": "AWS/S3/Files",
                    "MetricName": "PendingExports",
                    "Dimensions": [{"Name": "FileSystemId", "Value": file_system_id}],
                },
                # S3 Files publishes this once a minute, and 'Sum' is the only valid stat:
                "Period": 60,
                "Stat": "Sum",
            },
        }],
        StartTime=now - timedelta(seconds=60),
        EndTime=now,
        # Newest first, since Values[0] is the only one we care about:
        ScanBy="TimestampDescending",
    )
    values = response["MetricDataResults"][0]["Values"]
    return values[0] if values else None


def wait_for_exports_to_finish(file_system_id: str) -> None:
    """
    Block until S3 Files has pushed every last write out to the bucket.
    """
    ## Give S3 Files time to start syncing, so you don't prematurely think it's done:
    time.sleep(EXPORT_SETTLE_SEC)

    while True:
        pending_exports = get_pending_exports(file_system_id)
        if pending_exports == 0:
            return
        logger.debug("Waiting for S3 Files to finish exporting...", extra={"PendingExports": pending_exports})
        time.sleep(EXPORT_POLL_INTERVAL_SEC)
    # Just let this timeout if it goes over 15min. That likely means the container
    # spun back up, OR we need to look closer at a bug we don't want to hide.
    # (This triggers a base-stack notification/email on error anyways).


def purge_noncurrent_versions(bucket_name: str) -> None:
    """
    Permanently delete every noncurrent version and delete-marker in the bucket.
    They'll get stored in the backup snapshot otherwise, and cost pointless money.
    """
    s3_client = get_s3_client()
    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3/paginator/ListObjectVersions.html
    for page in s3_client.get_paginator("list_object_versions").paginate(Bucket=bucket_name):
        old_versions = [
            {"Key": obj["Key"], "VersionId": obj["VersionId"]}
            for obj in page.get("Versions", []) + page.get("DeleteMarkers", [])
            if not obj["IsLatest"]
        ]
        if not old_versions:
            continue
        ## A page holds at most 1000 entries and delete_objects takes at most 1000
        # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3/client/delete_objects.html
        response = s3_client.delete_objects(
            Bucket=bucket_name,
            # Quiet: only report what FAILED. We don't care about listing the successes.
            Delete={"Objects": old_versions, "Quiet": True},
        )
        ## delete_objects reports per-object failures inside a 200, it does NOT raise:
        errors = response.get("Errors", [])
        if errors:
            logger.warning("Failed to delete some noncurrent versions.", extra={"DeleteObjectsErrors": errors})
        logger.debug("Deleted noncurrent versions from bucket.", extra={"DeletedObjectsCount": len(old_versions), "Response": response})


def trigger_backup_job() -> None:
    """ Trigger a backup job for the bucket. No need to wait for it to finish. """
    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/backup/client/start_backup_job.html
    env = get_env_vars()
    backup_client = get_backup_client()
    backup_client.start_backup_job(
        BackupVaultName=env.BACKUP_VAULT_NAME,
        ResourceArn=env.BUCKET_ARN,
        IamRoleArn=env.BACKUP_ROLE_ARN,
        # https://docs.aws.amazon.com/aws-backup/latest/devguide/API_Lifecycle.html
        Lifecycle={
            ## DO NOT add 'MoveToColdStorageAfterDays', not supported for S3.
            "DeleteAfterDays": env.DELETE_AFTER_DAYS,
        },
    )


# https://docs.aws.amazon.com/powertools/python/latest/utilities/data_classes/#eventbridge
@event_source(data_class=EventBridgeEvent)
@logger.inject_lambda_context(clear_state=True, log_event=False)
def lambda_handler(event: EventBridgeEvent, context: LambdaContext) -> None: # pylint: disable=unused-argument
    """ Main function of the lambda. """
    try:
        env = get_env_vars()
        logger.append_keys(env_vars=asdict(env))

        wait_for_exports_to_finish(env.FILE_SYSTEM_ID)
        purge_noncurrent_versions(env.BUCKET_ARN.split(":")[-1])
        trigger_backup_job()
    except Exception:
        logger.exception("Failed to create a backup job.")
        raise
    logger.info("Successfully created a backup job.")
