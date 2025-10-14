
import boto3
from moto import mock_aws
import pytest

from .utils import setup_autoscaling_group

DEFAULT_ENV_VARS = {
    "HOSTED_ZONE_ID": "Z_DUMMY_12345",  # Dummy value
    "DOMAIN_NAME": "test.example.com",
    "UNAVAILABLE_IP": "0.0.0.0",
    "DNS_TTL": "1",
    "RECORD_TYPE": "A"
}

@pytest.fixture()
def setup_env(monkeypatch):
    def _set_envs(env_vars: dict):
        """ Set the default env vars for the lambda """
        for k, v in env_vars.items():
            monkeypatch.setenv(k, v)
    return _set_envs

@mock_aws
class TestInstanceStateChangeHook:
    @classmethod
    def setup_class(cls):
        ## These imports have to be the long forum, to let us modify the values here:
        # https://stackoverflow.com/a/12496239/11650472
        import ContainerManager.leaf_stack_group.lambda_functions.instance_StateChange_hook.main as instance_StateChange_hook # pylint: disable=import-outside-toplevel # type: ignore
        cls.instance_StateChange_hook = instance_StateChange_hook

    
    def setup_method(self, _method):
        ## Override the lambda's boto3 client(s) here, to make sure moto mocks them:
        #    (All moto clients have to be in-scope, together. They'll error if in setup_class.)
        self.instance_StateChange_hook.route53_client = boto3.client('route53', region_name="us-west-2")
        self.instance_StateChange_hook.ec2_client = boto3.client('ec2', region_name="us-west-2")
        ## Create a hosted zone for each test:
        # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/route53/client/create_hosted_zone.html
        hosted_zone = self.instance_StateChange_hook.route53_client.create_hosted_zone(
            Name="example.com.",
            CallerReference="test-reference",
            HostedZoneConfig={
                'Comment': 'Test hosted zone',
                'PrivateZone': False
            }
        )
        ## Can't use monkeypatch.setenv here, because this isn't a test_* function
        #    and thus can't use fixtures.
        hosted_zone_id = hosted_zone["HostedZone"]["Id"].split("/")[-1]  # Update the env var to the real ID
        # Don't persist back into DEFAULT_ENV_VARS (shared mutable!)
        self.env = {**DEFAULT_ENV_VARS, "HOSTED_ZONE_ID": hosted_zone_id} # pylint: disable=attribute-defined-outside-init
        ## Create a record set for each test:
        # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/route53/client/change_resource_record_sets.html
        self.instance_StateChange_hook.route53_client.change_resource_record_sets(
            HostedZoneId=self.env['HOSTED_ZONE_ID'],
            ChangeBatch={
                'Changes': [{
                    'Action': 'CREATE',
                    'ResourceRecordSet': {
                        'Name': self.env['DOMAIN_NAME'],
                        'Type': self.env['RECORD_TYPE'],
                    'ResourceRecords': [{'Value': self.env['UNAVAILABLE_IP']}],
                    'TTL': int(self.env['DNS_TTL']),
                    }
                }]
            }
        )
        print(self.env)
        ## Create an ASG for each test:
        self.asg_name = "test-asg" # pylint: disable=attribute-defined-outside-init
        self.instance_StateChange_hook.asg_client, _ = setup_autoscaling_group(self.asg_name)

    def teardown_method(self, _method):
        # Reset the env vars, so each test is a "cold start":
        self.instance_StateChange_hook._env_vars = None # pylint: disable=protected-access

    def test_starting_record_values(self, setup_env):
        """ Test that the starting record values are correct (Other tests will change these) """
        setup_env(self.env)
        ## Check the record:
        records = self.instance_StateChange_hook.route53_client.list_resource_record_sets(
            HostedZoneId=self.env['HOSTED_ZONE_ID']
        )["ResourceRecordSets"]
        # There should be three records: the default NS and SOA, and our A record:
        assert len(records) == 3
        # The A record should be the last one:
        a_record = records[2]
        assert a_record["Name"] == self.env["DOMAIN_NAME"] + "."
        assert a_record["Type"] == self.env["RECORD_TYPE"]
        assert a_record["TTL"] == int(self.env["DNS_TTL"])
        assert a_record["ResourceRecords"] == [{"Value": self.env["UNAVAILABLE_IP"]}]


    @pytest.mark.parametrize("event_type,desired_capacity", [
        ("EC2 Instance Launch Successful", 1),
        ("EC2 Instance-terminate Lifecycle Action", 0),
    ])
    def test_lambda_sets_ip_events(self, setup_env, monkeypatch, event_type, desired_capacity):
        """ Test that the lambda sets the IP correctly on both event types """
        setup_env(self.env)
        ## First, update the ASG:
        self.instance_StateChange_hook.asg_client.update_auto_scaling_group(
            AutoScalingGroupName=self.asg_name,
            DesiredCapacity=desired_capacity,
        )
        ## Figure out the instance ID, if there is one:
        asg_info = self.instance_StateChange_hook.asg_client.describe_auto_scaling_instances()
        assert len(asg_info["AutoScalingInstances"]) == desired_capacity
        ## Depending on the event, set what the lambda will check for the IP:
        if event_type == "EC2 Instance Launch Successful":
            # Moto doesn't support public IPs, so we have to mock it:
            mock_ec2_response = {"Reservations": [{"Instances": [{"PublicIpAddress": "1.2.3.4"}]}]}
            monkeypatch.setattr(
                self.instance_StateChange_hook.ec2_client,
                "describe_instances",
                lambda *args, **kwargs: mock_ec2_response
            )
            instance_id = asg_info["AutoScalingInstances"][0]["InstanceId"]
        else:
            monkeypatch.setenv("UNAVAILABLE_IP", "1.2.3.4")
            instance_id = "i-1234567890abcdef0" # Dummy value, won't be used.
        ## Run the lambda:
        self.instance_StateChange_hook.lambda_handler(
            event={
                "detail-type": event_type,
                "detail": {
                    "AutoScalingGroupName": self.asg_name,
                    "EC2InstanceId": instance_id
                }
            },
            context={},
        )
        ## Check the record:
        records = self.instance_StateChange_hook.route53_client.list_resource_record_sets(
            HostedZoneId=self.env['HOSTED_ZONE_ID']
        )["ResourceRecordSets"]
        a_record = records[2]
        assert a_record["ResourceRecords"] == [{"Value": "1.2.3.4"}]

    def test_lambda_exit_if_asg_instance_coming_up_on_terminate(self, setup_env, monkeypatch):
        """
        If you flag a instance to terminate, right when the other is coming up, there's a
        window where the terminate one will happen just after the new one comes up, and
        wipe the new one's IP. This tests that if it happens, the lambda just exits.
        """
        setup_env(self.env)
        ## First, update the ASG:
        instance_id = "i-1234567890abcdef0"
        lifecycle_state = "Pending"
        self.instance_StateChange_hook.asg_client.update_auto_scaling_group(
            AutoScalingGroupName=self.asg_name,
            DesiredCapacity=0,
        )
        mock_asg_response = {
            'AutoScalingGroups': [{
                'Instances': [
                    {
                        "LifecycleState": lifecycle_state,
                        "InstanceId": instance_id,
                    },
                ],
            }],
        }
        monkeypatch.setattr(
            self.instance_StateChange_hook.asg_client,
            "describe_auto_scaling_groups",
            lambda *args, **kwargs: mock_asg_response
        )
        ## Run the lambda, expect it to exit:
        with pytest.raises(SystemExit, match=f"Instance '{instance_id}' is in '{lifecycle_state}', skipping this termination event."):
            self.instance_StateChange_hook.lambda_handler(
                event={
                    "detail-type": "EC2 Instance-terminate Lifecycle Action",
                    "detail": {
                        "AutoScalingGroupName": self.asg_name,
                        "EC2InstanceId": instance_id
                    }
                },
                context={},
            )

    def test_lambda_raises_on_unknown_event(self, setup_env):
        """ Test that the lambda raises an error on an unknown event type """
        setup_env(self.env)
        event_type = "Unknown Event"
        with pytest.raises(RuntimeError, match=f"Unknown event type: '{event_type}'. Did you mess with the EventBridge Rule??"):
            self.instance_StateChange_hook.lambda_handler(
                event={
                    "detail-type": event_type,
                },
                context={},
            )
