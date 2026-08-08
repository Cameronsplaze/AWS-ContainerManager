

import pytest

from aws_cdk.assertions import Match

from tests.configs import LEAF_VOLUMES


## Hangs off `leaf_config`, which the classes below parametrize:
@pytest.fixture
def app(cdk_app, leaf_config):
    return cdk_app(leaf_config=leaf_config)



def test_vault_is_shared_in_the_base_stack(minimal_app):
    """
    One vault for EVERY container, not one each. (Vaults are free, but a per-leaf
    vault would mean restoring from a different place depending on the container).
    """
    minimal_app.base_template.resource_count_is("AWS::Backup::BackupVault", 1)

VOLUMES_BACKUPS_OFF = [config for config in LEAF_VOLUMES if not config.expected_output["Volume"]["EnableBackups"]]
@pytest.mark.parametrize("leaf_config", VOLUMES_BACKUPS_OFF, ids=lambda config: config.label)
class TestVolumeBackupsDisabled():
    """ `EnableBackups: False` should mean nothing to pay for, and nothing to run. """

    def test_no_backup_resources(self, app):
        """ The volume itself should still exist, just without anything to snapshot it. """
        volume_template = app.container_manager_volume_template
        # No role for AWS Backup to assume:
        assert not volume_template.find_resources(
            "AWS::IAM::Role",
            {
                "Properties": {
                    "AssumeRolePolicyDocument": {
                        "Statement": [
                            {
                                "Action": "sts:AssumeRole",
                                "Effect": "Allow",
                                "Principal": {"Service": "backup.amazonaws.com"},
                            },
                        ],
                    },
                }
            }
        )
        ## (NOTE: Can't just count lambdas here. Turning backups off tends to go with
        #    `KeepOnDelete: False`, which adds CDK's auto-delete-objects lambda.)
        assert not volume_template.find_resources(
            "AWS::Lambda::Function",
            {"Properties": {"Description": Match.string_like_regexp("Trigger-AWS-Backup")}},
        )


VOLUMES_BACKUPS_ON = [config for config in LEAF_VOLUMES if config.expected_output["Volume"]["EnableBackups"]]
@pytest.mark.parametrize("leaf_config", VOLUMES_BACKUPS_ON, ids=lambda config: config.label)
class TestVolumeBackupsEnabled():
    """ `EnableBackups: True` snapshots the volume's bucket every time the container spins down. """

    def test_todo(self, leaf_config):
        pass
