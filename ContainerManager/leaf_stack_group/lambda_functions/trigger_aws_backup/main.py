
"""
Lambda code for snapshotting the volume's S3 bucket with AWS Backup,
whenever the container spins down (aka someone just finished playing).
"""

import os
import json
from functools import cache
from dataclasses import dataclass, asdict

import boto3

# frozen=True: This should never be modified (change cdk inputs instead)
@dataclass(frozen=True)
class EnvVars:
    """ Env vars that the lambda needs. """
    # pylint: disable=invalid-name
    BACKUP_VAULT_NAME: str
    # What to snapshot, and the role AWS Backup assumes to read it:
    BUCKET_ARN: str
    BACKUP_ROLE_ARN: str
    # How long to keep the snapshot around for:
    DELETE_AFTER_DAYS: str
    # pylint: enable=invalid-name

@cache
def get_env_vars() -> EnvVars:
    """ Lazy-load and Validate the environment variables """
    # EnvVars will naturally error with ALL the missing env-vars on creation:
    return EnvVars(**{
        # DON'T use getenv. We don't want the key to exist if it's missing.
        k: os.environ[k] for k in EnvVars.__annotations__.keys() if k in os.environ
    })

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


def purge_noncurrent_versions(bucket_name: str) -> None:
    """
    Permanently delete every noncurrent version and delete-marker in the bucket.
    They'll get stored in the backup snapshot otherwise, and cost pointless money.
    """
    s3_client = get_s3_client()
    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3/paginator/ListObjectVersions.html
    for page in s3_client.get_paginator("list_object_versions").paginate(Bucket=bucket_name):
        ## ONLY delete IsLatest=False. Deleting the newest DeleteMarker would *un*-delete the
        # file, and deleting the newest Version would eat the save we're about to back up.
        # Both lists mix latest and noncurrent entries, so they filter the exact same way.
        old_versions = [
            {"Key": obj["Key"], "VersionId": obj["VersionId"]}
            for obj in page.get("Versions", []) + page.get("DeleteMarkers", [])
            if not obj["IsLatest"]
        ]
        if not old_versions:
            continue
        ## A page holds at most 1000 entries and delete_objects takes at most 1000, so they
        # line up 1:1 and there's nothing extra to batch. DELETE requests are free.
        # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3/client/delete_objects.html
        response = s3_client.delete_objects(
            Bucket=bucket_name,
            # Quiet: only report what FAILED. We don't care about listing the successes.
            Delete={"Objects": old_versions, "Quiet": True},
        )
        ## delete_objects reports per-object failures inside a 200, it does NOT raise:
        errors = response.get("Errors", [])
        if errors:
            print(json.dumps({"DeleteObjectsErrors": errors}, default=str))


def lambda_handler(event: dict, context: dict) -> None:
    """ Main function of the lambda. """
    env = get_env_vars()
    print(json.dumps({"Event": event, "Context": context, "Env": asdict(env)}, default=str))

    ## TODO: Hook into the S3 Files PendingExports metric, to make sure S3 is up to date first.
    ##      (We spin down on "instance-terminate", which fires BEFORE the container's last
    ##       writes have exported, so right now the snapshot can miss the end of a session.)

    purge_noncurrent_versions(env.BUCKET_ARN.split(":")[-1])

    ## Snapshot the bucket. There's no BackupPlan on purpose: a plan only exists to run
    # backups on a *schedule*, and we want one restore point per play session instead.
    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/backup/client/start_backup_job.html
    backup_client = get_backup_client()
    backup_client.start_backup_job(
        BackupVaultName=env.BACKUP_VAULT_NAME,
        ResourceArn=env.BUCKET_ARN,
        IamRoleArn=env.BACKUP_ROLE_ARN,
        # https://docs.aws.amazon.com/aws-backup/latest/devguide/API_Lifecycle.html
        Lifecycle={
            ## DO NOT add 'MoveToColdStorageAfterDays', not supported for S3.
            "DeleteAfterDays": int(env.DELETE_AFTER_DAYS),
        },
    )
