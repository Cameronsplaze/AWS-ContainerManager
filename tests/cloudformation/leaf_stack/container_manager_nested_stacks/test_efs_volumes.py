

import pytest

from aws_cdk.assertions import Match

from tests.config_parser.test_base_config_parser import LEAF_VOLUMES


@pytest.fixture(scope="module")
def app(cdk_app):
    return cdk_app(leaf_config=LEAF_VOLUMES)


class TestEfsVolumes():

    def test_volume_count(self, app):
        # Check the number of EFS volumes created matches the config::
        volumes_config = LEAF_VOLUMES.create_config()
        expected_efs_count = len(volumes_config["Volumes"])
        app.container_manager_volumes_template.resource_count_is(
            "AWS::EFS::FileSystem",
            expected_efs_count,
        )

    @pytest.mark.parametrize(
        "volume_id,volume_config",
        enumerate(LEAF_VOLUMES.create_config()["Volumes"], start=1),
    )
    def test_volume_properties_efs(self, volume_id, volume_config, app, print_template):
        volume_template = app.container_manager_volumes_template
        # print_template(volume_template)
        volume_properties = {
            # Make sure you're testing the right EFS Volume:
            "FileSystemTags": [
                {
                    "Key": "Name",
                    "Value": f"TestLeafStack-ContainerManager/VolumesNestedStack/Efs-{volume_id}",
                }
            ],
            # Make sure the backup policy is correct, AND absent if not wanted:
            "BackupPolicy": {
                "Status": "ENABLED"
            } if volume_config["EnableBackups"] else Match.absent(),
            # Make sure encryption is always on:
            "Encrypted": True,
            "FileSystemPolicy": {
                "Statement": Match.array_with([
                    ## Enforce in-transit encryption for all clients:
                    # (Taken from AWS's console, when creating an EFS manually.)
                    {
                        "Effect": "Deny",
                        "Principal": {
                            "AWS": "*"
                        },
                        "Action": "*",
                        "Condition": {
                            "Bool": {
                                "aws:SecureTransport": "false"
                            }
                        }
                    },
                    ## Allow the ECS tasks to use the access point:
                    {
                        "Effect": "Allow",
                        "Principal": {
                            "AWS": "*"
                        },
                        "Action": Match.array_with([
                            # "ReadOnly" is on the access-point itself. Plus the
                            # EC2's access point should be able to modify any files:
                            "elasticfilesystem:ClientWrite",
                            # Prevent anonymous access:
                            Match.not_("elasticfilesystem:ClientMount"),
                        ]),
                        # Make sure public access is blocked:
                        "Condition": {
                            "Bool": {
                                "elasticfilesystem:AccessedViaMountTarget": "true",
                            }
                        },
                    },
                ]),
            },
        }
        # Make sure the dict above exists:
        volume_template.has_resource_properties(
            "AWS::EFS::FileSystem",
            volume_properties,
        )
        # And it's the only one:
        volume_template.resource_properties_count_is("AWS::EFS::FileSystem", volume_properties, 1)
        # The Update/Deletion Policies are just outside of "Properties",
        #    so we have to check them manually:
        volume_dict = volume_template.find_resources("AWS::EFS::FileSystem", {"Properties": volume_properties})
        # The one key is random and pointless for testing, move to it's dict:
        volume_dict = list(volume_dict.values())[0]
        assert volume_dict['UpdateReplacePolicy'] == ('Retain' if volume_config["KeepOnDelete"] else 'Delete')
        assert volume_dict['DeletionPolicy'] == ('RetainExceptOnCreate' if volume_config["KeepOnDelete"] else 'Delete')


    @pytest.mark.parametrize(
        "volume_id,volume_config",
        enumerate(LEAF_VOLUMES.create_config()["Volumes"], start=1),
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
                                    "SourceVolume": f"Efs-{volume_id}{path['Path'].replace('/', '-')}",
                                },
                            ]),
                        }),
                    ])
                },
            )
