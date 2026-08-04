

import hashlib
import pytest

from aws_cdk.assertions import Match

from tests.configs import LEAF_VOLUMES


@pytest.fixture(scope="module")
def app(cdk_app):
    return cdk_app(leaf_config=LEAF_VOLUMES)


class TestS3Volumes():

    def test_volume_count(self, app):
        # Check the number of S3 volumes created matches the config:
        volumes_config = LEAF_VOLUMES.create_config()
        expected_volume_count = len(volumes_config["Volumes"])
        # Each volume is one bucket, with one S3 Files file system on top of it:
        app.container_manager_volumes_template.resource_count_is(
            "AWS::S3::Bucket",
            expected_volume_count,
        )
        app.container_manager_volumes_template.resource_count_is(
            "AWS::S3Files::FileSystem",
            expected_volume_count,
        )

    @pytest.mark.parametrize(
        "volume_id,volume_config",
        LEAF_VOLUMES.create_config()["Volumes"].items(),
    )
    def test_volume_properties_s3(self, volume_id, volume_config, app):
        volume_template = app.container_manager_volumes_template

        ## Make sure you're testing the right volume. Unlike EFS, nothing inside the
        # bucket's properties says which volume it belongs to. The file system IS a
        # L1 construct at the root of the stack though, so it's logical id is stable:
        file_systems = volume_template.find_resources("AWS::S3Files::FileSystem")
        file_system_id = f"S3FilesFs{volume_id}"
        assert file_system_id in file_systems, f"No S3 Files FileSystem for volume '{volume_id}'."
        file_system_properties = file_systems[file_system_id]["Properties"]

        # Only pull files into the cache when they're first touched, and let them
        # expire back out as fast as AWS allows (the cache is what costs money):
        assert file_system_properties["SynchronizationConfiguration"] == {
            "ExpirationDataRules": [
                {"DaysAfterLastAccess": 1},
            ],
            "ImportDataRules": [
                {
                    "Prefix": "",
                    "SizeLessThan": 10 * 1024 * 1024 * 1024, # 10 GB
                    "Trigger": "ON_DIRECTORY_FIRST_ACCESS",
                },
            ],
        }

        # Now walk from the file system to the bucket it's actually backed by:
        bucket_id = file_system_properties["Bucket"]["Fn::GetAtt"][0]

        bucket_properties = {
            # S3 Files relies on object versions for consistency, it's required:
            "VersioningConfiguration": {
                "Status": "Enabled",
            },
            # Make sure we opted into the (paid) metrics:
            "MetricsConfigurations": [
                {"Id": "S3FilesFilter"},
            ],
            "LifecycleConfiguration": {
                "Rules": [
                    {
                        "Status": "Enabled",
                        # Keep ALL versions if they're new, but cap how long they stick around:
                        "NoncurrentVersionExpiration": {"NoncurrentDays": 30},
                        "Transitions": [
                            {
                                "StorageClass": "INTELLIGENT_TIERING",
                                "TransitionInDays": 0,
                            },
                        ],
                    },
                ],
            },
            # Only buckets that get nuked on delete should have the auto-delete
            # helper attached, AND it should be absent if not wanted:
            "Tags": Match.array_with([
                {"Key": "aws-cdk:auto-delete-objects", "Value": "true"},
            ]) if not volume_config["KeepOnDelete"] else Match.absent(),
        }
        # Make sure the dict above exists, on THIS volume's bucket:
        buckets = volume_template.find_resources("AWS::S3::Bucket", {"Properties": bucket_properties})
        assert bucket_id in buckets, f"Bucket for volume '{volume_id}' didn't match the expected properties."
        # The Update/Deletion Policies are just outside of "Properties",
        #    so we have to check them manually:
        bucket_dict = buckets[bucket_id]
        assert bucket_dict['UpdateReplacePolicy'] == ('Retain' if volume_config["KeepOnDelete"] else 'Delete')
        assert bucket_dict['DeletionPolicy'] == ('RetainExceptOnCreate' if volume_config["KeepOnDelete"] else 'Delete')

        ## Make sure in-transit encryption is enforced for all clients.
        # (EFS did this with a FileSystemPolicy, S3 does it with a BucketPolicy):
        volume_template.has_resource_properties(
            "AWS::S3::BucketPolicy",
            {
                "Bucket": {"Ref": bucket_id},
                "PolicyDocument": {
                    "Statement": Match.array_with([
                        Match.object_like({
                            "Effect": "Deny",
                            "Principal": {
                                "AWS": "*"
                            },
                            "Action": "s3:*",
                            "Condition": {
                                "Bool": {
                                    "aws:SecureTransport": "false"
                                }
                            },
                        }),
                    ]),
                },
            },
        )


    @pytest.mark.parametrize(
        "volume_id,volume_config",
        LEAF_VOLUMES.create_config()["Volumes"].items(),
    )
    def test_volume_properties_container(self, volume_id, volume_config, app):
        ## Check the ECS Task Definition to make sure it has the right
        #    mount points for this volume (And verify ReadOnly is correct):
        container_template = app.container_manager_container_template
        for path in volume_config["Paths"]:
            container_template.has_resource_properties(
                "AWS::ECS::TaskDefinition",
                {
                    "ContainerDefinitions": Match.array_with([
                        Match.object_like({
                            "MountPoints":
                            Match.array_with([
                                {
                                    "ContainerPath": path["Path"],
                                    "ReadOnly": path["ReadOnly"],
                                    "SourceVolume": f"S3FilesFs-{volume_id}-{hashlib.md5(path['Path'].encode()).hexdigest()[:8]}",
                                },
                            ]),
                        }),
                    ])
                },
            )
