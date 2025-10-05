

import json
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
# - Don't test against config_input directly. The Schema tests should do
#   config_input => create_config() => expected_output. These just test against
#   expected_output.
# - For the EFS config, "elasticfilesystem:ClientWrite" is for ALL Efs's. The "readOnly"
#   param is for the access-points themselves. (you might have one read-only, and one not. So
#   it CAN'T be on the Efs side anyways). Move to the shared-test.
# - Combine these tests into a parameterized test. Then create a SECOND
#   that loops over the Efs Access Points instead. (It can loop over EFS too, then
#   just pull the access points from the template based on the EFS it's on?)
class TestEfsVolumes():

    def test_volume_count(self, volume_template):
        # Check the number of EFS volumes created matches the config::
        volumes_config = LEAF_VOLUMES.create_config()
        expected_efs_count = len(volumes_config["Volumes"])
        volume_template.resource_count_is("AWS::EFS::FileSystem", expected_efs_count)

    # @pytest.mark.parametrize("volume_config", LEAF_VOLUMES.create_config()["Volumes"])
    # def test_volumes(self, volume_config, volume_template):
    #     # def _all_efs_resources(template_json):
    #     #     return {
    #     #         logical_id: res
    #     #         for logical_id, res in template_json.get("Resources", {}).items()
    #     #         if res.get("Type") == "AWS::EFS::FileSystem"
    #     #     }
    #     # efs_resources = _all_efs_resources(volume_template.to_json())
    #     # print(json.dumps(efs_resources, indent=2))
    #     # assert False
    #     assert False, volume_config


    def test_shared_settings(self, volume_template, print_template):
        volume_template.all_resources_properties(
            # For ALL EFS Volumes...:
            "AWS::EFS::FileSystem",
            {
                # Make sure encryption is always on:
                "Encrypted": True,
                "FileSystemPolicy": {
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Principal": {
                                "AWS": "*"
                            },
                            # Prevent anonymous access:
                            # (not is reserved, so they made it not_)
                            "Action": Match.not_(Match.array_with(["elasticfilesystem:ClientMount"])),
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
            },
        )

    def test_volume_defaults(self, volume_template, print_template):
        volume_properties = {
            # Make sure you're testing the right EFS Volume:
            "FileSystemTags": [
                {
                    "Key": "Name",
                    "Value": "TestLeafStack-ContainerManager/VolumesNestedStack/Efs-1"
                }
            ],
            # Default to keeping the data safe:
            "BackupPolicy": {
                "Status": "ENABLED"
            },
            "FileSystemPolicy": {
                "Statement": [
                    {
                        # You should have write-access by default:
                        "Action": Match.array_with([
                            "elasticfilesystem:ClientWrite",
                        ]),
                    },
                ],
            }
        }
        volume_template.has_resource_properties(
            "AWS::EFS::FileSystem",
            volume_properties,
        )
        # The Update/Deletion Policies are just outside of "Properties",
        #    so we have to check them manually:
        volume_js = volume_template.find_resources("AWS::EFS::FileSystem", {"Properties": volume_properties})
        assert len(volume_js) == 1, f"Expected to find exactly one EFS volume. Found {len(volume_js)}."
        # The one key is random and pointless for testing, move to it's dict:
        volume_js = list(volume_js.values())[0]
        assert volume_js['UpdateReplacePolicy'] == 'Retain'
        assert volume_js['DeletionPolicy'] == 'RetainExceptOnCreate'

    def test_volume_all_true(self, volume_template, print_template):
        volume_properties = {
            # Make sure you're testing the right EFS Volume:
            "FileSystemTags": [
                {
                    "Key": "Name",
                    "Value": "TestLeafStack-ContainerManager/VolumesNestedStack/Efs-1"
                },
            ],
            # Default to keeping the data safe:
            "BackupPolicy": {
                "Status": "ENABLED"
            },
            "FileSystemPolicy": {
                "Statement": [
                    {
                        # You should have write-access by default:
                        "Action": Match.array_with([
                            "elasticfilesystem:ClientWrite",
                        ]),
                    },
                ],
            }
        }
        volume_template.has_resource_properties(
            "AWS::EFS::FileSystem",
            volume_properties,
        )
        # The Update/Deletion Policies are just outside of "Properties",
        #    so we have to check them manually:
        volume_js = volume_template.find_resources("AWS::EFS::FileSystem", {"Properties": volume_properties})
        assert len(volume_js) == 1, f"Expected to find exactly one EFS volume. Found {len(volume_js)}."
        # The one key is random and pointless for testing, move to it's dict:
        volume_js = list(volume_js.values())[0]
        assert volume_js['UpdateReplacePolicy'] == 'Retain'
        assert volume_js['DeletionPolicy'] == 'RetainExceptOnCreate'


    def test_volume_all_false(self, volume_template, print_template):
        volume_properties = {
            # Make sure you're testing the right EFS Volume:
            "FileSystemTags": [
                {
                    "Key": "Name",
                    "Value": "TestLeafStack-ContainerManager/VolumesNestedStack/Efs-3"
                }
            ],
            # Doesn't have a backup policy:
            "BackupPolicy": Match.absent(),
            "FileSystemPolicy": {
                "Statement": [
                    {
                        # You should have write-access by default:
                        "Action": Match.array_with([
                            "elasticfilesystem:ClientWrite",
                        ]),
                    },
                ],
            }
        }
        volume_template.has_resource_properties(
            "AWS::EFS::FileSystem",
            volume_properties,
        )
        # The Update/Deletion Policies are just outside of "Properties",
        #    so we have to check them manually:
        volume_dict = volume_template.find_resources("AWS::EFS::FileSystem", {"Properties": volume_properties})
        assert len(volume_dict) == 1, f"Expected to find exactly one EFS volume. Found {len(volume_dict)}."
        # The one key is random and pointless for testing, move to *it's* dict:
        volume_dict = list(volume_dict.values())[0]
        assert volume_dict['UpdateReplacePolicy'] == 'Delete'
        assert volume_dict['DeletionPolicy'] == 'Delete'
