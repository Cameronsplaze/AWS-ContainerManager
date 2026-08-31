

import hashlib
import pytest

from aws_cdk.assertions import Match

from tests.configs import LEAF_VOLUMES


## The app under test always uses `container_id="test-stack"` (see `tests/cloudformation/conftest.py`),
# and the container name is that, title-cased with the non-alphanumerics stripped out:
CONTAINER_NAME = "TestStack"


## Both of these hang off `leaf_config`, which the class below parametrizes:
@pytest.fixture
def app(cdk_app, leaf_config):
    return cdk_app(leaf_config=leaf_config)

@pytest.fixture
def volume_config(leaf_config):
    return leaf_config.create_config()["Volume"]


def test_no_volume_declared_creates_nothing(minimal_app):
    """
    "Volume" is optional. LEAF_MINIMAL leaves it out, and that should mean NO storage
    at all, instead of an empty bucket nobody asked to pay for.
    """
    volume_template = minimal_app.container_manager_volume_template
    volume_template.resource_count_is("AWS::S3::Bucket", 0)
    volume_template.resource_count_is("AWS::S3Files::FileSystem", 0)
    volume_template.resource_count_is("AWS::S3Files::MountTarget", 0)
    # And nothing should be mounted into the container either:
    minimal_app.container_manager_container_template.has_resource_properties(
        "AWS::ECS::TaskDefinition",
        {"Volumes": Match.absent()},
    )


## This class will run all it's tests per each of LEAF_VOLUMES.
@pytest.mark.parametrize("leaf_config", LEAF_VOLUMES, ids=lambda config: config.label)
class TestS3Volumes():

    def test_volume_count(self, app):
        # One volume per container: one bucket, with one S3 Files file system on top of it:
        app.container_manager_volume_template.resource_count_is("AWS::S3::Bucket", 1)
        app.container_manager_volume_template.resource_count_is("AWS::S3Files::FileSystem", 1)

    def test_volume_properties_s3(self, app, volume_config):
        volume_template = app.container_manager_volume_template

        ## Unlike EFS, nothing inside the bucket's properties says which volume it belongs
        # to. The file system IS a L1 construct at the root of the stack though, so it's
        # logical id is stable:
        file_systems = volume_template.find_resources("AWS::S3Files::FileSystem")
        file_system_id = f"S3FilesFs{CONTAINER_NAME}"
        assert file_system_id in file_systems, f"No S3 Files FileSystem with the id '{file_system_id}'."
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
                    "SizeLessThan": 256 * 1024 * 1024, # 256 MiB
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
            "LifecycleConfiguration": {
                "Rules": [
                    {
                        "Status": "Enabled",
                        ## Old versions are pure cost here (S3 stores a full copy of the
                        # file per change), so sweep them as fast as AWS lets us:
                        "NoncurrentVersionExpiration": {
                            "NoncurrentDays": 1,
                        },
                        # Otherwise each leftover marker bills as a 128KiB object:
                        "ExpiredObjectDeleteMarker": True,
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
        # Make sure the dict above exists, on this volume's bucket:
        buckets = volume_template.find_resources("AWS::S3::Bucket", {"Properties": bucket_properties})
        assert bucket_id in buckets, "The bucket didn't match the expected properties."
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


    def test_volume_properties_container(self, app, volume_config):
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
                                    "SourceVolume": f"S3FilesFs-{CONTAINER_NAME}-{hashlib.md5(path['Path'].encode()).hexdigest()[:8]}",
                                },
                            ]),
                        }),
                    ])
                },
            )
