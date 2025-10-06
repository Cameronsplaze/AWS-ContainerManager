

import pytest

from aws_cdk.assertions import Match

from tests.config_parser.test_base_config_parser import LEAF_VOLUMES

@pytest.fixture
def volume_template(create_leaf_stack_container_manager, to_template):
    # Setup the template here, so each test can share it:
    container_manager_stack = create_leaf_stack_container_manager(
        leaf_config=LEAF_VOLUMES,
    )
    # The volume is a nested stack, just return that:
    #  (returning the whole stack just is references to nested stacks. Nothing else)
    return to_template(container_manager_stack.volumes_nested_stack)


# TODO: NOTE: For the next time I take a pass at this:
# - Need to loop over the access points to check THEIR properties too,
#   since  that's where "read-only" is stored. Append it to the end of the test
#   below, since 1) you'll need the properties it defines to make sure you're checking
#   the right AP's, and 2) if this test fails, there's no point to try the AP tests too.

class TestEfsVolumes():

    def test_volume_count(self, volume_template):
        # Check the number of EFS volumes created matches the config::
        volumes_config = LEAF_VOLUMES.create_config()
        expected_efs_count = len(volumes_config["Volumes"])
        volume_template.resource_count_is("AWS::EFS::FileSystem", expected_efs_count)

    @pytest.mark.parametrize(
        "volume_id,volume_config",
        enumerate(LEAF_VOLUMES.create_config()["Volumes"], start=1),
    )
    def test_volume_properties(self, volume_id, volume_config, volume_template):
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
                "Statement": [
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
                    # # Enforce in-transit encryption for all clients:
                    # {
                    #     "Effect": "Deny",
                    #     "Principal": {
                    #         "AWS": "*"
                    #     },
                    #     "Action": "*",
                    #     "Condition": {
                    #         "Bool": {
                    #             "aws:SecureTransport": "false"
                    #         }
                    #     }
                    # }
                ],
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
